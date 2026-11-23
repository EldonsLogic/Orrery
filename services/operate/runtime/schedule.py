"""Scheduled agents with budgets (OPR-013, first slice; ADR-0064 Proposed). Deterministic, port-based, no host.

A schedule belongs to one tenant and one owner, both from the verified principal; its agent role must be one of the
owner's own roles, and its tools must be on that role's agent menu (`allowlist.resolve_allowlist`) and pass the
draft-only rule. At run time the owner's roles are re-read: losing the role suspends the schedule (ALP-026).
A run is always tainted (ALP-019), acts on behalf of the owner, and only drafts: `ctx.draft` records a proposal for
a human, nothing executes, and no ledger, stock, tax, e-invoice or payroll write is ever allowed as a tool.
Budget: the run cap is held against the per-period cap before the run and becomes the `run` layer of the PLT-026
model-call port, which reserves and meters every call; after the run the hold is settled to the metered cost.
Any error fails closed (no drafts delivered, metered spend still counted). Every change and run is audited."""
from __future__ import annotations

import math
import threading
from dataclasses import dataclass, replace

from . import authority as A
from .allowlist import resolve_allowlist
from .model_call_fake import ModelCallRefused

CODES = frozenset({"invalid_schedule", "not_found", "tenant_mismatch", "owner_mismatch", "role_escalation",
                   "tool_not_allowed", "draft_only", "owner_permission_lost", "budget_exhausted", "overlap",
                   "clock_fault", "port_refused", "run_failed", "audit_unavailable"})
FIELDS = ("agent_role", "tools", "cadence_s", "start_at", "run_cap", "period_s", "period_cap")
MIN_CADENCE_S, MAX_PERIOD_S, MAX_CAP = 300, 366 * 86400, 10**12
READ_VERBS = frozenset({"get", "list", "export"})


