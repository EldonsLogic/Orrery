"""Rate limits and budget guard for chat turns, new sessions and tool calls (SEC-009, chat side).
Design: docs/security/chat-rate-limits.md.

Keys are (tenant, user) from the verified principal only, never from a request body, a session id or the model.
Every check fails closed: a missing identity, a kind with no valid rule, an invalid rule set, a clock value that is
not a finite number in range, or any store error refuses. Over a limit is the Tool API code `rate_limited`
(retryable, with `retry_after_s`); the model-call contract has no rate code. The default numbers are proposed
defaults (accepted as starting values, Q-561; not measured). State is in process memory. A call is atomic: every rule is checked first, then each key's new window is built as a copy and all are published together under the counter lock by one `dict.update` of finished deques, so a failure while building leaves every live counter as it was and no rollback exists to fail (a refused or errored event costs nothing); a multi-instance host uses the shared cache with a per-server fallback on cache outage, every limit divided by the number of servers (Q-562, not built yet)."""
from __future__ import annotations

import logging
import math
import threading
from collections import deque
from dataclasses import dataclass

from .models import ToolResponse
from .ports import BudgetStop

log = logging.getLogger("ratelimit")
RATE_CODE = "rate_limited"     # contracts/tool-api.md section 7
RETRYABLE_REASONS = frozenset({"user_limit", "tenant_limit"})
SCOPES = ("user", "tenant")
MAX_CLOCK_S = 1e10             # a monotonic clock in seconds stays far below this; larger values are a clock fault
MIN_WINDOW_S, MAX_WINDOW_S = 1, 7 * 86400
MAX_LIMIT = 1_000_000
SWEEP_EVERY = 1024             # admits between sweeps of expired keys
MAX_SKEW_S = 5                 # a backwards step up to this is clamped; a larger one is a clock reset (rebase)
MAX_QUIET_KEYS = 10_000        # refusal-log suppression entries kept before the table is cleared
BUDGET_REASONS = frozenset({"exceeded", "policy_missing", "meter_unavailable", "layer_unbound"})  # model-call 5


@dataclass(frozen=True)
class RateRule:
    kind: str        # "turn" (chat message), "session" (new chat session) or "tool" (dispatched Tool API call)
    scope: str       # "user" (tenant + user) or "tenant"
    window_s: float
    limit: int


# Proposed defaults (design note section 3). Not facts; tune from PLT-025 metering once real traffic exists.
DEFAULT_RULES = (
    RateRule("turn", "user", 60, 20), RateRule("turn", "user", 3600, 300), RateRule("turn", "tenant", 60, 200),
    RateRule("session", "user", 3600, 30),
    RateRule("tool", "user", 60, 60), RateRule("tool", "tenant", 60, 600),
)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _valid_rules(rules) -> bool:
    try:
        seen = set()
        for r in rules:
            if not (isinstance(r, RateRule) and isinstance(r.kind, str) and r.kind and r.scope in SCOPES
                    and type(r.limit) is int and 1 <= r.limit <= MAX_LIMIT
                    and _num(r.window_s) and MIN_WINDOW_S <= r.window_s <= MAX_WINDOW_S):
                return False
            key = (r.kind, r.scope, float(r.window_s))
            if key in seen:  # duplicates would share one counter and count every event twice
                return False
            seen.add(key)
        return bool(seen)
    except Exception:
        return False


class RateLimited(Exception):
    """`reason`: user_limit | tenant_limit (retryable, `retry_after_s` > 0) or identity_missing | policy_missing |
    store_error (not retryable: a fault or a misconfiguration, never the user's doing)."""

    def __init__(self, reason: str, retry_after_s: int = 0):
        super().__init__(f"{RATE_CODE}:{reason}")
        self.code, self.reason, self.retry_after_s = RATE_CODE, reason, retry_after_s
        self.retryable = reason in RETRYABLE_REASONS
        self.first = True  # False for a repeat refusal of the same key and reason: callers do not log or audit it


