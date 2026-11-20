"""Flag evaluation. Never raises: unknown flag, bad context, bad clock, store
error or any other failure gives OFF, whatever the default says."""

import hashlib
import threading
from collections import OrderedDict
from dataclasses import dataclass

from .context import EvalContext, derive
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


MAX_FORWARD = 86_400  # a larger forward jump must be seen twice before it is believed


class FlagEvaluator:
    def __init__(self, registry, store, clock, *, ttl=15, max_entries=256, revoked=None):
        """`revoked(claims) -> bool` is an optional port (session or membership
        revocation); when given, a revoked or failing check gives OFF."""
        self.registry, self.store, self.clock, self.revoked = registry, store, clock, revoked
        self.ttl = min(max(ttl, 0), MAX_TTL) if type(ttl) is int else 0
        self.max_entries = min(max(max_entries, 1), MAX_CACHE) if type(max_entries) is int else 1
        self._cache: OrderedDict = OrderedDict()
        self._hw = 0
        self._cand = None
        self._lock = threading.Lock()

    def _read(self) -> int:
        """Per-call clock reading. Backwards: error and cache flush. A far-future
        reading is refused for that call only and never moves the high-water mark;
        it is believed only if the next reading agrees with it."""
        now = read_clock(self.clock)
        with self._lock:
            if now < self._hw:
                self._cache.clear()  # cached entries cannot be trusted
                raise FlagError("FLG-030")
            if self._hw and now - self._hw > MAX_FORWARD:
                c = self._cand
                self._cand = now
                if c is None or not c <= now <= c + MAX_FORWARD:
                    raise FlagError("FLG-030")
            else:
                self._cand = None
        return now

    def _accept(self, now: int) -> None:
        with self._lock:
            self._hw = max(self._hw, now)

    def _state(self, key, now):
        v = self.store.version()  # read first: an entry is never newer than its tag
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None and hit[1] == v and 0 <= now - hit[2] < self.ttl:
                self._cache.move_to_end(key)
                return hit[0]
        state = self.store.get_flag(key)
        with self._lock:
            cur = self._cache.get(key)
            if cur is None or cur[1] <= v:  # a slow reader never overwrites newer state
                self._cache[key] = (state, v, now)
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
        now = self._read()
        if type(ctx) is not EvalContext:
            raise FlagError("FLG-020")
        tenant, user = derive(ctx.claims, now)  # only the verified claims count
        self._accept(now)
        if self.revoked is not None:
            try:
                if self.revoked(ctx.claims) is not False:
                    return Decision(False, "error.revoked")
            except Exception:
                return Decision(False, "error.revoked")
        d = self.registry.get(key)
        if d is None:
            return OFF_UNKNOWN
        kill = self.store.kill_state()  # never cached: a kill takes effect at once
        if kill.platform:
            return Decision(False, "kill.platform")
        if key in kill.flags:
            return Decision(False, "kill.flag")
        if tenant is not None and tenant in kill.tenants:
            return Decision(False, "kill.tenant")
        s = self._state(key, now)
        if s.global_value is True:
            return Decision(True, "global")
        if tenant is not None:
            if (tenant, user) in s.users:
                return Decision(True, "user")
            if tenant in s.tenants:
                return Decision(True, "tenant")
            if s.percent_bp > 0:
                unit = tenant if d.percent_by == "tenant" else f"{tenant}\x00{user}"
                if bucket(key, unit) < s.percent_bp:
                    return Decision(True, "percent")
        if s.global_value is False:
            return Decision(False, "global")
        return Decision(d.default, "default")
