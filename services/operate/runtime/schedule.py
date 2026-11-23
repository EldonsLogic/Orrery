"""Scheduled agents with budgets (OPR-013, first slice; ADR-0064 Proposed). Deterministic, port-based, no host.

A schedule belongs to one tenant and one owner, both from the verified principal; its agent role must be one of the
owner's own roles, and its tools must be on that role's agent menu (`allowlist.resolve_allowlist`) and pass the
draft-only rule. At run time the owner's roles and the tools are re-checked: losing the role suspends (ALP-026).
A run only sees a `RunContext` (caller, complete, draft): the model-call port sits behind a private wrapper that forces
taint (ALP-019), meters the run from the port's own events and enforces the wall-clock limit. Drafts are re-checked,
copied and marked tainted; nothing executes; no ledger, stock, tax, e-invoice or payroll write is a schedulable tool.
Budget: the run cap is held against the schedule's trailing window before the run and is the `run` layer of the PLT-026
port, which must also carry a `tenant` layer; after the run the hold settles to the metered cost, never below zero and
at the full hold when the cost cannot be attributed. Any error fails closed. Every change, refusal and run is audited.
This is defence in depth inside one process, not a sandbox: agent code is platform code, never model output."""
from __future__ import annotations

import copy
import logging
import math
import re
import secrets
import threading
from dataclasses import dataclass, replace

from . import authority as A
from .allowlist import resolve_allowlist
from .model_call_fake import ModelCallRefused

log = logging.getLogger("schedule")
CODES = frozenset({"invalid_schedule", "not_found", "tenant_mismatch", "owner_mismatch", "role_escalation",
                   "tool_not_allowed", "draft_only", "owner_permission_lost", "budget_exhausted", "overlap",
                   "clock_fault", "port_refused", "run_failed", "run_timeout", "audit_unavailable",
                   "tenant_budget_missing", "schedule_limit", "roles_unavailable", "platform_unavailable",
                   "already_active"})
FIELDS = ("agent_role", "tools", "cadence_s", "start_at", "run_cap", "period_s", "period_cap")
# Platform defaults (ADR-0064 item 4; placeholders per Q-156, UNVERIFIED against real pricing).
MIN_CADENCE_S, MIN_PERIOD_S, MAX_PERIOD_S = 300, 86400, 366 * 86400
MAX_CAP = 50_000_000                    # micro-USD (USD 50): per run, and per owner over the window (>= a day)
MAX_SCHEDULES_PER_OWNER = 10            # active schedules
MAX_RUN_S = 600                         # wall clock per run
MAX_STEP_S = 31 * 86400                 # a larger forward gap is a fresh start (ledger shifted, nothing caught up)
REBASE_AFTER = 3                        # consecutive, mutually consistent backward readings before a rebase
MAX_EPOCH_S = 4_102_444_800             # 2100-01-01: a larger reading is a clock fault
MAX_FAILURES = 3                        # consecutive self-caused failed runs before the schedule is suspended
SELF_CAUSED = frozenset({"run_failed", "tool_not_allowed", "draft_only"})  # platform outages never count
READ_VERBS = frozenset({"get", "list"})  # `export` is egress (Tool API section 11), not a read
# Rigid-zone words, matched as substrings of the lowercased name with separators removed (GLPosting, salesinvoice).
RIGID_SUBSTRINGS = ("invoice", "zatca", "fatoora", "wps", "posting", "tax", "payroll", "salary", "payslip", "ledger",
                    "journal", "zakat", "gosi", "withholding", "bank", "iban")
RIGID_TOKENS = frozenset({"gl", "vat"})  # too short for substring matching (global, private): whole tokens only
HARD_STOP = (KeyboardInterrupt, SystemExit, GeneratorExit)
_SPLIT = re.compile(r"[^a-z0-9]+")
_CAMEL = re.compile(r"([a-z0-9])([A-Z])")
_RUNS: dict = {}                        # opaque run token -> run state; the agent's functions hold only the token


def _tokens(name: str) -> set:
    return {t for t in _SPLIT.split(_CAMEL.sub(r"\1_\2", name).lower()) if t}


def _rigid(name: str) -> bool:
    flat = _SPLIT.sub("", name.lower())
    return any(w in flat for w in RIGID_SUBSTRINGS) or bool(_tokens(name) & RIGID_TOKENS)


