"""Plain data types of the agent runtime. No behaviour, no I/O.

Trust levels follow docs/security/prompt-injection-defence.md: the model request keeps instructions (L0/L1),
the user's own turn (L2) and untrusted data (L3) in separate fields. Nothing in `data` is ever an instruction."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Limits:
    """Hard caps for one run. A value of 0 or less is never "unlimited": every cap is enforced."""
    max_steps: int = 8                 # model calls
    max_tool_calls: int = 12           # tool calls actually dispatched (refusals do not count)
    max_total_tokens: int = 60_000
    max_cost_micro_usd: int = 150_000  # docs/architecture/ai-layer.md budget example
    max_wall_s: float = 120.0
    max_repeat_calls: int = 2          # identical (tool, arguments) reads allowed; an identical write runs once only
    max_refusals: int = 3              # refused or blocked calls before the run stops; also the needs-approval cap
    max_result_chars: int = 8_000      # per tool result shown to the model
    max_args_bytes: int = 16_384
    est_input_tokens: int = 2_000      # per-call estimate handed to the gateway precheck
    est_output_tokens: int = 1_000
    est_call_cost_micro_usd: int = 0   # floor for the next call's projected cost (else the dearest call so far)


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cost_micro_usd: int = 0
    model_id: str = ""
    tier: str = ""
    metered: bool = False  # True when the gateway already wrote the meter event


@dataclass(frozen=True)
class TaintState:
    """Session-level taint (M8). The chat service (OPR-010) stores it with the session and passes it to the next run,
    so tool data summarised in earlier turns cannot come back untainted. Once tainted, a session stays tainted."""
    tainted: bool = False
    sources: tuple = ()                # provenance labels, e.g. "tool:sales_order.get" (at most 32 kept)

    def add(self, source: str) -> "TaintState":
        srcs = self.sources if source in self.sources else (self.sources + (str(source)[:128],))[-32:]
        return TaintState(True, srcs)


@dataclass(frozen=True)
class Caller:
    """The verified caller. Built from the identity service by the host; the model never supplies any of it."""
    tenant_id: str
    user_id: str
    role_ids: tuple
    session_id: str = ""


@dataclass(frozen=True)
class ToolCall:
    """A tool call the model asked for. `id` is the model's own label; it is never trusted as an identity."""
    id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class ModelReply:
    text: str = ""
    tool_calls: tuple = ()
    usage: Usage = field(default_factory=Usage)


@dataclass(frozen=True)
class DataItem:
    """Untrusted content with a provenance label (trust level L3). Built only by `untrusted.wrap_data`."""
    content_id: str
    source: str            # e.g. "tool:sales_order.get"
    text: str
    content_hash: str
    flags: tuple = ()      # sanitise flags, e.g. instruction_like, bidi_control, truncated
    trust: str = "L3"


@dataclass(frozen=True)
class Step:
    """One finished model step as shown back to the model: its text, its calls and what they returned."""
    text: str
    calls: tuple           # of (ToolCall, observation text written by the platform)


@dataclass(frozen=True)
class ToolSpec:
    """What the model may see of an allowed tool."""
    name: str
    description: str
    input_schema: dict
    risk_class: str
    mode: str              # run | propose


@dataclass(frozen=True)
class ModelRequest:
    instructions: str                  # L0/L1 platform text, resolved by the caller from i18n keys
    user_turn: str                     # L2: the signed-in user's own words
    steps: tuple                       # of Step (assistant history; observations are platform-written)
    data: tuple                        # of DataItem (L3), a separate channel
    tools: tuple                       # of ToolSpec (the allow-list for this run only)
    tainted: bool
    locale: str = "en"


@dataclass(frozen=True)
class ToolRequest:
    """What the Tool API port receives. Caller identity comes from the verified principal, never the model."""
    tool: str
    arguments: dict
    idempotency_key: str
    tenant_id: str
    user_id: str
    role_ids: tuple
    session_id: str
    run_id: str
    agent_class: bool = True
    tainted: bool = False
    propose: bool = False  # True: create a pending approval (confirm preview), execute nothing


@dataclass(frozen=True)
class ToolResponse:
    """Mirror of contracts/tool-api.md section 3 and 7: status ok | pending_approval | error."""
    status: str
    result: object = None
    approval: dict | None = None
    error: dict | None = None
    audit_id: str | None = None


@dataclass(frozen=True)
class Span:
    span_id: str
    run_id: str
    tenant_id: str
    step: int
    kind: str                       # run | model | tool
    started_ms: int
    ended_ms: int
    outcome: str
    tool: str | None = None
    risk_class: str | None = None
    args_redacted: dict | None = None
    args_hash: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cost_micro_usd: int = 0
    tainted: bool = False
    flags: tuple = ()
    error_code: str | None = None
    approval_id: str | None = None
    audit_id: str | None = None

    def to_dict(self) -> dict:
        return {k: (list(v) if isinstance(v, tuple) else v) for k, v in self.__dict__.items()}


@dataclass(frozen=True)
class RunResult:
    status: str                     # completed | interrupted | stopped | cancelled | failed
    stop_reason: str                # none | interrupt | max_steps | max_tool_calls | max_tokens | max_cost |
                                    # wall_clock | loop_guard | refusals | needs_approval | propose_unavailable |
                                    # cancelled | budget | rate_limited | error
    answer: str = ""
    error_code: str | None = None
    approval_ids: tuple = ()
    needs_approval: tuple = ()      # tool names refused for need of human approval
    steps: int = 0
    tool_calls: int = 0
    tainted: bool = False
    usage: Usage = field(default_factory=Usage)
    taint_state: TaintState = field(default_factory=TaintState)  # persist with the session (OPR-010)


# Events yielded while a run is in flight (the adapter maps them to AG-UI events).
@dataclass(frozen=True)
class RunEvent:
    kind: str                       # text | tool_start | tool_end | usage | approval | done
    data: dict = field(default_factory=dict)
    result: RunResult | None = None
