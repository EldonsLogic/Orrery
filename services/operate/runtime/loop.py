"""The agent loop: a deterministic turn state machine around an injected model.

    plan (build request) -> call model -> parse tool calls -> classify (allow-list, risk) -> execute through the
    Tool API port only -> observe (result becomes L3 data) -> repeat, until an answer, an interrupt, a cap or a cancel.

All variation comes from the model port; ids and time come from injected helpers, so one script gives one trace."""
from __future__ import annotations

import logging
from typing import Iterator, Optional

from .allowlist import Allowlist
from .errors import firewall_exception, map_tool_error
from .models import (Caller, Limits, ModelReply, ModelRequest, RunEvent, RunResult, Span, Step, ToolCall, ToolRequest,
                     Usage)
from .ports import BudgetStop, CancelToken, Clock, EventSink, Ids, ModelPort, ToolPort, TraceStore
from .untrusted import canonical, redact_args, sha, wrap_data

log = logging.getLogger("agent_runtime")
MAX_CALLS_PER_REPLY = 8
MAX_DATA_ITEMS = 16


class _Stop(Exception):
    def __init__(self, status, reason, code=None, kind=None):
        super().__init__(reason)
        self.status, self.reason, self.code, self.kind = status, reason, code, kind


class AgentLoop:
    def __init__(self, *, model: ModelPort, tools: ToolPort, allow: Allowlist, limits: Limits, clock: Clock, ids: Ids,
                 traces: TraceStore, events: Optional[EventSink] = None, cancel: Optional[CancelToken] = None,
                 emit_run_events: bool = True):
        self.model, self.tools, self.allow, self.lim = model, tools, allow, limits
        self.clock, self.ids, self.traces, self.events = clock, ids, traces, events
        self.cancel = cancel or CancelToken()
        self.emit_run_events = emit_run_events

    # ---- helpers -------------------------------------------------------------------------------------------
    def _ms(self) -> int:
        return int(round((self.clock() - self._t0) * 1000))

    def _event(self, type_: str, data: dict) -> None:
        if self.events is None or (type_ in ("agent.run_started", "agent.run_completed", "agent.run_failed")
                                   and not self.emit_run_events):
            return
        trace = {"model_id": str(getattr(self.model, "model_id", "unknown"))[:256],
                 "prompt_version": str(getattr(self.model, "prompt_version", "unversioned"))[:256]}
        try:
            self.events.emit(self.c.tenant_id, self.c.user_id, type_, {"run_id": self.run_id, **data}, trace)
        except Exception:
            log.exception("runtime event sink failed")

    def _span(self, kind, started, outcome, **kw) -> Span:
        sp = Span(span_id=self.ids.new_id("span"), run_id=self.run_id, tenant_id=self.c.tenant_id, step=self.steps,
                  kind=kind, started_ms=started, ended_ms=self._ms(), outcome=outcome, **kw)
        try:
            self.traces.append(sp)
        except Exception:
            log.exception("trace store append failed")
        return sp

    def _check_caps(self, projecting: bool) -> None:
        lim = self.lim
        if self.cancel.cancelled:
            raise _Stop("cancelled", "cancelled", "cancelled")
        if self.clock() - self._t0 >= lim.max_wall_s:
            raise _Stop("stopped", "wall_clock", "budget_exceeded", "wall_clock")
        if projecting:
            if self.steps >= lim.max_steps:
                raise _Stop("stopped", "max_steps", "budget_exceeded", "steps")
            if self.tokens + lim.est_input_tokens + lim.est_output_tokens > lim.max_total_tokens:
                raise _Stop("stopped", "max_tokens", "budget_exceeded", "tokens")
        elif self.tokens > lim.max_total_tokens:
            raise _Stop("stopped", "max_tokens", "budget_exceeded", "tokens")
        if self.cost >= lim.max_cost_micro_usd and (projecting or self.cost > lim.max_cost_micro_usd):
            raise _Stop("stopped", "max_cost", "budget_exceeded", "cost")

    # ---- run -----------------------------------------------------------------------------------------------
    def run(self, **kw) -> RunResult:
        result = None
        for ev in self.stream(**kw):
            if ev.kind == "done":
                result = ev.result
        return result

    def stream(self, *, caller: Caller, run_id: str, user_text: str, instructions: str = "",
               locale: str = "en") -> Iterator[RunEvent]:
        self.c, self.run_id, self._t0 = caller, run_id, self.clock()
        self.steps = self.dispatched = self.tokens = self.cost = self.refusals = 0
        self.tainted, self.usage_in, self.usage_out, self.usage_cached = False, 0, 0, 0
        history, data, needs, approvals, seen = [], [], [], [], {}
        answer, run_started = "", self._ms()
        self._event("agent.run_started", {})
        try:
            if not caller.tenant_id or not caller.user_id or not caller.role_ids:
                raise _Stop("failed", "error", "permission_denied")  # no roles: fail closed
            limit_calls = min(self.lim.max_tool_calls, self.allow.max_tool_calls or self.lim.max_tool_calls)
            while True:
                self._check_caps(True)
                req = ModelRequest(instructions=instructions, user_turn=user_text, steps=tuple(history),
                                   data=tuple(data), tools=self.allow.specs(), tainted=self.tainted, locale=locale)
                m0 = self._ms()
                try:
                    reply: ModelReply = self.model.complete(req)
                except BudgetStop as e:
                    self._span("model", m0, "budget_stop", error_code="budget_exceeded")
                    raise _Stop("stopped", "budget", "budget_exceeded", e.kind)
                except Exception as e:
                    err = firewall_exception(e)
                    self._span("model", m0, "error", error_code=err["code"])
                    raise _Stop("failed", "error", "internal_error")
                self.steps += 1
                u = reply.usage
                self.tokens += u.input_tokens + u.output_tokens
                self.cost += u.cost_micro_usd
                self.usage_in, self.usage_out, self.usage_cached = (self.usage_in + u.input_tokens,
                                                                    self.usage_out + u.output_tokens,
                                                                    self.usage_cached + u.cached_tokens)
                self._span("model", m0, "ok", input_tokens=u.input_tokens, output_tokens=u.output_tokens,
                           cached_tokens=u.cached_tokens, cost_micro_usd=u.cost_micro_usd, tainted=self.tainted)
                yield RunEvent("usage", {"usage": u})
                if reply.text:
                    yield RunEvent("text", {"text": reply.text})
                calls = tuple(c for c in reply.tool_calls if isinstance(c, ToolCall))
                if not calls:
                    answer = reply.text
                    break
                self._check_caps(False)  # over a token or cost cap: do not act on this reply
                observed = []
                interrupted = False
                for i, call in enumerate(calls):
                    if interrupted or i >= MAX_CALLS_PER_REPLY:
                        self._span("tool", self._ms(), "skipped", tool=str(call.name)[:96])
                        continue
                    if self.cancel.cancelled:
                        raise _Stop("cancelled", "cancelled", "cancelled")
                    self._check_caps(False)
                    obs, item, pend = yield from self._one(call, limit_calls, seen)
                    observed.append((call, obs))
                    if item:
                        data.append(item)
                        del data[:-MAX_DATA_ITEMS]
                    if pend:
                        approvals.append(pend)
                        interrupted = True
                    if self._needs.get(call.id):
                        needs.append(call.name)
                    if self._stop is not None:
                        raise self._stop
                    if self.refusals >= self.lim.max_refusals:
                        raise _Stop("stopped", "refusals", "permission_denied")
                history.append(Step(reply.text, tuple(observed)))
                if interrupted:
                    raise _Stop("interrupted", "interrupt")
            result = self._finish("completed", "none", answer, None, approvals, needs, run_started)
        except _Stop as s:
            result = self._finish(s.status, s.reason, answer, s.code, approvals, needs, run_started, s.kind)
        except GeneratorExit:
            raise
        yield RunEvent("done", {}, result)

    def _finish(self, status, reason, answer, code, approvals, needs, started, kind=None) -> RunResult:
        if kind:
            self._event("agent.budget_exceeded", {"budget_kind": kind})
        usage = Usage(self.usage_in, self.usage_out, self.usage_cached, self.cost)
        res = RunResult(status=status, stop_reason=reason, answer=answer, error_code=code,
                        approval_ids=tuple(approvals), needs_approval=tuple(dict.fromkeys(needs)), steps=self.steps,
                        tool_calls=self.dispatched, tainted=self.tainted, usage=usage)
        self._span("run", 0, status if status != "stopped" else f"stopped:{reason}", error_code=code,
                   input_tokens=self.usage_in, output_tokens=self.usage_out, cached_tokens=self.usage_cached,
                   cost_micro_usd=self.cost, tainted=self.tainted,
                   approval_id=approvals[0] if approvals else None)
        if status in ("completed", "interrupted"):
            self._event("agent.run_completed", {})
        else:
            self._event("agent.run_failed", {"error_code": code or "internal_error"})
        return res

    # ---- one tool call -------------------------------------------------------------------------------------
    _needs: dict = {}
    _stop = None

    def _one(self, call: ToolCall, limit_calls: int, seen: dict):
        """Returns (observation text, DataItem or None, approval id or None). Yields tool events."""
        self._stop, t0 = None, self._ms()
        self._needs = {}
        name = str(call.name)[:96]
        args = call.arguments if isinstance(call.arguments, dict) else None
        ok_size = args is not None and len(canonical(args).encode()) <= self.lim.max_args_bytes
        red = redact_args(args) if ok_size else None
        ahash = sha(canonical(args)) if ok_size else None
        self.allow_check = self.allow.classify(name, args if ok_size else {}, self.tainted)
        dec = self.allow_check
        self._event("agent.tool_proposed", {"tool": name, "tainted": self.tainted})
        base = dict(tool=name, risk_class=dec.risk, args_redacted=red, args_hash=ahash, tainted=self.tainted)
        if not ok_size:
            self.refusals += 1
            self._span("tool", t0, "refused", error_code="invalid_arguments", **base)
            return "error: invalid_arguments", None, None
        if dec.kind == "refused":
            self.refusals += 1
            self._span("tool", t0, f"refused:{dec.reason}",
                       error_code="invalid_arguments" if dec.reason == "invalid_arguments" else "permission_denied",
                       **base)
            return f"refused: {dec.reason}", None, None
        if dec.kind == "needs_approval":
            self.refusals += 1
            self._needs[call.id] = True
            self._span("tool", t0, "needs_approval", **base)
            return "not performed: this action needs human approval", None, None
        fp = (name, ahash)
        seen[fp] = seen.get(fp, 0) + 1
        if seen[fp] > self.lim.max_repeat_calls:
            self.refusals += 1
            self._span("tool", t0, "repeat_blocked", **base)
            if self.refusals >= self.lim.max_refusals:
                self._stop = _Stop("stopped", "loop_guard", "budget_exceeded", "loop_guard")
            return "blocked: identical call repeated", None, None
        if self.dispatched >= limit_calls:
            self._span("tool", t0, "cap_tool_calls", **base)
            self._stop = _Stop("stopped", "max_tool_calls", "budget_exceeded", "tool_calls")
            return "not performed: tool call limit reached", None, None
        self.dispatched += 1
        propose = dec.kind == "propose"
        req = ToolRequest(tool=name, arguments=dict(args), idempotency_key=self.ids.new_ulid(),
                          tenant_id=self.c.tenant_id, user_id=self.c.user_id, role_ids=tuple(self.c.role_ids),
                          session_id=self.c.session_id, run_id=self.run_id, agent_class=True, tainted=self.tainted,
                          propose=propose)
        cid = self.ids.new_id("call")
        yield RunEvent("tool_start", {"call_id": cid, "tool": name, "args": red})
        try:
            resp = self.tools.call(req)
            status = resp.status
        except Exception as e:
            err = firewall_exception(e)
            self._span("tool", t0, "error", error_code=err["code"], **base)
            yield RunEvent("tool_end", {"call_id": cid, "status": "error", "code": err["code"]})
            return f"error: {err['code']}", None, None
        audit = resp.audit_id if isinstance(resp.audit_id, str) else None
        if status == "pending_approval":
            aid = (resp.approval or {}).get("id") if isinstance(resp.approval, dict) else None
            if not isinstance(aid, str) or not aid:
                self._span("tool", t0, "error", error_code="internal_error", audit_id=audit, **base)
                self._stop = _Stop("failed", "error", "internal_error")
                return "error: internal_error", None, None
            self._span("tool", t0, "pending_approval", approval_id=aid, audit_id=audit, **base)
            yield RunEvent("approval", {"approval_id": aid, "tool": name})
            yield RunEvent("tool_end", {"call_id": cid, "status": "pending_approval", "approval_id": aid})
            return "pending human approval; the run stops here", None, aid
        if status == "ok":
            if propose:  # the Tool API must park a propose call; an executed one is a contract breach
                self._span("tool", t0, "unexpected_execution", error_code="internal_error", audit_id=audit, **base)
                self._stop = _Stop("failed", "error", "internal_error")
                yield RunEvent("tool_end", {"call_id": cid, "status": "error", "code": "internal_error"})
                return "error: internal_error", None, None
            item = wrap_data(self.ids.new_id("data"), f"tool:{name}", resp.result, self.lim.max_result_chars)
            self.tainted = True  # every tool result is L3 until a deterministic-class rule exists (Q-231)
            if "instruction_like" in item.flags:
                self._event("agent.output_flagged", {"reason_code": "instruction_like"})
            self._span("tool", t0, "ok", flags=item.flags, audit_id=audit, **{**base, "tainted": True})
            yield RunEvent("tool_end", {"call_id": cid, "status": "ok"})
            return f"ok: result in data item {item.content_id}", item, None
        err = map_tool_error(resp.error)
        self._span("tool", t0, "error", error_code=err["code"], audit_id=audit, **base)
        yield RunEvent("tool_end", {"call_id": cid, "status": "error", "code": err["code"]})
        if err["code"] == "budget_exceeded":
            self._stop = _Stop("stopped", "budget", "budget_exceeded", "tool_api")
        elif err["code"] == "permission_denied":
            self.refusals += 1
        extra = f" {canonical(err['params'])}" if err.get("params") else ""
        return f"error: {err['code']} retryable={str(err['retryable']).lower()}{extra}", None, None