class ScheduleRefused(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code, self.detail = (code if code in CODES else "run_failed"), detail


@dataclass(frozen=True)
class Principal:
    """The verified session (never a request body): tenant, user and that user's current role ids."""
    tenant_id: str
    user_id: str
    role_ids: tuple


@dataclass(frozen=True)
class Schedule:
    id: str
    tenant_id: str
    owner_id: str
    agent_role: str
    tools: tuple
    cadence_s: int
    start_at: int
    run_cap: int          # micro-USD, the PLT-026 `run` layer
    period_s: int
    period_cap: int       # micro-USD per period window, held and settled here
    version: int = 1
    active: bool = True


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    schedule_id: str
    slot: int
    outcome: str          # completed | refused | failed
    code: str = ""
    detail: str = ""
    cost: int = 0
    drafts: tuple = ()    # (tool, args) proposals for the human review queue; empty unless completed


def _int(v, lo, hi) -> bool:
    return type(v) is int and lo <= v <= hi


class RunContext:
    def __init__(self, sch: Schedule, run_id: str, port):
        self.schedule, self.run_id, self.port, self.calls, self.drafts = sch, run_id, port, 0, []

    def caller(self) -> dict:
        p = self.port.principal
        return {k: p[k] for k in ("tenant_id", "actor_kind", "actor_id", "role_ids", "on_behalf_of", "agent_id",
                                  "run_id", "thread_id")} | {"correlation_id": self.run_id}

    def complete(self, request: dict) -> dict:
        self.calls += 1
        return self.port.complete(dict(request, thread_tainted=True))       # scheduled runs start tainted

    def draft(self, tool: str, args: dict) -> None:
        if tool not in self.schedule.tools:
            raise ScheduleRefused("tool_not_allowed")
        self.drafts.append((tool, args))


class Scheduler:
    """`tool_defs(tenant)` and `roles_of(tenant, user)` read trusted stores; `port_factory(principal, budgets)` returns
    a model-call port bound to that principal; `clock()` gives epoch seconds; `emit(record)` is the audit sink."""

    def __init__(self, tool_defs, roles_of, port_factory, clock, emit):
        self._defs, self._roles_of, self._factory = tool_defs, roles_of, port_factory
        self._clock, self._emit = clock, emit
        self._s: dict = {}
        self._last_slot: dict = {}
        self._spent: dict = {}        # (schedule id, period index) -> settled micro-USD
        self._held: dict = {}         # schedule id -> open hold
        self._inflight: set = set()
        self._last_now = -math.inf
        self._lock = threading.RLock()

    # -- schedule changes -------------------------------------------------------------------------------------------
    def create(self, who: Principal, *, tenant_id=None, owner_id=None, **spec) -> Schedule:
        if tenant_id is not None and tenant_id != who.tenant_id:
            raise ScheduleRefused("tenant_mismatch")
        if owner_id is not None and owner_id != who.user_id:
            raise ScheduleRefused("owner_mismatch")
        if set(spec) != set(FIELDS):
            raise ScheduleRefused("invalid_schedule")
        with self._lock:
            sch = Schedule(f"sch_{len(self._s) + 1}", who.tenant_id, who.user_id, **spec)
            self._check(who, sch)
            self._audit("schedule.created", sch, who)
            self._s[sch.id] = sch
            return sch

    def update(self, who: Principal, schedule_id: str, **changes) -> Schedule:
        if not changes or not set(changes) <= set(FIELDS):
            raise ScheduleRefused("invalid_schedule")
        with self._lock:
            old = self.get(who, schedule_id)
            sch = replace(old, version=old.version + 1, **changes)
            self._check(who, sch)
            changed = sorted(k for k in changes if changes[k] != getattr(old, k))
            self._audit("schedule.updated", sch, who, changed=changed)
            self._s[sch.id] = sch
            return sch

    def disable(self, who: Principal, schedule_id: str) -> Schedule:
        with self._lock:
            sch = replace(self.get(who, schedule_id), active=False)
            self._audit("schedule.disabled", sch, who)
            self._s[sch.id] = sch
            return sch

    def get(self, who: Principal, schedule_id: str) -> Schedule:
        sch = self._s.get(schedule_id)
        if sch is None or sch.tenant_id != who.tenant_id:
            raise ScheduleRefused("not_found")                    # no cross-tenant existence oracle
        if sch.owner_id != who.user_id:
            raise ScheduleRefused("owner_mismatch")
        return sch

    def period_spent(self, schedule_id: str) -> int:
        sch = self._s[schedule_id]
        return self._spent.get((sch.id, self._period(sch, self._last_now)), 0)

    def period_held(self, schedule_id: str) -> int:
        return self._held.get(schedule_id, 0)

    def _check(self, who: Principal, s: Schedule) -> None:
        if not (isinstance(s.agent_role, str) and _int(s.cadence_s, MIN_CADENCE_S, MAX_PERIOD_S)
                and _int(s.period_s, s.cadence_s, MAX_PERIOD_S) and _int(s.start_at, 0, 10**11)
                and _int(s.period_cap, 1, MAX_CAP) and _int(s.run_cap, 1, s.period_cap)
                and isinstance(s.tools, tuple) and s.tools and len(set(s.tools)) == len(s.tools)
                and all(isinstance(t, str) for t in s.tools)):
            raise ScheduleRefused("invalid_schedule")
        if s.agent_role not in who.role_ids:                     # roles only from the verified principal
            raise ScheduleRefused("role_escalation")
        self._check_tools(s)

    def _check_tools(self, s: Schedule) -> None:
        allow = resolve_allowlist(self._defs(s.tenant_id), (s.agent_role,))
        for name in s.tools:
            if name not in allow.menu:
                raise ScheduleRefused("tool_not_allowed")
            d, (domain, _, verb) = allow.defs[name], name.partition(".")
            if (A.tool_refusal(name, d) or allow.menu[name].risk_class == "R2"
                    or (verb not in READ_VERBS and A.posting_entity(d, domain))):
                raise ScheduleRefused("draft_only")              # no posting write, even as a draft

    def _audit(self, type_: str, sch: Schedule, who: Principal | None, **data) -> None:
        rec = {"type": type_, "tenant_id": sch.tenant_id, "subject": sch.id,
               "data": {"actor_id": who.user_id if who else "scheduler", "version": sch.version,
                        "agent_role": sch.agent_role, "tools": list(sch.tools), "run_cap": sch.run_cap,
                        "period_cap": sch.period_cap, "cadence_s": sch.cadence_s, **data}}
        try:
            self._emit(rec)
        except Exception as exc:                                  # no audit, no change and no run
            raise ScheduleRefused("audit_unavailable") from exc

    # -- runs -------------------------------------------------------------------------------------------------------
    def _period(self, s: Schedule, now) -> int:
        return int((now - s.start_at) // s.period_s)

    def tick(self, agent) -> list:
        now = self._clock()
        if not (isinstance(now, (int, float)) and not isinstance(now, bool) and math.isfinite(now)
                and now >= self._last_now):
            raise ScheduleRefused("clock_fault")                  # a broken or backwards clock runs nothing
        self._last_now = now
        out = []
        for sch in list(self._s.values()):
            slot = int((now - sch.start_at) // sch.cadence_s) if now >= sch.start_at else -1
            if sch.active and slot >= 0 and slot > self._last_slot.get(sch.id, -1):
                out.append(self._run(sch, slot, now, agent))
        return out

    def _run(self, sch: Schedule, slot: int, now, agent) -> RunRecord:
        run_id = f"srun_{sch.id}_{slot}"
        refuse = lambda code: RunRecord(run_id, sch.id, slot, "refused", code)  # noqa: E731
        with self._lock:
            if sch.id in self._inflight:
                return refuse("overlap")
            self._last_slot[sch.id] = slot
            if sch.agent_role not in tuple(self._roles_of(sch.tenant_id, sch.owner_id) or ()):
                self._s[sch.id] = replace(sch, active=False)
                self._audit("schedule.suspended", sch, None, reason="owner_permission_lost")
                return refuse("owner_permission_lost")
            key = (sch.id, self._period(sch, now))
            if self._spent.get(key, 0) + sch.run_cap > sch.period_cap:
                self._audit("agent.budget_exceeded", sch, None, run_id=run_id, scope="period",
                            spent=self._spent.get(key, 0))
                return refuse("budget_exhausted")
            self._inflight.add(sch.id)
            self._held[sch.id] = sch.run_cap
        port, cost = None, 0
        try:
            self._check_tools(sch)
            principal = {"service": "operate", "tenant_id": sch.tenant_id, "actor_kind": "agent",
                         "actor_id": f"agent_{sch.id}", "role_ids": [sch.agent_role], "on_behalf_of": sch.owner_id,
                         "agent_id": f"agent_{sch.id}", "run_id": run_id, "thread_id": run_id,
                         "tool_grant": list(sch.tools)}
            port = self._factory(principal, {"run": sch.run_cap})
            if getattr(port, "principal", {}).get("tenant_id") != sch.tenant_id:
                raise ScheduleRefused("tenant_mismatch")
            self._audit("agent.run_started", sch, None, run_id=run_id)
            ctx = RunContext(sch, run_id, port)
            agent(ctx)
            cost = self._metered(port, sch.run_cap)
            for tool, _ in ctx.drafts:
                self._audit("agent.tool_proposed", sch, None, run_id=run_id, tool=tool)
            self._audit("agent.run_completed", sch, None, run_id=run_id, cost=cost, drafts=len(ctx.drafts),
                        overrun=cost > sch.run_cap)
            return RunRecord(run_id, sch.id, slot, "completed", cost=cost, drafts=tuple(ctx.drafts))
        except Exception as exc:                                  # fail closed: drafts discarded
            code = exc.code if isinstance(exc, ScheduleRefused) else (
                "port_refused" if isinstance(exc, ModelCallRefused) else "run_failed")
            detail = exc.code if isinstance(exc, ModelCallRefused) else ""
            cost = self._metered(port, sch.run_cap)
            try:
                self._audit("agent.run_failed", sch, None, run_id=run_id, code=code, detail=detail, cost=cost)
            except ScheduleRefused:
                pass                                              # already failing; the record below still says so
            return RunRecord(run_id, sch.id, slot, "failed", code, detail, cost)
        finally:
            with self._lock:
                self._spent[key] = self._spent.get(key, 0) + cost   # settle: hold -> metered spend
                self._held.pop(sch.id, None)
                self._inflight.discard(sch.id)

    @staticmethod
    def _metered(port, hold: int) -> int:
        """Committed spend from the port's meter.ai_usage events (contract section 8); unreadable counts the hold."""
        try:
            return sum(e["data"]["cost_micro_usd"] for e in (port.events if port is not None else ()))
        except Exception:
            return hold