def _ctx_functions(token: str):
    """Plain functions whose only captured value is the token string (no bound method, meter or drafts list)."""
    def caller():
        return copy.deepcopy(_RUNS[token]["caller"])

    def complete(request):
        return _RUNS[token]["complete"](request)

    def draft(tool, args):
        return _RUNS[token]["draft"](tool, args)
    return caller, complete, draft


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

    def __post_init__(self):
        if not (isinstance(self.tenant_id, str) and self.tenant_id and isinstance(self.user_id, str) and self.user_id
                and isinstance(self.role_ids, tuple) and all(isinstance(r, str) and r for r in self.role_ids)):
            raise ScheduleRefused("role_escalation", "malformed principal")


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
    period_cap: int       # micro-USD per trailing window, held and settled here
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
    drafts: tuple = ()    # ({tool, args, tainted}) proposals for the human review queue; empty unless completed
    tainted: bool = True  # every scheduled run is tainted (ALP-019)


def _owner(sch) -> tuple:
    return (sch.tenant_id, sch.owner_id)


def _int(v, lo, hi) -> bool:
    return type(v) is int and lo <= v <= hi


class _Meter:
    """Private wrapper around the port: forces taint, attributes committed cost to this run, enforces the deadline."""

    def __init__(self, port, sch: Schedule, run_id: str, clock, deadline):
        self._port, self._sch, self._run_id, self._clock, self._deadline = port, sch, run_id, clock, deadline
        self.cost, self.unattributed, self.calls = 0, False, 0

    def check_deadline(self):
        now = self._clock()
        if not (isinstance(now, (int, float)) and math.isfinite(now) and now <= self._deadline):
            raise ScheduleRefused("run_timeout")

    def complete(self, request: dict) -> dict:
        self.check_deadline()
        self.calls += 1
        before, charged = self._seen(), True
        try:
            return copy.deepcopy(self._port.complete(dict(request, thread_tainted=True)))
        except ModelCallRefused as exc:
            charged = not exc.reservation_released
            raise
        except Exception as exc:                                  # the port failed, not the schedule
            raise ScheduleRefused("platform_unavailable") from exc
        finally:
            self._attribute(before, charged)

    def _seen(self):
        try:
            return len(self._port.events)
        except Exception:
            return None

    def _attribute(self, before, charged: bool) -> None:
        """Only meter.ai_usage events of this tenant and run, new since the call began, with an int cost >= 0."""
        if before is None:
            self.unattributed = True
            return
        try:
            new = [e for e in self._port.events[before:] if isinstance(e, dict) and e.get("type") == "meter.ai_usage"
                   and e.get("tenant_id") == self._sch.tenant_id and e.get("correlation_id") == self._run_id]
            costs = [e["data"]["cost_micro_usd"] for e in new]
        except Exception:
            self.unattributed = True
            return
        if any(not _int(c, 0, MAX_CAP) for c in costs) or (charged and not costs):
            self.unattributed = True      # settle at the full hold (F1, F6)
        self.cost += sum(c for c in costs if _int(c, 0, MAX_CAP))

    def settled(self) -> int:
        return max(self.cost, self._sch.run_cap) if self.unattributed else self.cost


class RunContext:
    """What an agent gets. No port, drafts list or schedule is reachable as an attribute."""
    __slots__ = ("run_id", "caller", "complete", "draft")

    def __init__(self, run_id, caller, complete, draft):
        self.run_id, self.caller, self.complete, self.draft = run_id, caller, complete, draft


