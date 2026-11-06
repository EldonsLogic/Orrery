# Spec 04: Operate (Part 4)

Status: draft
Owner: unassigned
Plan IDs: OPR (plus SEC, QA, WEB for screens)

## Purpose
The one chat after go-live. Anyone in the company asks, acts, gets reports and requests changes, in Arabic or English, with their own permissions and their own role-based view of the system.

## Responsibilities
1. **Chat with modes** discover / ask / act / change, one UI. **Intent router** classifies each turn and applies the right guardrails.
2. **Typed tool API per tenant**, generated from the Blueprint ([tool-api.md](../../contracts/tool-api.md)).
3. **Semantic layer**: governed metrics (`sales.revenue`, `finance.receivables_aging`) computed by code; the model picks metric ids and explains results, it does not compute them.
4. **Role-based views**: screens and tools generated from role, function and scope; the chat acts with the user's own permissions.
5. **Approval inbox**: pending approvals for the caller, decide in chat or on screen.
6. **Report builder**: natural-language to a report definition (metric refs + filters), saved as a Blueprint report via the change path.
7. **Change-by-chat**: any request to change the system becomes a Blueprint diff through Part 2 (simulate, explain, approve, apply).
8. **Scheduled agents** with budgets and permissions (reminders, document extraction, reconciliation suggestions). They draft; humans approve anything touching ledger, tax or external sends.
9. **Per-tenant memory** (preferences, terminology, notes) with expiry and a review screen.

## Interfaces
| Contract | Use |
|---|---|
| Tool API | Exposes and enforces |
| Blueprint | Reads roles, scopes, reports; writes only via `blueprint.propose_change` |
| Events | Emits `tool.called`, `chat.turn_completed`, `agent.*`, `memory.*`, `meter.ai_usage`; reads record events for agent triggers |
| AI gateway | Model calls with tier, budget and region routing ([ai-layer](../architecture/ai-layer.md)) |
| Theming | Applies resolved tokens to the app ([theming](../architecture/theming.md)) |

## Data owned
Chat sessions and summaries, agent definitions and run logs, tenant memory, saved report definitions (mirrored in Blueprint), approval requests, semantic-layer metric definitions (platform-level, parameterised per tenant).

## Key behaviours
- Anyone in the company can chat; what they see and can do depends on their role and scope. The chat cannot exceed the user's permissions.
- Writes show a confirmation step in the user's language before execution, or park for approval when a rule matches.
- Answers with figures cite the metric or record id; figures come from tool results.
- Arabic and English can be mixed within a conversation; replies follow the user's language and glossary.
- Untrusted content (an invoice's text, an email) never changes the tool plan; tainted write calls need human approval.

## Failure modes
| Failure | Handling |
|---|---|
| Model proposes a tool the user cannot use | Tool filter plus server-side check; polite denial, `permission.denied` event |
| Prompt injection from a document | Quoted-data handling, policy filter, tainted flag, human approval; `agent.output_flagged` |
| Model outage or budget exhausted | Provider fallback; then degrade to deterministic reports and menus |
| Ambiguous request | Ask one clarifying question; never guess on writes |
| Memory poisoning | Memory writes are explicit, attributed, reviewable and expire |

## Security notes
- All authorization in the tool API gateway, not in prompts.
- Chat transcripts are tenant data; support sees them only via just-in-time access.
- Rate and budget limits per user and tenant; abuse detection.
- Agents run with a service role of least privilege defined in their definition, never the owner's role.

## Open questions
1. Voice and WhatsApp as chat channels: after G2.
2. How much of the semantic layer is hand-written vs generated from components?
3. Per-user vs per-tenant memory boundaries for privacy within a company.
4. Pricing of agent runs vs seats (see strategy 07).

## Acceptance criteria
**G1 (spine proven)**
- Tool generation from the example Blueprint produces the documented tool set; role/scope/field checks have tests including the fail-closed cases.
- A scripted chat turn in Arabic creates a sales order with the user's permissions; a second user without permission is denied and audited.
- Semantic layer answers three metrics from code; the model never outputs an unverified number (test).

**G2 (pilot-ready)**
- The pilot's staff each get their own role view and use the chat for ask and act in daily work.
- At least one change-by-chat completes through Part 2 end to end with simulation and approval.
- Approval inbox works for the owner on mobile.
- Injection test suite passes; cost per active user per month is measured and within budget.
