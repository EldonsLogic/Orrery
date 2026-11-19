"""The `AgentRuntime` port of services/operate/agui (ADR-0044), backed by the agent loop.

It yields allow-listed AG-UI event dicts and `RuntimeUsage` items only. The endpoint owns the run envelope and writes
`agent.run_*` events, so the loop is built with `emit_run_events=False` here. Tool results are not streamed: the chat
renders records itself; the stream carries the call, its status and any approval id.

Tenant binding (H2): the model port is built per request by `model_for(principal, run_id)` (for the gateway:
`gateway_port.gateway_model_for(router)`), so budgets and metering land on the caller's tenant. The older shared
`model=` still works for unbound ports (tests, scripted fakes); a port bound to another tenant fails the run closed."""
from __future__ import annotations

import json
from typing import Callable, Iterable, Optional

from agui.errors import AuthFailure
from agui.ports import RuntimeContext, RuntimeUsage

from .allowlist import AssistantConfig, resolve_allowlist
from .loop import AgentLoop
from .models import Caller, Limits, TaintState
from .ports import CancelToken

BUDGET_KEY = "errors.budget_exceeded"
OUTCOME_KEYS = {"budget_exceeded": BUDGET_KEY, "needs_approval": "errors.needs_approval",
                "propose_unavailable": "errors.propose_unavailable"}


class AguiRuntimeAdapter:
    reports_approvals = True  # the endpoint interrupts only on approvals listed in ctx.run_approvals (M7)

    def __init__(self, *, model=None, tools, tool_defs: Callable[[str], list], clock, ids, traces, events=None,
                 limits: Limits = Limits(), model_id: str = "unknown", prompt_version: str = "unversioned",
                 assistant_for: Optional[Callable[[object], Optional[AssistantConfig]]] = None,
                 instructions_for: Callable[[str], str] = lambda locale: "",
                 cancel_for: Optional[Callable[[str], CancelToken]] = None,
                 model_for: Optional[Callable[[object, str], object]] = None,
                 hash_salt_for: Optional[Callable[[str], bytes]] = None,
                 taint_for: Optional[Callable[[RuntimeContext], Optional[TaintState]]] = None,
                 on_taint: Optional[Callable[[RuntimeContext, TaintState], None]] = None):
        if model is None and model_for is None:
            raise ValueError("model_for (or a shared unbound model) is required")
        self.model, self.model_for, self.tools, self.tool_defs = model, model_for, tools, tool_defs
        self.clock, self.ids, self.traces, self.events, self.limits = clock, ids, traces, events, limits
        self.model_id, self.prompt_version = model_id, prompt_version
        self.assistant_for, self.instructions_for, self.cancel_for = assistant_for, instructions_for, cancel_for
        self.hash_salt_for, self.taint_for, self.on_taint = hash_salt_for, taint_for, on_taint

    def run(self, ctx: RuntimeContext) -> Iterable:
        p = ctx.principal
        assistant = self.assistant_for(p) if self.assistant_for else None
        allow = resolve_allowlist(self.tool_defs(p.tenant_id), p.role_ids, assistant)  # roles: principal only
        model = self.model_for(p, ctx.run_id) if self.model_for else self.model
        loop = AgentLoop(model=model, tools=self.tools, allow=allow, limits=self.limits, clock=self.clock,
                         ids=self.ids, traces=self.traces, events=self.events,
                         cancel=self.cancel_for(ctx.run_id) if self.cancel_for else None, emit_run_events=False,
                         hash_salt=self.hash_salt_for(p.tenant_id) if self.hash_salt_for else None)
        caller = Caller(p.tenant_id, p.subject, tuple(p.role_ids), p.session_id)
        taint = self.taint_for(ctx) if self.taint_for else None
        for ev in loop.stream(caller=caller, run_id=ctx.run_id, user_text=ctx.user_text,
                              instructions=self.instructions_for(ctx.locale), locale=ctx.locale, taint=taint):
            d = ev.data
            if ev.kind == "text":
                yield from self._text(d["text"])
            elif ev.kind == "usage" and not d["usage"].metered:  # the gateway already metered it: never twice
                u = d["usage"]
                yield RuntimeUsage(u.model_id or self.model_id, u.tier or "mid", u.input_tokens, u.output_tokens,
                                   u.cached_tokens, u.cost_micro_usd)
            elif ev.kind == "tool_start":
                yield {"type": "TOOL_CALL_START", "toolCallId": d["call_id"], "toolCallName": d["tool"]}
                yield {"type": "TOOL_CALL_ARGS", "toolCallId": d["call_id"], "delta": json.dumps(d["args"] or {})}
                yield {"type": "TOOL_CALL_END", "toolCallId": d["call_id"]}
            elif ev.kind == "tool_end":
                body = {k: v for k, v in d.items() if k in ("status", "code", "approval_id")}
                yield {"type": "TOOL_CALL_RESULT", "toolCallId": d["call_id"], "messageId": self.ids.new_id("msg"),
                       "content": json.dumps(body)}
            elif ev.kind == "approval":
                ctx.run_approvals.append(d["approval_id"])
                yield {"type": "CUSTOM", "name": "approval.pending",
                       "value": {"approvalId": d["approval_id"], "tool": d["tool"]}}
            elif ev.kind == "done":
                r = ev.result
                if self.on_taint:
                    self.on_taint(ctx, r.taint_state)
                if r.error_code == "permission_denied" and r.stop_reason == "error":
                    raise AuthFailure(403)  # only the no-roles case is an auth failure
                if r.error_code in ("internal_error", "permission_denied"):
                    raise RuntimeError("agent run failed")  # the endpoint maps it to a generic internal error
                if r.error_code in OUTCOME_KEYS:
                    yield from self._text(OUTCOME_KEYS[r.error_code])

    def _text(self, text: str):
        mid = self.ids.new_id("msg")
        yield {"type": "TEXT_MESSAGE_START", "messageId": mid, "role": "assistant"}
        yield {"type": "TEXT_MESSAGE_CONTENT", "messageId": mid, "delta": text}
        yield {"type": "TEXT_MESSAGE_END", "messageId": mid}
