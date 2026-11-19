"""The `AgentRuntime` port of services/operate/agui (ADR-0044), backed by the agent loop.

It yields allow-listed AG-UI event dicts and `RuntimeUsage` items only. The endpoint owns the run envelope and writes
`agent.run_*` events, so the loop is built with `emit_run_events=False` here. Tool results are not streamed: the chat
renders records itself; the stream carries the call, its status and any approval id."""
from __future__ import annotations

import json
from typing import Callable, Iterable, Optional

from agui.errors import AuthFailure
from agui.ports import RuntimeContext, RuntimeUsage

from .allowlist import AssistantConfig, resolve_allowlist
from .loop import AgentLoop
from .models import Caller, Limits
from .ports import CancelToken

BUDGET_KEY = "errors.budget_exceeded"


class AguiRuntimeAdapter:
    def __init__(self, *, model, tools, tool_defs: Callable[[str], list], clock, ids, traces, events=None,
                 limits: Limits = Limits(), model_id: str = "unknown", prompt_version: str = "unversioned",
                 assistant_for: Optional[Callable[[object], Optional[AssistantConfig]]] = None,
                 instructions_for: Callable[[str], str] = lambda locale: "",
                 cancel_for: Optional[Callable[[str], CancelToken]] = None):
        self.model, self.tools, self.tool_defs = model, tools, tool_defs
        self.clock, self.ids, self.traces, self.events, self.limits = clock, ids, traces, events, limits
        self.model_id, self.prompt_version = model_id, prompt_version
        self.assistant_for, self.instructions_for, self.cancel_for = assistant_for, instructions_for, cancel_for

    def run(self, ctx: RuntimeContext) -> Iterable:
        p = ctx.principal
        assistant = self.assistant_for(p) if self.assistant_for else None
        allow = resolve_allowlist(self.tool_defs(p.tenant_id), p.role_ids, assistant)  # roles: principal only
        loop = AgentLoop(model=self.model, tools=self.tools, allow=allow, limits=self.limits, clock=self.clock,
                         ids=self.ids, traces=self.traces, events=self.events,
                         cancel=self.cancel_for(ctx.run_id) if self.cancel_for else None, emit_run_events=False)
        caller = Caller(p.tenant_id, p.subject, tuple(p.role_ids), p.session_id)
        calls = {}
        for ev in loop.stream(caller=caller, run_id=ctx.run_id, user_text=ctx.user_text,
                              instructions=self.instructions_for(ctx.locale), locale=ctx.locale):
            d = ev.data
            if ev.kind == "text":
                yield from self._text(d["text"])
            elif ev.kind == "usage" and not d["usage"].metered:
                u = d["usage"]
                yield RuntimeUsage(u.model_id or self.model_id, u.tier or "mid", u.input_tokens, u.output_tokens,
                                   u.cached_tokens, u.cost_micro_usd)
            elif ev.kind == "tool_start":
                calls[d["call_id"]] = d["tool"]
                yield {"type": "TOOL_CALL_START", "toolCallId": d["call_id"], "toolCallName": d["tool"]}
                yield {"type": "TOOL_CALL_ARGS", "toolCallId": d["call_id"], "delta": json.dumps(d["args"] or {})}
                yield {"type": "TOOL_CALL_END", "toolCallId": d["call_id"]}
            elif ev.kind == "tool_end":
                body = {k: v for k, v in d.items() if k in ("status", "code", "approval_id")}
                yield {"type": "TOOL_CALL_RESULT", "toolCallId": d["call_id"], "messageId": self.ids.new_id("msg"),
                       "content": json.dumps(body)}
            elif ev.kind == "approval":
                yield {"type": "CUSTOM", "name": "approval.pending",
                       "value": {"approvalId": d["approval_id"], "tool": d["tool"]}}
            elif ev.kind == "done":
                r = ev.result
                if r.error_code == "permission_denied":
                    raise AuthFailure(403)
                if r.error_code == "internal_error":
                    raise RuntimeError("agent run failed")  # the endpoint maps it to a generic internal error
                if r.error_code == "budget_exceeded":
                    yield from self._text(BUDGET_KEY)

    def _text(self, text: str):
        mid = self.ids.new_id("msg")
        yield {"type": "TEXT_MESSAGE_START", "messageId": mid, "role": "assistant"}
        yield {"type": "TEXT_MESSAGE_CONTENT", "messageId": mid, "delta": text}
        yield {"type": "TEXT_MESSAGE_END", "messageId": mid}