class RateLimiter:
    """Sliding-window counters. `clock` is injected and must be monotonic seconds (`time.monotonic` in a host,
    `TickClock` in tests). A small backwards step (up to `MAX_SKEW_S`) is clamped to the last good value; a larger
    one is a clock reset, so hits stamped after the new value are moved to it (counts kept, windows restart) and one
    spurious high reading cannot freeze the limiter. A non-finite, negative or huge value refuses with `store_error`
    and records nothing, so the limiter recovers when the clock does. Refusals are logged once per key and reason
    until that key is admitted again; the repeats are counted and reported then."""

    def __init__(self, clock, rules=DEFAULT_RULES, sweep_every: int = SWEEP_EVERY):
        try:
            self.rules = tuple(rules)
        except Exception:
            self.rules = ()
        sweep_ok = type(sweep_every) is int and sweep_every >= 1
        self.clock, self._valid = clock, _valid_rules(self.rules) and sweep_ok
        self.sweep_every = sweep_every if sweep_ok else SWEEP_EVERY
        self._hits: dict = {}
        self._quiet: dict = {}   # (kind, tenant, user) -> {reason: repeats not logged}
        self._last = 0.0
        self._calls = 0
        self._lock = threading.Lock()

    def admit(self, kind: str, tenant_id, user_id) -> None:
        """Record one `kind` event for (tenant, user) or raise `RateLimited` (logged). A refused event is not
        recorded."""
        ident = (str(kind)[:32], str(tenant_id)[:128], str(user_id)[:128])
        try:
            self._admit(kind, tenant_id, user_id)
        except RateLimited as e:
            with self._lock:
                seen = self._quiet.get(ident)
                if seen is not None and e.reason in seen:
                    seen[e.reason] += 1
                    e.first = False
                else:
                    if len(self._quiet) >= MAX_QUIET_KEYS:
                        self._quiet.clear()
                    self._quiet.setdefault(ident, {})[e.reason] = 0
            if e.first:
                log.warning("rate refusal kind=%s tenant=%s user=%s reason=%s retry_after_s=%d", *ident, e.reason,
                            e.retry_after_s)
            raise
        with self._lock:
            seen = self._quiet.pop(ident, None)
        if seen and any(seen.values()):
            log.warning("rate refusals repeated kind=%s tenant=%s user=%s %s", *ident,
                        " ".join(f"{k}={v}" for k, v in sorted(seen.items())))

    def _admit(self, kind, tenant_id, user_id) -> None:
        if not (isinstance(tenant_id, str) and tenant_id.strip() and isinstance(user_id, str) and user_id.strip()):
            raise RateLimited("identity_missing")
        rules = [r for r in self.rules if r.kind == kind] if self._valid and isinstance(kind, str) else []
        if not rules:
            raise RateLimited("policy_missing")
        try:
            with self._lock:
                now = self.clock()
                if not (_num(now) and 0 <= now <= MAX_CLOCK_S):
                    raise RateLimited("store_error")
                now = float(now)
                if now < self._last - MAX_SKEW_S:
                    self._rebase(now)
                elif now < self._last:
                    now = self._last
                self._last = now
                keyed = [(r, (kind, r.scope, float(r.window_s), tenant_id, user_id if r.scope == "user" else ""))
                         for r in rules]
                for r, key in keyed:  # check every rule before recording any, so a refusal costs nothing
                    q = self._hits.setdefault(key, deque())
                    while q and q[0] <= now - r.window_s:
                        q.popleft()
                    if len(q) >= r.limit:
                        raise RateLimited(f"{r.scope}_limit", max(1, math.ceil(q[0] + r.window_s - now)))
                staged = {}  # key -> new window, built off to the side
                for _, key in keyed:
                    staged[key] = self._stage(self._hits[key], now)
                self._hits.update(staged)  # publish: one dict.update of finished windows, nothing to roll back
                self._calls += 1
                if self._calls % self.sweep_every == 0:
                    self._sweep(now)
        except RateLimited:
            raise
        except Exception as exc:  # a broken clock or store refuses, never admits
            raise RateLimited("store_error") from exc

    @staticmethod
    def _stage(q: deque, now: float) -> deque:
        """The key's window with this hit added, as a new deque (the live one is not touched)."""
        new = deque(q)
        new.append(now)
        return new

    def _rebase(self, now: float) -> None:
        """Clock reset: hits stamped after `now` are moved to `now` (the caller holds the lock)."""
        for key, q in self._hits.items():
            if q and q[-1] > now:
                self._hits[key] = deque(min(t, now) for t in q)

    def _sweep(self, now: float) -> None:
        """Drop keys whose newest hit is outside their window (bounded memory; the caller holds the lock)."""
        for key in [k for k, q in self._hits.items() if not q or q[-1] <= now - k[2]]:
            del self._hits[key]


class RateLimitedTools:
    """ToolPort decorator: each dispatched call (proposals included) counts against the caller's `tool` rules.
    Identity comes from the `ToolRequest` the loop built from the verified caller. Over the limit, or on any limiter
    fault, the call is not sent and the loop sees the Tool API error `rate_limited` (with `retry_after_s` when
    retryable), which stops the run."""

    def __init__(self, inner, limiter: RateLimiter):
        self.inner, self.limiter = inner, limiter
        self.supports_propose = getattr(inner, "supports_propose", False)

    def call(self, request):
        try:
            self.limiter.admit("tool", request.tenant_id, request.user_id)
        except RateLimited as e:
            err = {"code": RATE_CODE, "retryable": e.retryable}
            if e.retryable:
                err["retry_after_s"] = e.retry_after_s
            return ToolResponse(status="error", error=err)
        return self.inner.call(request)


class BudgetGuard:
    """Decorator over a model-call contract port (`complete(request dict) -> reply dict`, PLT-026). The port's
    reserve-then-commit check is the budget control: a `budget_refused` refusal, raised or returned, becomes
    `BudgetStop(reason)` with the reason mapped to the contract's closed set (anything else is `unknown`), so the
    agent loop stops the run with `budget_exceeded`. Any other raised refusal is re-raised, and any other returned
    result that is not a reply raises `RuntimeError`; the loop maps both to `internal_error`."""

    def __init__(self, port):
        self.port = port

    @staticmethod
    def _stop(reason) -> BudgetStop:
        return BudgetStop(reason if isinstance(reason, str) and reason in BUDGET_REASONS else "unknown")

    def complete(self, request: dict) -> dict:
        try:
            out = self.port.complete(request)
        except Exception as exc:
            if getattr(exc, "code", None) == "budget_refused":
                raise self._stop(getattr(exc, "reason", None)) from exc
            raise
        kind = out.get("kind") if isinstance(out, dict) else None
        if kind == "refusal" and out.get("code") == "budget_refused":
            raise self._stop(out.get("reason"))
        if kind != "reply":
            raise RuntimeError("model-call port returned no reply")
        return out
