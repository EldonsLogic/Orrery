"""Agent runtime (OPR-001): deterministic loop, tool calls through the Tool API port, traces, budgets.

Design: docs/architecture/agent-runtime.md. Needs `services/operate` (toolapi, agui), `services/blueprint/events`
(evstream) and `services/` (gateway) on the path; the host sets that up. No model calls and no network here."""
from .allowlist import Allowlist, AssistantConfig, Decision, resolve_allowlist
from .errors import firewall_exception, map_tool_error
from .loop import AgentLoop
from .memory import MemoryTraceStore, SequentialIds, StoreEventSink, TickClock
from .models import (Caller, DataItem, Limits, ModelReply, ModelRequest, RunEvent, RunResult, Span, Step, TaintState,
                     ToolCall, ToolRequest, ToolResponse, ToolSpec, Usage)
from .ports import BudgetStop, CancelToken
from .untrusted import args_hash, redact_args, sanitise_text, wrap_data

__all__ = ["Allowlist", "AssistantConfig", "Decision", "resolve_allowlist", "firewall_exception", "map_tool_error",
           "AgentLoop", "MemoryTraceStore", "SequentialIds", "StoreEventSink", "TickClock", "Caller", "DataItem",
           "Limits", "ModelReply", "ModelRequest", "RunEvent", "RunResult", "Span", "Step", "TaintState", "ToolCall",
           "ToolRequest", "ToolResponse", "ToolSpec", "Usage", "BudgetStop", "CancelToken", "args_hash", "redact_args",
           "sanitise_text", "wrap_data"]
