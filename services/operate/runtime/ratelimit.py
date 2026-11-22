"""Rate limits and budget guard for chat turns and tool calls (SEC-009, chat side).
Design: docs/security/chat-rate-limits.md.


Keys are (tenant, user) from the verified principal only, never from a request body or the model. Every check fails
closed: a missing identity, a kind with no rule or a store error refuses. Refusals mirror the model-call contract's
refusal shape (`code`, `reason`, `retryable`; contracts/model-call.md section 5) with the Tool API code `rate_limited`.
The default numbers are proposed defaults (UNVERIFIED, not measured); hosts override them with their own rules.
State is in process memory; a multi-instance host needs a shared counter store (see the design note)."""
from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass

from .models import ToolResponse
from .ports import BudgetStop

RATE_CODE = "rate_limited"  # contracts/tool-api.md section 7; the model-call contract has no rate code


@dataclass(frozen=True)
class RateRule:
    kind: str        # "turn" (one chat message) or "tool" (one dispatched Tool API call)
    scope: str       # "user" (tenant + user) or "tenant"
    window_s: float
    limit: int


# Proposed defaults (design note section 3). Not facts; tune from PLT-025 metering once real traffic exists.
DEFAULT_RULES = (
    RateRule("turn", "user", 60, 20), RateRule("turn", "user", 3600, 300), RateRule("turn", "tenant", 60, 200),
    RateRule("tool", "user", 60, 60), RateRule("tool", "tenant", 60, 600),
)


class RateLimited(Exception):
    """`reason`: user_limit | tenant_limit (retryable) or identity_missing | policy_missing | store_error (not)."""

    def __init__(self, reason: str, retry_after_s: int = 0):
        super().__init__(f"{RATE_CODE}:{reason}")
        self.code, self.reason, self.retry_after_s = RATE_CODE, reason, retry_after_s
        self.retryable = reason in ("user_limit", "tenant_limit")

    def as_dict(self) -> dict:
        return {"kind": "refusal", "code": self.code, "reason": self.reason, "retryable": self.retryable,
                "retry_after_s": self.retry_after_s}


class RateLimiter:
    """Sliding-window counters. `clock` is injected (seconds, monotonic) so tests are deterministic."""

    def __init__(self, clock, rules=DEFAULT_RULES):
        self.clock, self.rules = clock, tuple(rules)
        self._hits: dict = {}
        self._lock = threading.Lock()

    def admit(self, kind: str, tenant_id, user_id) -> None:
        """Record one `kind` event for (tenant, user) or raise `RateLimited`. A refused event is not recorded."""
        if not (isinstance(tenant_id, str) and tenant_id and isinstance(user_id, str) and user_id):
            raise RateLimited("identity_missing")
        rules = [r for r in self.rules if r.kind == kind]
        if not rules or any(r.scope not in ("user", "tenant") or r.limit < 1 or r.window_s <= 0 for r in rules):
            raise RateLimited("policy_missing")
        try:
            with self._lock:
                now = float(self.clock())
                keyed = [(r, (kind, r.scope, r.window_s, tenant_id, user_id if r.scope == "user" else ""))
                         for r in rules]
                for r, key in keyed:  # check every rule before recording any, so a refusal costs nothing
                    q = self._hits.setdefault(key, deque())
                    while q and q[0] <= now - r.window_s:
                        q.popleft()
                    if len(q) >= r.limit:
                        raise RateLimited(f"{r.scope}_limit", max(1, int(-(-(q[0] + r.window_s - now) // 1))))
                for _, key in keyed:
                    self._hits[key].append(now)
        except RateLimited:
            raise
        except Exception as exc:  # a broken clock or store refuses, never admits
            raise RateLimited("store_error") from exc


class RateLimitedTools:
    """ToolPort decorator: each dispatched call (proposals included) counts against the caller's `tool` rules.
    Identity comes from the `ToolRequest` the loop built from the verified caller. Over the limit the call is not
    sent and the loop sees the Tool API error `rate_limited`."""

    def __init__(self, inner, limiter: RateLimiter):
        self.inner, self.limiter = inner, limiter
        self.supports_propose = getattr(inner, "supports_propose", False)

    def call(self, request):
        try:
            self.limiter.admit("tool", request.tenant_id, request.user_id)
        except RateLimited:
            return ToolResponse(status="error", error={"code": RATE_CODE})
        return self.inner.call(request)


class BudgetGuard:
    """Decorator over a model-call contract port (`complete(request dict) -> reply dict`, PLT-026). The port's
    reserve-then-commit check is the budget control: a `budget_refused` refusal (any reason, including
    `meter_unavailable` and `policy_missing`) becomes `BudgetStop`, so the agent loop stops the run with
    `budget_exceeded`. Every other refusal is re-raised (the loop maps it to `internal_error`); a result that is
    neither a reply nor a refusal fails closed."""

    def __init__(self, port):
        self.port = port

    def complete(self, request: dict) -> dict:
        try:
            out = self.port.complete(request)
        except Exception as exc:
            if getattr(exc, "code", None) == "budget_refused":
                raise BudgetStop(str(getattr(exc, "reason", "") or "exceeded")[:64]) from exc
            raise
        kind = out.get("kind") if isinstance(out, dict) else None
        if kind == "refusal" and out.get("code") == "budget_refused":
            raise BudgetStop(str(out.get("reason") or "exceeded")[:64])
        if kind != "reply":
            raise RuntimeError("model-call port returned no reply")
        return out
