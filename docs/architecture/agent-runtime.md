# Agent runtime

Status: draft
Owner: eldon

Plan row OPR-001. Code: `services/operate/runtime/`. It is the agent-runtime port that `services/operate/agui` expects ([ADR-0044](../decisions/ADR-0044-ag-ui-agent-to-screen-transport.md)). Model-agnostic, no model calls and no network inside it. Security basis: [prompt-injection-defence](../security/prompt-injection-defence.md), [ADR-0027](../decisions/ADR-0027-human-floor-action-policy-and-agent-authority.md), [ADR-0043](../decisions/ADR-0043-department-assistants.md), [Tool API](../../contracts/tool-api.md).

## Turn state machine
Plan (build request) -> call model -> parse tool calls -> classify each call -> execute through the Tool API port only -> observe -> repeat. It ends on an answer (no tool calls), an interrupt, a cap, a cancel or a failure. Ids and the clock are injected, so one model script gives one trace.

## Ports (all injected)
`ModelPort.complete(request) -> ModelReply`; `ToolPort.call(request) -> ToolResponse` (contract sections 3 and 7); `TraceStore`; `EventSink`; `Ids`; `Clock`; `CancelToken`. `GatewayModelPort` wraps `MeteredGatewayRouter` (tier routing, budget precheck, metering stay in the gateway; live providers are PLT-009). Callers: tenant, user, roles and session come from the verified principal; the model supplies only a tool name and arguments.

## Controls
| Control | Rule |
|---|---|
| Allow-list | Per run, from the principal's roles and the optional assistant config: role overlap, `agent_creatable`, at most R2, never `approval.decide` or `blueprint.propose_change`; an assistant needs `confirm: true` for each R2 tool. No roles or an unreadable tool set gives an empty list; no roles fails the run. |
| Risk | R0 and untainted R1 run. R2, and R1 once the run is tainted, are sent to the Tool API with `propose=true` (a pending approval) and the loop stops at an interrupt. R3 and R4 never run: recorded as `needs_approval`. A transition tool takes the risk and agent flag of the chosen transition. |
| Untrusted data | Tool results become `DataItem`s (trust L3, source, hash, sanitise flags) in `ModelRequest.data`, never in instructions, the user turn or observations. Flags come from the discovery sanitise and detect functions; `instruction_like` also writes `agent.output_flagged`. Every tool result taints the run (Q-231). |
| Caps | Steps, tool calls, tokens, cost, wall clock (injected clock), repeat calls, refusals; plus the gateway precheck inside `GatewayModelPort`. A cap stops the run with `budget_exceeded` and `agent.budget_exceeded` with a budget kind. |
| Errors | Tool errors keep only a Tool API class code or an ADR-0036 catalog id with typed params; free text, exception text and stack traces never reach the model, the trace or the wire (`errors.py`). Port exceptions become `internal_error`. |
| Cancel | `CancelToken` is checked before each step and each call; no further tool call starts. |

## Trace and events
One `Span` per model call, per tool call (tool, risk class, outcome, redacted args, args hash, tokens, cost, approval and audit ids) and one for the run. Spans go to a tenant-scoped `TraceStore` (in-memory here). Events through `EventSink`: `agent.run_started`, `agent.run_completed`, `agent.run_failed`, `agent.tool_proposed`, `agent.budget_exceeded`, `agent.output_flagged`. `tool.called` is written by the Tool API and `meter.ai_usage` by the gateway, not here. Under agui the endpoint already writes `agent.run_*`, so the adapter sets `emit_run_events=False`, and yields `RuntimeUsage` only when the usage was not already metered by the gateway.

## agui adapter
`AguiRuntimeAdapter.run(ctx)` yields text, tool call and `approval.pending` events and `RuntimeUsage`; tool results are not streamed. `permission_denied` raises the endpoint's auth failure, `internal_error` raises a plain error (generic wire error), a budget stop yields the key `errors.budget_exceeded` (Q-233).

## Not here
Live providers (PLT-009), the real Tool API gateway (OPR-004), intent routing (OPR-002), chat sessions (OPR-010), summarisation and memory, a persistent trace store.