class Scheduler:
    """`tool_defs(tenant)` and `roles_of(tenant, user)` read trusted stores; `port_factory(principal, budgets)` returns
    a model-call port bound to that principal with at least a `tenant` and a `run` layer; `clock()` gives epoch
    seconds; `emit(record)` is the audit sink."""

    def __init__(self, tool_defs, roles_of, port_factory, clock, emit):
        self._defs, self._roles_of, self._factory = tool_defs, roles_of, port_factory
        self._clock, self._emit = clock, emit
        self._s: dict = {}
        self._last_slot: dict = {}
        self._ledger: dict = {}       # (tenant, owner) -> [(time, settled micro-USD)], kept across schedules
        self._window: dict = {}       # (tenant, owner) -> longest period_s ever set (never shortened)
        self._backward: list = []     # consecutive backward clock readings (rebase after REBASE_AFTER)
        self._held: dict = {}
        self._fails: dict = {}
        self._inflight: set = set()
        self._last_now = None
        self._lock = threading.RLock()

    # -- schedule changes -------------------------------------------------------------------------------------------
    def create(self, who: Principal, *, tenant_id=None, owner_id=None, **spec) -> Schedule:
        with self._lock:
            try:
                if tenant_id is not None and tenant_id != who.tenant_id:
                    raise ScheduleRefused("tenant_mismatch")
                if owner_id is not None and owner_id != who.user_id:
                    raise ScheduleRefused("owner_mismatch")
                if set(spec) != set(FIELDS):
                    raise ScheduleRefused("invalid_schedule")
                if sum(1 for s in self._s.values() if s.active and s.tenant_id == who.tenant_id
                       and s.owner_id == who.user_id) >= MAX_SCHEDULES_PER_OWNER:
                    raise ScheduleRefused("schedule_limit")
                sch = Schedule(f"sch_{len(self._s) + 1}", who.tenant_id, who.user_id, **spec)
                self._check(who, sch)
            except ScheduleRefused as exc:
                self._refused_change(who, None, exc)
                raise
            self._audit("schedule.created", sch, who)
            self._s[sch.id] = sch
            self._widen(sch)
            return sch

    def update(self, who: Principal, schedule_id: str, **changes) -> Schedule:
        with self._lock:
            try:
                if not changes or not set(changes) <= set(FIELDS):
                    raise ScheduleRefused("invalid_schedule")
                old = self.get(who, schedule_id)
                sch = replace(old, version=old.version + 1, **changes)
                self._check(who, sch)
            except ScheduleRefused as exc:
                self._refused_change(who, schedule_id, exc)
                raise
            changed = sorted(k for k in changes if changes[k] != getattr(old, k))
            self._audit("schedule.updated", sch, who, changed=changed)
            self._s[sch.id] = sch
            self._widen(sch)
            return sch

    def disable(self, who: Principal, schedule_id: str) -> Schedule:
        with self._lock:
            sch = replace(self.get(who, schedule_id), active=False)
            self._audit("schedule.disabled", sch, who)
            self._s[sch.id] = sch
            return sch

    def get(self, who: Principal, schedule_id: str) -> Schedule:
        if not isinstance(who, Principal):
            raise ScheduleRefused("role_escalation", "malformed principal")
        sch = self._s.get(schedule_id)
        if sch is None or sch.tenant_id != who.tenant_id:
            raise ScheduleRefused("not_found")                    # no cross-tenant existence oracle
        if sch.owner_id != who.user_id:
            raise ScheduleRefused("owner_mismatch")
        return sch

    def resume(self, who: Principal, schedule_id: str) -> Schedule:
        """The owner re-activates a suspended or disabled schedule; the owner's spend ledger is kept."""
        with self._lock:
            try:
                old = self.get(who, schedule_id)
                if old.active:
                    raise ScheduleRefused("already_active")       # resume never resets a running schedule's count
                if sum(1 for s in self._s.values() if s.active and s.tenant_id == who.tenant_id
                       and s.owner_id == who.user_id and s.id != old.id) >= MAX_SCHEDULES_PER_OWNER:
                    raise ScheduleRefused("schedule_limit")
                sch = replace(old, active=True, version=old.version + 1)
                self._check(who, sch)
            except ScheduleRefused as exc:
                self._refused_change(who, schedule_id, exc)
                raise
            self._audit("schedule.resumed", sch, who, spent=self._spent(_owner(sch), self._last_now))
            self._s[sch.id] = sch
            self._fails.pop(sch.id, None)
            return sch

    def period_spent(self, who: Principal, schedule_id: str) -> int:
        """The owner's spend over the window: one ledger for all of that owner's schedules."""
        with self._lock:
            return self._spent(_owner(self.get(who, schedule_id)), self._last_now)

    def period_held(self, who: Principal, schedule_id: str) -> int:
        with self._lock:
            return self._owner_held(_owner(self.get(who, schedule_id)))

    def _widen(self, sch: Schedule) -> None:
        self._window[_owner(sch)] = max(self._window.get(_owner(sch), 0), sch.period_s)

    def _owner_held(self, key) -> int:
        return sum(v for sid, v in self._held.items() if _owner(self._s[sid]) == key)

    def _spent(self, key, now) -> int:
        if now is None:
            return 0
        w = self._window.get(key, MAX_PERIOD_S)
        return sum(c for t, c in self._ledger.get(key, ()) if t > now - w)

    def _check(self, who: Principal, s: Schedule) -> None:
        if not isinstance(who, Principal):
            raise ScheduleRefused("role_escalation", "malformed principal")
        if not (isinstance(s.agent_role, str) and _int(s.cadence_s, MIN_CADENCE_S, MAX_PERIOD_S)
                and _int(s.period_s, max(s.cadence_s, MIN_PERIOD_S), MAX_PERIOD_S) and _int(s.start_at, 0, MAX_EPOCH_S)
                and _int(s.period_cap, 1, MAX_CAP) and _int(s.run_cap, 1, s.period_cap)
                and isinstance(s.tools, tuple) and s.tools and len(set(s.tools)) == len(s.tools)
                and all(isinstance(t, str) for t in s.tools)):
            raise ScheduleRefused("invalid_schedule")
        if s.agent_role not in who.role_ids:                     # roles only from the verified principal (a tuple)
            raise ScheduleRefused("role_escalation")
        self._check_tools(s)

    def _check_tools(self, s: Schedule) -> None:
        try:
            defs = self._defs(s.tenant_id)
        except Exception as exc:                                  # the store failed, not the schedule
            raise ScheduleRefused("platform_unavailable") from exc
        allow = resolve_allowlist(defs, (s.agent_role,))
        for name in s.tools:
            if name not in allow.menu:
                raise ScheduleRefused("tool_not_allowed")
            if self._draft_only_refusal(name, allow.defs[name], allow.menu[name].risk_class):
                raise ScheduleRefused("draft_only")

    @staticmethod
    def _draft_only_refusal(name: str, d: dict, risk: str) -> bool:
        domain, _, verb = name.partition(".")
        if A.tool_refusal(name, d) or risk == "R2":
            return True
        if verb == "export":
            return True                                           # egress always needs a human (Tool API section 11)
        if name.endswith(".transition") or verb == "transition" or "transitions" in d:
            return True                                           # a move is chosen per call; never scheduled
        if verb in READ_VERBS and d.get("kind") == "read":
            return False
        if d.get("kind") != "write" or d.get("entity_class") != "plain":
            return True                                           # missing kind or class is never plain
        return _rigid(domain) or A.posting_entity(d, domain)

    def _record(self, type_: str, tenant_id, subject, data: dict) -> None:
        try:
            self._emit({"type": type_, "tenant_id": tenant_id, "subject": subject, "data": data})
        except Exception as exc:                                  # no audit, no change and no run
            raise ScheduleRefused("audit_unavailable") from exc

    def _audit(self, type_: str, sch: Schedule, who: Principal | None, **data) -> None:
        self._record(type_, sch.tenant_id, sch.id, {
            "actor_id": who.user_id if who else "scheduler", "owner_id": sch.owner_id, "on_behalf_of": sch.owner_id,
            "at": self._last_now, "version": sch.version, "agent_role": sch.agent_role, "tools": list(sch.tools),
            "run_cap": sch.run_cap, "period_cap": sch.period_cap, "cadence_s": sch.cadence_s, **data})

    def _refused_change(self, who, schedule_id, exc: ScheduleRefused) -> None:
        if exc.code == "audit_unavailable" or not isinstance(who, Principal):
            return
        try:
            self._record("schedule.change_refused", who.tenant_id, schedule_id,
                         {"actor_id": who.user_id, "code": exc.code, "at": self._last_now})
        except ScheduleRefused:
            log.error("schedule change refusal not audited: %s", exc.code)

    # -- runs -------------------------------------------------------------------------------------------------------
    def tick(self, agent) -> list:
        with self._lock:
            now = self._clock()
            last = self._last_now
            if not (isinstance(now, (int, float)) and not isinstance(now, bool) and math.isfinite(now)
                    and 0 <= now <= MAX_EPOCH_S):
                self._clock_event("scheduler.clock_fault", last)
                raise ScheduleRefused("clock_fault")              # the rejected reading is not stored
            if last is not None and now < last:
                self._backward = (self._backward if self._backward and now >= self._backward[-1] else []) + [now]
                if len(self._backward) < REBASE_AFTER:
                    self._clock_event("scheduler.clock_fault", last)
                    raise ScheduleRefused("clock_fault")
                self._rebase(now, last)                           # the clock is consistently earlier: follow it
                return []
            self._backward = []
            if last is not None and now - last > MAX_STEP_S:      # a long gap: fresh start, spend still counts
                self._clock_event("scheduler.clock_gap", last)
                self._shift_ledger(now - last)
            self._last_now = now
            ids = list(self._s)
        out = []
        for sid in ids:
            try:
                rec = self._run(sid, now, agent)
            except HARD_STOP:
                raise
            except Exception as exc:                               # one schedule never ends the tick for others
                log.error("schedule %s failed: %s", sid, type(exc).__name__)
                rec = RunRecord(f"srun_{sid}_x", sid, -1, "failed",
                                exc.code if isinstance(exc, ScheduleRefused) else "run_failed")
            if rec is not None:
                out.append(rec)
        return out

    def _clock_event(self, type_: str, last) -> None:
        try:
            self._record(type_, None, None, {"last": last})
        except ScheduleRefused:
            log.error("%s not audited", type_)

    def _shift_ledger(self, delta) -> None:
        for key, rows in self._ledger.items():
            self._ledger[key] = [(t + delta, c) for t, c in rows]

    def _rebase(self, now, last) -> None:
        """Follow a clock that is consistently earlier. Spend rows are kept as they are (a row ahead of now keeps
        counting) and slot marks only ever rise, so no slot runs twice and the cap still binds."""
        self._clock_event("scheduler.clock_rebase", last)
        self._backward, self._last_now = [], now
        for sid, sch in self._s.items():
            cur = int((now - sch.start_at) // sch.cadence_s) if now >= sch.start_at else -1
            self._last_slot[sid] = max(self._last_slot.get(sid, -1), cur)

    def _claim(self, sid: str, now):
        """Under the lock: re-read the schedule and claim its slot, or say why not. Returns (sch, slot, refusal)."""
        sch = self._s.get(sid)
        if sch is None or not sch.active or now < sch.start_at:
            return None, -1, None
        slot = int((now - sch.start_at) // sch.cadence_s)
        if slot <= self._last_slot.get(sid, -1):
            return None, -1, None
        if sid in self._inflight:
            return sch, slot, "overlap"
        self._last_slot[sid] = slot
        try:
            roles = self._roles_of(sch.tenant_id, sch.owner_id)
            roles = tuple(roles) if isinstance(roles, tuple) else None
        except Exception:
            roles = None
        if roles is None:
            return sch, slot, "roles_unavailable"
        if sch.agent_role not in roles:
            return sch, slot, "owner_permission_lost"
        if self._spent(_owner(sch), now) + self._owner_held(_owner(sch)) + sch.run_cap > sch.period_cap:
            return sch, slot, "budget_exhausted"
        self._inflight.add(sid)
        self._held[sid] = sch.run_cap
        return sch, slot, None

    def _suspend(self, sid: str, reason: str) -> None:
        cur = self._s[sid]
        try:
            self._audit("schedule.suspended", cur, None, reason=reason)
        finally:                                                  # suspend even if the audit fails
            self._s[sid] = replace(self._s[sid], active=False)

    def _run(self, sid: str, now, agent):
        with self._lock:
            sch, slot, why = self._claim(sid, now)
            if sch is None:
                return None
            run_id = f"srun_{sid}_{slot}"
            if why is not None:
                if why == "owner_permission_lost":
                    self._suspend(sid, why)                       # suspended even if its audit fails
                kind = "agent.budget_exceeded" if why == "budget_exhausted" else "agent.run_refused"
                self._audit(kind, sch, None, run_id=run_id, slot=slot, code=why, scope="period",
                            spent=self._spent(_owner(sch), now))
                return RunRecord(run_id, sid, slot, "refused", why)
        meter, drafts, cost = None, [], 0
        try:
            self._check_tools(sch)
            principal = {"service": "operate", "tenant_id": sch.tenant_id, "actor_kind": "agent",
                         "actor_id": f"agent_{sid}", "role_ids": [sch.agent_role], "on_behalf_of": sch.owner_id,
                         "agent_id": f"agent_{sid}", "run_id": run_id, "thread_id": run_id,
                         "tool_grant": list(sch.tools)}
            try:
                port = self._factory(copy.deepcopy(principal), {"run": sch.run_cap})
            except Exception as exc:
                raise ScheduleRefused("platform_unavailable") from exc
            if getattr(port, "principal", {}).get("tenant_id") != sch.tenant_id:
                raise ScheduleRefused("tenant_mismatch")
            if "tenant" not in tuple(getattr(port, "layers", ())) or "run" not in tuple(getattr(port, "layers", ())):
                raise ScheduleRefused("tenant_budget_missing")
            start = self._clock()                                 # the deadline counts from this run's claim
            if not (isinstance(start, (int, float)) and not isinstance(start, bool) and math.isfinite(start)):
                raise ScheduleRefused("clock_fault")
            meter = _Meter(port, sch, run_id, self._clock, max(start, now) + MAX_RUN_S)
            self._audit("agent.run_started", sch, None, run_id=run_id, slot=slot)
            caller = {k: principal[k] for k in ("tenant_id", "actor_kind", "actor_id", "role_ids", "on_behalf_of",
                                                "agent_id", "run_id", "thread_id")} | {"correlation_id": run_id}

            def draft(tool, args):
                meter.check_deadline()
                if not isinstance(tool, str) or tool not in sch.tools:
                    raise ScheduleRefused("tool_not_allowed")
                drafts.append({"tool": tool, "args": copy.deepcopy(args), "tainted": True})
            token = secrets.token_hex(16)
            _RUNS[token] = {"caller": caller, "complete": meter.complete, "draft": draft}
            try:
                agent(RunContext(run_id, *_ctx_functions(token)))
            finally:
                _RUNS.pop(token, None)
            meter.check_deadline()
            self._check_tools(sch)                                # re-check every draft at the end, too
            if any(not isinstance(d, dict) or d.get("tool") not in sch.tools for d in drafts):
                raise ScheduleRefused("tool_not_allowed")
            drafts = [{"tool": d["tool"], "args": copy.deepcopy(d.get("args")), "tainted": True} for d in drafts]
            cost = meter.settled()
            for d in drafts:
                self._audit("agent.tool_proposed", sch, None, run_id=run_id, slot=slot, tool=d["tool"], tainted=True)
            self._audit("agent.run_completed", sch, None, run_id=run_id, slot=slot, cost=cost, drafts=len(drafts),
                        overrun=cost > sch.run_cap, tainted=True)
            with self._lock:
                self._fails.pop(sid, None)
            return RunRecord(run_id, sid, slot, "completed", cost=cost, drafts=tuple(drafts))
        except BaseException as exc:                              # fail closed: drafts discarded, spend settled
            code = exc.code if isinstance(exc, ScheduleRefused) else (
                "port_refused" if isinstance(exc, ModelCallRefused) else "run_failed")
            detail = exc.code if isinstance(exc, ModelCallRefused) else ""
            cost = meter.settled() if meter is not None else 0
            try:
                self._audit("agent.run_failed", sch, None, run_id=run_id, slot=slot, code=code, detail=detail,
                            cost=cost)
            except ScheduleRefused:
                log.error("run %s failed and its failure was not audited", run_id)
                code, detail = "audit_unavailable", code
            with self._lock:
                if code in SELF_CAUSED:                           # outages, timeouts and refusals never count
                    self._fails[sid] = self._fails.get(sid, 0) + 1
                if self._fails.get(sid, 0) >= MAX_FAILURES and self._s[sid].active:
                    try:
                        self._suspend(sid, "repeated_failures")
                    except ScheduleRefused:
                        log.error("schedule %s suspended without an audit record", sid)
            if isinstance(exc, HARD_STOP):
                raise
            return RunRecord(run_id, sid, slot, "failed", code, detail, cost)
        finally:
            if meter is not None and cost == 0:
                cost = meter.settled()
            with self._lock:
                self._ledger.setdefault(_owner(sch), []).append((now, max(0, cost)))  # never lowers the total
                self._held.pop(sid, None)
                self._inflight.discard(sid)
