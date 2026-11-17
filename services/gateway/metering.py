"""Per-tenant and per-call AI token & cost metering for services/gateway (PLT-025).

Implements deterministic integer micro-USD cost attribution, builder session cost
tracking, fail-closed tenant/session budget enforcement, and Contract 4
`meter.ai_usage` event emission.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
import threading
from typing import Any, Callable, Mapping

from .pricing import (
    CostBreakdown,
    PriceBook,
    compute_call_cost,
    require_non_negative_int,
)
from .ulid import UlidGenerator, is_valid_ulid

TENANT_ID_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")
VALID_ACTOR_KINDS = frozenset({"user", "agent", "system", "support"})
VALID_PURPOSES = frozenset({"chat", "agent", "build", "simulation"})
_SPOOF_TENANT_KEYS = frozenset({"tenantid", "tenantids", "tenant"})


class GatewayMeteringError(Exception):
    """Base error for fail-closed gateway metering failures."""


class TenantContextError(GatewayMeteringError):
    """Raised when authenticated tenant/actor context is missing, invalid, or spoofed."""


class BudgetExceededError(GatewayMeteringError):
    """Raised when a tenant or session AI budget cap would be exceeded."""

    def __init__(
        self,
        message: str,
        *,
        scope: str,
        tenant_id: str,
        limit_kind: str,
        limit_value: int,
        current_value: int,
        projected_value: int,
    ) -> None:
        super().__init__(message)
        self.scope = scope
        self.tenant_id = tenant_id
        self.limit_kind = limit_kind
        self.limit_value = limit_value
        self.current_value = current_value
        self.projected_value = projected_value


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _norm_key(key: str) -> str:
    return re.sub(r"[^a-z]", "", key.lower())


def validate_tenant_id(tenant_id: object) -> str:
    if not isinstance(tenant_id, str) or not TENANT_ID_RE.fullmatch(tenant_id):
        raise TenantContextError(f"Invalid tenant_id {tenant_id!r}; expected ^[A-Za-z0-9_]{{1,64}}$")
    if tenant_id == "platform":
        raise TenantContextError("Tenant metering cannot use reserved scope 'platform'")
    return tenant_id


def _require_short_str(name: str, value: object, *, max_len: int = 256) -> str:
    if not isinstance(value, str) or not value or len(value) > max_len:
        raise ValueError(f"{name} must be a non-empty string up to {max_len} chars")
    return value


@dataclass(frozen=True)
class GatewayContext:
    """Authenticated caller identity stamped by the platform gateway.

    `tenant_id` and `actor` originate only from verified session/auth state, never from
    untrusted request payloads.
    """

    tenant_id: str
    actor_kind: str
    actor_id: str
    correlation_id: str
    role_ids: tuple[str, ...] = ()
    on_behalf_of: str | None = None
    session_id: str | None = None
    component: str | None = None
    blueprint_revision: int | None = None

    def __post_init__(self) -> None:
        validate_tenant_id(self.tenant_id)
        if self.actor_kind not in VALID_ACTOR_KINDS:
            raise TenantContextError(f"Invalid actor_kind {self.actor_kind!r}")
        _require_short_str("actor_id", self.actor_id)
        _require_short_str("correlation_id", self.correlation_id)
        if len(self.role_ids) > 50:
            raise ValueError("role_ids cannot contain more than 50 entries")
        for role_id in self.role_ids:
            _require_short_str("role_id", role_id)
        if self.on_behalf_of is not None:
            _require_short_str("on_behalf_of", self.on_behalf_of)
        if self.session_id is not None:
            _require_short_str("session_id", self.session_id)
        if self.component is not None:
            _require_short_str("component", self.component)
        if self.blueprint_revision is not None:
            require_non_negative_int("blueprint_revision", self.blueprint_revision)

    @property
    def effective_session_id(self) -> str:
        return self.session_id if self.session_id is not None else self.correlation_id


@dataclass(frozen=True)
class CallUsage:
    """Measured token & trace attributes for a single gateway model invocation."""

    model_id: str
    tier: str
    purpose: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0
    agent_id: str | None = None
    prompt_version: str | None = None
    tool: str | None = None
    audit_id: str | None = None
    latency_ms: int | None = None
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        _require_short_str("model_id", self.model_id)
        _require_short_str("tier", self.tier)
        if self.purpose not in VALID_PURPOSES:
            raise ValueError(f"purpose must be one of {sorted(VALID_PURPOSES)}, got {self.purpose!r}")
        inp = require_non_negative_int("input_tokens", self.input_tokens)
        require_non_negative_int("output_tokens", self.output_tokens)
        cached = require_non_negative_int("cached_tokens", self.cached_tokens)
        if cached > inp:
            raise ValueError(f"cached_tokens ({cached}) cannot exceed input_tokens ({inp})")
        if self.agent_id is not None:
            _require_short_str("agent_id", self.agent_id)
        if self.prompt_version is not None:
            _require_short_str("prompt_version", self.prompt_version)
        if self.tool is not None:
            _require_short_str("tool", self.tool)
        if self.audit_id is not None:
            _require_short_str("audit_id", self.audit_id)
        if self.latency_ms is not None:
            require_non_negative_int("latency_ms", self.latency_ms)
        if self.metadata is not None:
            for key in self.metadata:
                if not isinstance(key, str):
                    raise ValueError("metadata keys must be strings")
                if _norm_key(key) in _SPOOF_TENANT_KEYS:
                    raise TenantContextError(
                        f"Call metadata must not specify tenant key {key!r}; use GatewayContext"
                    )


@dataclass(frozen=True)
class BudgetPolicy:
    """Fail-closed token/cost cap for a tenant or session."""

    max_cost_micro_usd: int | None = None
    max_total_tokens: int | None = None
    alert_threshold_pct: int = 80

    def __post_init__(self) -> None:
        if self.max_cost_micro_usd is not None:
            require_non_negative_int("max_cost_micro_usd", self.max_cost_micro_usd)
        if self.max_total_tokens is not None:
            require_non_negative_int("max_total_tokens", self.max_total_tokens)
        if isinstance(self.alert_threshold_pct, bool) or not isinstance(self.alert_threshold_pct, int) or not (
            1 <= self.alert_threshold_pct <= 100
        ):
            raise ValueError("alert_threshold_pct must be an integer between 1 and 100")


@dataclass(frozen=True)
class BudgetAlert:
    """Threshold crossing notification emitted when spend or tokens pass alert_threshold_pct."""

    scope: str
    tenant_id: str
    session_id: str | None
    metric: str
    current_value: int
    limit_value: int
    threshold_pct: int
    triggered_at: str


@dataclass(frozen=True)
class MeteredCallRecord:
    """Immutable per-call metering record."""

    call_id: str
    event_id: str
    occurred_at: str
    tenant_id: str
    session_id: str
    correlation_id: str
    purpose: str
    tier: str
    model_id: str
    agent_id: str | None
    input_tokens: int
    uncached_input_tokens: int
    cached_tokens: int
    output_tokens: int
    total_tokens: int
    cost_micro_usd: int
    pico_usd: int
    rate_verified: bool
    latency_ms: int | None


@dataclass(frozen=True)
class UsageTotals:
    """Aggregated token and cost counters."""

    call_count: int = 0
    input_tokens: int = 0
    uncached_input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_micro_usd: int = 0


@dataclass(frozen=True)
class TenantUsageSummary:
    """Full tenant usage breakdown across calls, purposes, tiers, and models."""

    tenant_id: str
    totals: UsageTotals
    by_purpose: dict[str, UsageTotals]
    by_tier: dict[str, UsageTotals]
    by_model: dict[str, UsageTotals]
    sessions: dict[str, UsageTotals]
    budget: BudgetPolicy | None
    alerts: tuple[BudgetAlert, ...]


@dataclass(frozen=True)
class SessionUsageSummary:
    """Usage breakdown for one session (for example one Blueprint build session)."""

    tenant_id: str
    session_id: str
    totals: UsageTotals
    by_purpose: dict[str, UsageTotals]
    by_tier: dict[str, UsageTotals]
    by_model: dict[str, UsageTotals]
    budget: BudgetPolicy | None


def build_ai_usage_event(
    ctx: GatewayContext,
    usage: CallUsage,
    cost: CostBreakdown,
    *,
    event_id: str,
    occurred_at: datetime,
) -> dict[str, Any]:
    """Build an unstamped Contract 4 `meter.ai_usage` event conforming to envelope + data.meter schema."""
    if not is_valid_ulid(event_id):
        raise ValueError(f"Invalid ULID event_id: {event_id!r}")

    source: dict[str, Any] = {"service": "gateway"}
    if ctx.component is not None:
        source["component"] = ctx.component
    if ctx.blueprint_revision is not None:
        source["blueprint_revision"] = ctx.blueprint_revision

    trace: dict[str, Any] = {"model_id": usage.model_id}
    if usage.prompt_version is not None:
        trace["prompt_version"] = usage.prompt_version
    if usage.tool is not None:
        trace["tool"] = usage.tool
    if usage.audit_id is not None:
        trace["audit_id"] = usage.audit_id

    data: dict[str, Any] = {
        "model_id": usage.model_id,
        "tier": usage.tier,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cached_tokens": usage.cached_tokens,
        "cost_micro_usd": cost.cost_micro_usd,
        "purpose": usage.purpose,
        "agent_id": usage.agent_id,
    }

    ts = _iso_z(occurred_at)
    return {
        "event_id": event_id,
        "type": "meter.ai_usage",
        "schema_version": 1,
        "occurred_at": ts,
        "recorded_at": ts,
        "tenant_id": ctx.tenant_id,
        "actor": {
            "kind": ctx.actor_kind,
            "id": ctx.actor_id,
            "role_ids": list(ctx.role_ids),
            "on_behalf_of": ctx.on_behalf_of,
        },
        "source": source,
        "correlation_id": ctx.correlation_id,
        "causation_id": None,
        "subject": None,
        "data": data,
        "data_class": "operational",
        "trace": trace,
    }


def _accumulate(bucket: dict[str, list[int]], key: str, cost: CostBreakdown, usage: CallUsage) -> None:
    vals = bucket.setdefault(key, [0, 0, 0, 0, 0, 0, 0])
    vals[0] += 1
    vals[1] += usage.input_tokens
    vals[2] += cost.uncached_input_tokens
    vals[3] += usage.cached_tokens
    vals[4] += usage.output_tokens
    vals[5] += cost.total_tokens
    vals[6] += cost.cost_micro_usd


def _freeze_totals(vals: list[int]) -> UsageTotals:
    return UsageTotals(
        call_count=vals[0],
        input_tokens=vals[1],
        uncached_input_tokens=vals[2],
        cached_tokens=vals[3],
        output_tokens=vals[4],
        total_tokens=vals[5],
        cost_micro_usd=vals[6],
    )


@dataclass
class _ScopeState:
    totals: list[int] = field(default_factory=lambda: [0, 0, 0, 0, 0, 0, 0])
    by_purpose: dict[str, list[int]] = field(default_factory=dict)
    by_tier: dict[str, list[int]] = field(default_factory=dict)
    by_model: dict[str, list[int]] = field(default_factory=dict)

    def add(self, cost: CostBreakdown, usage: CallUsage) -> None:
        self.totals[0] += 1
        self.totals[1] += usage.input_tokens
        self.totals[2] += cost.uncached_input_tokens
        self.totals[3] += usage.cached_tokens
        self.totals[4] += usage.output_tokens
        self.totals[5] += cost.total_tokens
        self.totals[6] += cost.cost_micro_usd
        _accumulate(self.by_purpose, usage.purpose, cost, usage)
        _accumulate(self.by_tier, usage.tier, cost, usage)
        _accumulate(self.by_model, usage.model_id, cost, usage)


@dataclass
class _TenantLedger:
    aggregate: _ScopeState = field(default_factory=_ScopeState)
    sessions: dict[str, _ScopeState] = field(default_factory=dict)
    calls: list[MeteredCallRecord] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    alerts: list[BudgetAlert] = field(default_factory=list)
    alerted_keys: set[tuple[str, str | None, str]] = field(default_factory=set)


class GatewayMeter:
    """Thread-safe per-tenant & per-call token and micro-USD cost meter."""

    def __init__(
        self,
        *,
        price_book: PriceBook | None = None,
        default_budget: BudgetPolicy | None = None,
        event_sink: Callable[[dict[str, Any]], Any] | None = None,
        clock: Callable[[], datetime] = _utc_now,
        ulids: UlidGenerator | None = None,
    ) -> None:
        self._price_book = price_book or PriceBook()
        self._default_budget = default_budget
        self._event_sink = event_sink
        self._clock = clock
        self._ulids = ulids or UlidGenerator()
        self._lock = threading.Lock()
        self._tenant_budgets: dict[str, BudgetPolicy] = {}
        self._session_budgets: dict[tuple[str, str], BudgetPolicy] = {}
        self._ledgers: dict[str, _TenantLedger] = {}

    @property
    def price_book(self) -> PriceBook:
        return self._price_book

    def set_tenant_budget(self, tenant_id: str, policy: BudgetPolicy) -> None:
        tid = validate_tenant_id(tenant_id)
        with self._lock:
            self._tenant_budgets[tid] = policy

    def set_session_budget(self, tenant_id: str, session_id: str, policy: BudgetPolicy) -> None:
        tid = validate_tenant_id(tenant_id)
        sid = _require_short_str("session_id", session_id)
        with self._lock:
            self._session_budgets[(tid, sid)] = policy

    def _effective_tenant_budget(self, tenant_id: str) -> BudgetPolicy | None:
        return self._tenant_budgets.get(tenant_id, self._default_budget)

    def _check_policy(
        self,
        *,
        scope: str,
        tenant_id: str,
        policy: BudgetPolicy | None,
        current_totals: list[int],
        add_cost: int,
        add_tokens: int,
    ) -> None:
        if policy is None:
            return
        cur_tokens = current_totals[5]
        cur_cost = current_totals[6]
        if policy.max_cost_micro_usd is not None:
            proj_cost = cur_cost + add_cost
            if proj_cost > policy.max_cost_micro_usd or (
                add_cost == 0 and policy.max_cost_micro_usd == 0 and add_tokens > 0
            ):
                raise BudgetExceededError(
                    f"{scope} cost budget exceeded for tenant {tenant_id}: "
                    f"{proj_cost} > {policy.max_cost_micro_usd} micro_usd",
                    scope=scope,
                    tenant_id=tenant_id,
                    limit_kind="cost_micro_usd",
                    limit_value=policy.max_cost_micro_usd,
                    current_value=cur_cost,
                    projected_value=proj_cost,
                )
        if policy.max_total_tokens is not None:
            proj_tokens = cur_tokens + add_tokens
            if proj_tokens > policy.max_total_tokens:
                raise BudgetExceededError(
                    f"{scope} token budget exceeded for tenant {tenant_id}: "
                    f"{proj_tokens} > {policy.max_total_tokens} tokens",
                    scope=scope,
                    tenant_id=tenant_id,
                    limit_kind="total_tokens",
                    limit_value=policy.max_total_tokens,
                    current_value=cur_tokens,
                    projected_value=proj_tokens,
                )

    def _maybe_record_alert(
        self,
        ledger: _TenantLedger,
        *,
        scope: str,
        tenant_id: str,
        session_id: str | None,
        policy: BudgetPolicy | None,
        state: _ScopeState,
        occurred_at: str,
    ) -> None:
        if policy is None:
            return
        checks: list[tuple[str, int, int | None]] = [
            ("cost_micro_usd", state.totals[6], policy.max_cost_micro_usd),
            ("total_tokens", state.totals[5], policy.max_total_tokens),
        ]
        for metric, current, limit in checks:
            if limit is None or limit <= 0:
                continue
            key = (scope, session_id, metric)
            if key in ledger.alerted_keys:
                continue
            if current * 100 >= limit * policy.alert_threshold_pct:
                ledger.alerted_keys.add(key)
                ledger.alerts.append(
                    BudgetAlert(
                        scope=scope,
                        tenant_id=tenant_id,
                        session_id=session_id,
                        metric=metric,
                        current_value=current,
                        limit_value=limit,
                        threshold_pct=policy.alert_threshold_pct,
                        triggered_at=occurred_at,
                    )
                )

    def precheck_budget(
        self,
        ctx: GatewayContext,
        *,
        estimated_cost_micro_usd: int = 0,
        estimated_tokens: int = 0,
        tier: str | None = None,
    ) -> None:
        """Fail-closed check before dispatching a model request.

        Deterministic `tier == "code"` calls with zero estimated cost/tokens remain
        available even when the tenant's AI budget is exhausted.
        """
        est_cost = require_non_negative_int("estimated_cost_micro_usd", estimated_cost_micro_usd)
        est_tokens = require_non_negative_int("estimated_tokens", estimated_tokens)
        if tier == "code" and est_cost == 0 and est_tokens == 0:
            return

        with self._lock:
            ledger = self._ledgers.get(ctx.tenant_id)
            t_totals = ledger.aggregate.totals if ledger else [0, 0, 0, 0, 0, 0, 0]
            t_policy = self._effective_tenant_budget(ctx.tenant_id)
            self._check_policy(
                scope="tenant",
                tenant_id=ctx.tenant_id,
                policy=t_policy,
                current_totals=t_totals,
                add_cost=est_cost,
                add_tokens=est_tokens,
            )
            # Also block if tenant is already at/above cap when estimate is 0 for a metered tier
            if est_cost == 0 and est_tokens == 0 and t_policy is not None:
                if t_policy.max_cost_micro_usd is not None and t_totals[6] >= t_policy.max_cost_micro_usd:
                    raise BudgetExceededError(
                        f"tenant cost budget exhausted for {ctx.tenant_id}",
                        scope="tenant",
                        tenant_id=ctx.tenant_id,
                        limit_kind="cost_micro_usd",
                        limit_value=t_policy.max_cost_micro_usd,
                        current_value=t_totals[6],
                        projected_value=t_totals[6],
                    )
                if t_policy.max_total_tokens is not None and t_totals[5] >= t_policy.max_total_tokens:
                    raise BudgetExceededError(
                        f"tenant token budget exhausted for {ctx.tenant_id}",
                        scope="tenant",
                        tenant_id=ctx.tenant_id,
                        limit_kind="total_tokens",
                        limit_value=t_policy.max_total_tokens,
                        current_value=t_totals[5],
                        projected_value=t_totals[5],
                    )

            sid = ctx.effective_session_id
            s_policy = self._session_budgets.get((ctx.tenant_id, sid))
            if s_policy is not None:
                s_state = ledger.sessions.get(sid) if ledger else None
                s_totals = s_state.totals if s_state else [0, 0, 0, 0, 0, 0, 0]
                self._check_policy(
                    scope="session",
                    tenant_id=ctx.tenant_id,
                    policy=s_policy,
                    current_totals=s_totals,
                    add_cost=est_cost,
                    add_tokens=est_tokens,
                )
                if est_cost == 0 and est_tokens == 0:
                    if s_policy.max_cost_micro_usd is not None and s_totals[6] >= s_policy.max_cost_micro_usd:
                        raise BudgetExceededError(
                            f"session cost budget exhausted for {ctx.tenant_id}/{sid}",
                            scope="session",
                            tenant_id=ctx.tenant_id,
                            limit_kind="cost_micro_usd",
                            limit_value=s_policy.max_cost_micro_usd,
                            current_value=s_totals[6],
                            projected_value=s_totals[6],
                        )
                    if s_policy.max_total_tokens is not None and s_totals[5] >= s_policy.max_total_tokens:
                        raise BudgetExceededError(
                            f"session token budget exhausted for {ctx.tenant_id}/{sid}",
                            scope="session",
                            tenant_id=ctx.tenant_id,
                            limit_kind="total_tokens",
                            limit_value=s_policy.max_total_tokens,
                            current_value=s_totals[5],
                            projected_value=s_totals[5],
                        )

    def record_call(
        self,
        ctx: GatewayContext,
        usage: CallUsage,
        *,
        call_id: str | None = None,
        event_id: str | None = None,
        occurred_at: datetime | None = None,
        enforce_budget: bool = True,
    ) -> MeteredCallRecord:
        """Compute cost, enforce tenant/session budgets, emit `meter.ai_usage`, and store record."""
        rate = self._price_book.resolve(usage.model_id, usage.tier)
        cost = compute_call_cost(
            rate,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cached_tokens=usage.cached_tokens,
        )
        eid = event_id or self._ulids.generate()
        cid = call_id or eid
        _require_short_str("call_id", cid)
        ts_dt = occurred_at or self._clock()
        event = build_ai_usage_event(ctx, usage, cost, event_id=eid, occurred_at=ts_dt)

        sid = ctx.effective_session_id
        record = MeteredCallRecord(
            call_id=cid,
            event_id=eid,
            occurred_at=event["occurred_at"],
            tenant_id=ctx.tenant_id,
            session_id=sid,
            correlation_id=ctx.correlation_id,
            purpose=usage.purpose,
            tier=usage.tier,
            model_id=usage.model_id,
            agent_id=usage.agent_id,
            input_tokens=usage.input_tokens,
            uncached_input_tokens=cost.uncached_input_tokens,
            cached_tokens=usage.cached_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=cost.total_tokens,
            cost_micro_usd=cost.cost_micro_usd,
            pico_usd=cost.pico_usd,
            rate_verified=rate.verified,
            latency_ms=usage.latency_ms,
        )

        with self._lock:
            ledger = self._ledgers.setdefault(ctx.tenant_id, _TenantLedger())
            t_policy = self._effective_tenant_budget(ctx.tenant_id)
            s_policy = self._session_budgets.get((ctx.tenant_id, sid))
            s_state = ledger.sessions.setdefault(sid, _ScopeState())

            if enforce_budget and usage.tier != "code":
                self._check_policy(
                    scope="tenant",
                    tenant_id=ctx.tenant_id,
                    policy=t_policy,
                    current_totals=ledger.aggregate.totals,
                    add_cost=cost.cost_micro_usd,
                    add_tokens=cost.total_tokens,
                )
                self._check_policy(
                    scope="session",
                    tenant_id=ctx.tenant_id,
                    policy=s_policy,
                    current_totals=s_state.totals,
                    add_cost=cost.cost_micro_usd,
                    add_tokens=cost.total_tokens,
                )

            if self._event_sink is not None:
                self._event_sink(copy.deepcopy(event))

            ledger.aggregate.add(cost, usage)
            s_state.add(cost, usage)
            ledger.calls.append(record)
            ledger.events.append(event)

            self._maybe_record_alert(
                ledger,
                scope="tenant",
                tenant_id=ctx.tenant_id,
                session_id=None,
                policy=t_policy,
                state=ledger.aggregate,
                occurred_at=event["occurred_at"],
            )
            self._maybe_record_alert(
                ledger,
                scope="session",
                tenant_id=ctx.tenant_id,
                session_id=sid,
                policy=s_policy,
                state=s_state,
                occurred_at=event["occurred_at"],
            )

        return record

    def tenant_summary(self, tenant_id: str) -> TenantUsageSummary:
        tid = validate_tenant_id(tenant_id)
        with self._lock:
            ledger = self._ledgers.get(tid)
            policy = self._effective_tenant_budget(tid)
            if ledger is None:
                return TenantUsageSummary(
                    tenant_id=tid,
                    totals=UsageTotals(),
                    by_purpose={},
                    by_tier={},
                    by_model={},
                    sessions={},
                    budget=policy,
                    alerts=(),
                )
            return TenantUsageSummary(
                tenant_id=tid,
                totals=_freeze_totals(ledger.aggregate.totals),
                by_purpose={k: _freeze_totals(v) for k, v in ledger.aggregate.by_purpose.items()},
                by_tier={k: _freeze_totals(v) for k, v in ledger.aggregate.by_tier.items()},
                by_model={k: _freeze_totals(v) for k, v in ledger.aggregate.by_model.items()},
                sessions={k: _freeze_totals(v.totals) for k, v in ledger.sessions.items()},
                budget=policy,
                alerts=tuple(ledger.alerts),
            )

    def session_summary(self, tenant_id: str, session_id: str) -> SessionUsageSummary:
        tid = validate_tenant_id(tenant_id)
        sid = _require_short_str("session_id", session_id)
        with self._lock:
            ledger = self._ledgers.get(tid)
            s_policy = self._session_budgets.get((tid, sid))
            s_state = ledger.sessions.get(sid) if ledger else None
            if s_state is None:
                return SessionUsageSummary(
                    tenant_id=tid,
                    session_id=sid,
                    totals=UsageTotals(),
                    by_purpose={},
                    by_tier={},
                    by_model={},
                    budget=s_policy,
                )
            return SessionUsageSummary(
                tenant_id=tid,
                session_id=sid,
                totals=_freeze_totals(s_state.totals),
                by_purpose={k: _freeze_totals(v) for k, v in s_state.by_purpose.items()},
                by_tier={k: _freeze_totals(v) for k, v in s_state.by_tier.items()},
                by_model={k: _freeze_totals(v) for k, v in s_state.by_model.items()},
                budget=s_policy,
            )

    def calls_for_tenant(self, tenant_id: str) -> tuple[MeteredCallRecord, ...]:
        tid = validate_tenant_id(tenant_id)
        with self._lock:
            ledger = self._ledgers.get(tid)
            return tuple(ledger.calls) if ledger else ()

    def calls_for_session(self, tenant_id: str, session_id: str) -> tuple[MeteredCallRecord, ...]:
        tid = validate_tenant_id(tenant_id)
        sid = _require_short_str("session_id", session_id)
        with self._lock:
            ledger = self._ledgers.get(tid)
            if not ledger:
                return ()
            return tuple(c for c in ledger.calls if c.session_id == sid)

    def events_for_tenant(self, tenant_id: str) -> list[dict[str, Any]]:
        tid = validate_tenant_id(tenant_id)
        with self._lock:
            ledger = self._ledgers.get(tid)
            return copy.deepcopy(ledger.events) if ledger else []
