"""Flag evaluation. Never raises: unknown flag, bad context, bad clock, store
error or any other failure gives OFF, whatever the default says."""

import hashlib
import threading
from collections import OrderedDict
from dataclasses import dataclass

from identity import IdentityError
from identity.tokens import check_live

from .context import EvalContext
from .errors import FlagError
from .model import MAX_BP

MAX_TTL = 60
MAX_CACHE = 1024


@dataclass(frozen=True)
class Decision:
    enabled: bool
    reason: str


OFF_UNKNOWN = Decision(False, "error.unknown_flag")


def bucket(flag_key: str, unit: str) -> int:
    """Stable 0..9999 bucket; the same inputs give the same answer on every node,
    and raising the percentage only ever adds units."""
    digest = hashlib.sha256(f"featureflags.v1\x00{flag_key}\x00{unit}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % (MAX_BP)


def read_clock(clock) -> int:
    now = clock()
    if type(now) is not int or now <= 0:
        raise FlagError("FLG-030")
    return now


class FlagEvaluator:
    def __init__(self, registry, store, clock, *, ttl=15, max_entries=256):
        self.registry, self.store, self.clock = registry, store, clock
        self.ttl = min(max(ttl, 0), MAX_TTL) if type(ttl) is int else 0
        self.max_entries = min(max(max_entries, 1), MAX_CACHE) if type(max_entries) is int else 1
        self._cache: OrderedDict = OrderedDict()
        self._hw = 0
        self._lock = threading.Lock()

    def _now(self) -> int:
        now = read_clock(self.clock)
        with self._lock:
            if now < self._hw:
                self._cache.clear()  # cached entries cannot be trusted
                raise FlagError("FLG-030")
            self._hw = now
        return now

    def _state(self, key, now):
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None and 0 <= now - hit[1] < self.ttl:
                self._cache.move_to_end(key)
                return hit[0]
        state = self.store.get_flag(key)
        with self._lock:
            self._cache[key] = (state, now)
            self._cache.move_to_end(key)
            while len(self._cache) > self.max_entries:
                self._cache.popitem(last=False)
        return state

    def evaluate(self, ctx, key) -> Decision:
        try:
            return self._evaluate(ctx, key)
        except FlagError as e:
            return Decision(False, {"FLG-030": "error.clock", "FLG-020": "error.context",
                                    "FLG-050": "error.store"}.get(e.code, "error.other"))
        except Exception:  # fail closed on anything unexpected
            return Decision(False, "error.other")

    def is_enabled(self, ctx, key) -> bool:
        return self.evaluate(ctx, key).enabled

    def _evaluate(self, ctx, key) -> Decision:
        now = self._now()
        if not isinstance(ctx, EvalContext):
            raise FlagError("FLG-020")
        try:
            check_live(ctx.claims, now)
        except IdentityError:
            raise FlagError("FLG-020") from None
        d = self.registry.get(key)
        if d is None:
            return OFF_UNKNOWN
        kill = self.store.kill_state()  # never cached: a kill takes effect at once
        if kill.platform:
            return Decision(False, "kill.platform")
        if key in kill.flags:
            return Decision(False, "kill.flag")
        if ctx.tenant_id is not None and ctx.tenant_id in kill.tenants:
            return Decision(False, "kill.tenant")
        s = self._state(key, now)
        if s.global_value is True:
            return Decision(True, "global")
        if ctx.tenant_id is not None:
            if (ctx.tenant_id, ctx.user_id) in s.users:
                return Decision(True, "user")
            if ctx.tenant_id in s.tenants:
                return Decision(True, "tenant")
            if s.percent_bp > 0:
                unit = ctx.tenant_id if d.percent_by == "tenant" else f"{ctx.tenant_id}\x00{ctx.user_id}"
                if bucket(key, unit) < s.percent_bp:
                    return Decision(True, "percent")
        if s.global_value is False:
            return Decision(False, "global")
        return Decision(d.default, "default")
