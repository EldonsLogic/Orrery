"""Default runtime factory over the OPR-001 agent loop. History reaches the model only as L3 data items, by
wrapping the model port; the loop and the allow-list are untouched. A fresh adapter per run carries that run's
history and cancel token."""
from __future__ import annotations

import dataclasses

from runtime import Limits, RateLimitedTools, RateLimiter
from runtime.agui_adapter import AguiRuntimeAdapter


class HistoryModel:
    """ModelPort decorator: prepends history data items to `ModelRequest.data` (never to instructions)."""

    def __init__(self, inner, items: tuple):
        self.inner, self.items = inner, items
        self.model_id = getattr(inner, "model_id", "unknown")
        self.prompt_version = getattr(inner, "prompt_version", "unversioned")

    def complete(self, request):
        return self.inner.complete(dataclasses.replace(request, data=self.items + tuple(request.data)))


def loop_runtime_factory(*, model, tools, tool_defs, clock, ids, traces, events=None, limits: Limits = Limits(),
                         assistant_for=None, limiter=None):
    """Return `factory(setup) -> AgentRuntime` for `ChatService`. Every dispatched tool call counts against the
    caller's tenant and user `tool` rules (SEC-009): pass the chat service's `limiter`, else defaults on `clock`."""
    tools = RateLimitedTools(tools, RateLimiter(clock) if limiter is None else limiter)

    def factory(setup):
        return AguiRuntimeAdapter(
            model=HistoryModel(model, setup.window.items), tools=tools, tool_defs=tool_defs, clock=clock, ids=ids,
            traces=traces, events=events, limits=limits, assistant_for=assistant_for,
            instructions_for=lambda locale: setup.window.frame, cancel_for=lambda run_id: setup.cancel,
            model_id=str(getattr(model, "model_id", "unknown")),
            prompt_version=str(getattr(model, "prompt_version", "unversioned")))
    return factory
