# ADR-0044: AG-UI as the agent-to-screen transport, not an authority

Status: Proposed
Owner: eldon
Approved by: pending

## Context
The chat screen (WEB-004) and the agent servers (OPR-001, OPR-010) are not built, and nothing defines the live stream between them. The Event stream contract ([events.md](../../contracts/events.md)) is the durable, append-only record of what happened in a tenant; it is not a live UI protocol. The partner proposed adopting the AG-UI protocol for this link; the WEB-022 paper spike ([web-022-ag-ui-spike.md](../research/web-022-ag-ui-spike.md)) mapped our chat needs to AG-UI events and recommended adopting the vocabulary by a short ADR. This is that ADR.

Facts (accessed 2026-11-18):
- AG-UI is an MIT-licensed event protocol for agent-to-user streams, created and maintained by CopilotKit (https://github.com/ag-ui-protocol/ag-ui). The README calls 1.0 "stable, frozen" with a JSON Schema and backward compatible with 0.x; the exact spec GA date is UNVERIFIED.
- Python SDK `ag-ui-protocol` 1.0.0 was published on PyPI on 2026-09-17, MIT, owned by the CopilotKit organisation (https://pypi.org/pypi/ag-ui-protocol/json). Before that it moved quickly through 0.1.x.
- npm `@ag-ui/client` latest is 1.0.5, MIT per the repo `package.json`, maintainers include CopilotKit (https://registry.npmjs.org/@ag-ui/client; release `release/2026-11-17`, https://api.github.com/repos/ag-ui-protocol/ag-ui/releases/latest).
- Events include text messages, `ToolCall*`, `StateSnapshot` and `StateDelta` (JSON Patch, RFC 6902), `RunError` (message, optional code, terminal), `Custom`, `Raw` and `Reasoning*` (https://docs.ag-ui.com/concepts/events).
- Interrupts: `RunFinished.outcome` may be `interrupt`; resume is a new run carrying `resume[]` entries `{interruptId, status, payload}` (https://docs.ag-ui.com/concepts/interrupts). Whether interrupts are labelled stable or draft is UNVERIFIED.
- Transports: HTTP POST of `RunAgentInput` with a Server-Sent Events response, and an HTTP binary (Protobuf) option. WebSockets are mentioned but not specified (https://docs.ag-ui.com/concepts/architecture); treat them as not standardised.
- AG-UI is not a generative-UI spec; it can carry A2UI (declarative), Open-JSON-UI and MCP-UI (iframe) payloads (https://docs.ag-ui.com/concepts/generative-ui-specs).
- Advisory GHSA-chx5-hp6j-gv92 (High, CVSS 7.5, published 2026-10-21): the `ag-ui-adk` integration stored client-supplied `RunAgentInput.state` under shared app and user prefixes, so a caller could write shared state; fixed in 0.11.0 (https://github.com/ag-ui-protocol/ag-ui/security/advisories/GHSA-chx5-hp6j-gv92). It is the only advisory found; the list may be incomplete (UNVERIFIED).

Constraints from accepted or proposed decisions: one chat that acts only with the caller's own permissions (ADR-0004); human review and approval-required actions (ADR-0005, ADR-0027 Proposed); tokens-only, RTL-safe UI (ADR-0014, ADR-0022); engine invisibility (ADR-0016); per-tenant tokens with the tenant re-derived from the token (ADR-0007); approval only counts when it is a recorded review, never a transient or verbal signal (ADR-0032, a repo rule applied here by analogy); bilingual domain error codes (ADR-0036 Proposed).

## Decision
1. **Transport only, never authority.** We adopt the AG-UI event vocabulary and wire format as the transport between the agent servers (`services/operate`, `services/discovery`) and the web app. Nothing received over AG-UI grants, widens or proves permission. Every tool call, whether proposed by the model or requested by the client, is decided by the Tool API role and scope check ([tool-api.md](../../contracts/tool-api.md) section 4) and the action policy (ADR-0027). Client-side ("frontend") tools are not offered: the model cannot cause a browser action.
2. **No interrupt or resume is an approval.** An AG-UI interrupt only displays a pending approval that the Tool API already created (`status: pending_approval`, section 5). The decision is made by an authenticated call to our own approval endpoint (`approval.decide`), bound to the tenant, action, data revision, amount, approver and expiry (ADR-0027), and written as a recorded review through the audit path (`approval.decided` and `tool.called` events). A resume entry carries only the approval id; its `status` and `payload` are never read as the decision, and a resume naming an approval that is not recorded as decided does nothing.
3. **Static typed payloads to certified components only.** The agent may only emit typed data (tool-call summaries, state snapshots and deltas, allow-listed `Custom` names), each validated against our schema and rendered by a fixed set of our own token-themed, RTL-tested components. No declarative or open-ended UI: A2UI, Open-JSON-UI, MCP-UI, iframes, HTML or markup from the model are refused. Model text is rendered as plain text. `Raw` and `Reasoning*` events are never sent. The client drops unknown event types and unknown `Custom` names (fail closed).
4. **The Event stream stays the durable log.** AG-UI streams are ephemeral. Audit, compliance and metering (`tool.called`, `approval.*`, `meter.ai_usage`) are written to the Event stream by the server as they happen; an AG-UI event is never the source of an audit or billing fact, and a dropped stream loses no record.
5. **Client-supplied input is untrusted.** `RunAgentInput.state`, `messages`, `context`, `forwardedProps` and `tools` from the browser are data, never instructions, roles, tenant ids or caller ids. The server keeps its own session state; client state is at most a hint, validated and size-capped, and is never written to shared or cross-user storage (lesson of GHSA-chx5-hp6j-gv92). Prompt-injection rules apply (SEC-003, Tool API section 10).
6. **Error firewall.** Every failure is mapped to our error model (Tool API section 7, domain codes per ADR-0036, bilingual `message_key`) before a `RunError` is emitted. `RunError.message` carries only an i18n key or a catalog message; `code` is our code. No stack traces, SQL, paths or engine text.
7. **Engine invisibility on the wire.** No event type, tool name, argument, result, state key, `Custom` name, error, header, cookie or SSE comment names the engine or exposes its paths (ADR-0016). Tool names are Tool API names. The staging crawl (QA-016) covers the stream endpoint.
8. **Pinned SDKs and a fallback.** `ag-ui-protocol` (PyPI) and `@ag-ui/client` (npm) are pinned to exact versions in the lockfiles and upgraded only by reviewed PRs. Vendor risk: both are owned by one company (CopilotKit) and the Python SDK reached 1.0.0 only on 2026-09-17. Fallback if the project is abandoned or changes licence: the spec is MIT and small, so we keep the 1.0 event schema we use and replace the SDKs with our own encoder and a thin client; our components and the server's allow-list do not change. We use the SDKs' event types and encoder, not CopilotKit's UI or runtime.
9. **SSE first.** The first transport is HTTP POST plus Server-Sent Events. WebSocket and the binary transport are not assumed; adding one needs a plan row and a review of its auth and gateway handling.
10. **Auth on the stream endpoint.** The endpoint sits behind our gateway and requires the per-tenant session of ADR-0007: the tenant comes from the token, never from the URL, body or `RunAgentInput`; a thread or run id from another tenant or user is refused; the stream ends when the access token or session version is no longer valid. Fail closed on any auth error.

## Alternatives rejected
- **Our own protocol.** Full control, but we would design, document and maintain an event set that AG-UI already defines; the fallback in item 8 keeps that option open at low cost.
- **Vercel AI SDK data stream.** Tied to one vendor's SDK and server helpers, aimed at chat text rather than state sync and interrupts; its UI parts invite generated UI that we refuse.
- **Raw SSE with ad hoc JSON.** Simplest today, but every event shape, resync and error rule would be reinvented without a schema or shared tests.
- **CopilotKit full stack (runtime and React components).** More dependency on the same vendor; its components are not token-only or proven RTL (UNVERIFIED), and its runtime would sit where our Tool API and approval path must decide.

## Consequences
- Easier: one documented event set for chat, tool progress, Blueprint draft state and approvals; shared tests; SDKs in both languages.
- Harder: an allow-list, schema validation and an error mapper on the server; a strict renderer on the client; a dependency on one vendor's SDKs, watched through pinned versions and the licence register.
- Must be done: GOV-051 (this ADR); OPR-020 (server stream endpoint) and WEB-026 (web stream client), both in eldon's lane; the licence register rows for both SDKs, marked planned, before first use; open questions Q-175 to Q-177. The gateway (PLT-024, partner) must pass the SSE response through unbuffered; recorded as Q-176, not a dependency.
- Security review by a different model or founder is needed before acceptance (auth and tenancy, AGENTS.md security rules).

## Supersedes
none
