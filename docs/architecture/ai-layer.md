# AI layer

Status: draft
Owner: eldon

How models are used across the platform. Basis: [strategy 03](../strategy/03-ai-native-and-moat.md), [strategy 06](../strategy/06-model-strategy.md) (all prices there are ASSUMPTIONS). Decision: ADR-0010. Rule of thumb: **numbers come from code, words come from the model.** Anything with a rule is deterministic code.

## Model gateway
One internal service every model call goes through (Part 5). Verify the licence of any adopted gateway (for example LiteLLM) before use; not checked yet.
| Capability | Behaviour |
|---|---|
| Routing | By task tier, not customer choice; per-provider model ids hidden behind tier names |
| Budgets | Per tenant, per user, per agent, per run; owner alerts at thresholds; hard cap; deterministic paths still work when exhausted |
| Caching | Prompt caching and response caching for repeated, non-personal prompts |
| Regional routing | Tenant region decides allowed endpoints; KSA traffic only to approved endpoints (availability UNVERIFIED) |
| Logging | Every call: tenant, purpose, tier, model id, prompt version, token counts, cost, latency, redaction summary. Content logging is configurable and off by default for tenant data |
| Fallback | Provider/model fallback chain per tier; degrade to deterministic features |
| Redaction | Names, IBANs, national IDs, phone numbers redacted before the call where the task allows ([data](data.md)) |
| Zero retention | Provider terms with no training and minimal retention; verify per provider (UNVERIFIED) |

## Tiering
| Tier | Use | Volume |
|---|---|---|
| frontier | Interview, source mapping, Blueprint planning, diff explanation, component specs | Low, high stakes |
| mid | Document extraction, agent drafting, report-building | Medium |
| small | Run-time chat turns, routing, classification, summarisation | High |
| code | Anything with a rule: tax, totals, dates, permissions, validation | Not a model |
Models are chosen per tier by passing the Arabic eval at the lowest cost. The registry is `agents/model-registry.md`.

## Agent definition format
Each agent is a versioned file (YAML/JSON) in `agents/`. Customers never see model names.
```yaml
id: invoice_reminder_agent
version: 3
purpose: "Draft payment reminders for overdue invoices"
tier: small
prompt: prompts/invoice_reminder@3        # from the prompt registry
tools:                                    # allow-list from the tenant's Tool API
  - metric.query
  - sales_invoice.list
  - message.draft                         # drafts only; sending needs approval
permissions:
  service_role: agent_reminder            # least privilege role defined in the Blueprint
  scope: from_tenant_config
budget: {max_calls: 40, max_rows: 500, max_cost_micro_usd: 150000, max_runtime_s: 120}
approval:
  rule: all_external_sends_require_human
  auto_approve: []
triggers: [{event: "meter.day_start"}, {event: "document.issued"}]
inputs_trust: untrusted_content_quoted_only
outputs: {schema: schemas/reminder_draft.json, language: from_user_or_tenant}
evals: [evals/agents/invoice_reminder]
```

## Prompt registry
Prompts are files, versioned in the repo, with owner, purpose, tier, input and output schema, and linked eval sets. A prompt change is a PR that must pass its evals (CI gate). Prompts reference glossary terms by key, not hard-coded strings. Production pins prompt versions; the version is logged on every call.

## Evals (a product asset)
- **Arabic/English set** starting at 100 prompts: Gulf and MSA dialects, mixed language, accounting terms, Hijri dates, number formats, Egyptian dialect once Egypt is in scope. Grows with every incident and pilot (anonymised).
- Suites: interview-to-Blueprint, source mapping accuracy, diff explanation, tool-call correctness (right tool, right args), refusal/permission behaviour, injection resistance, date handling, numeric fidelity.
- Replay simulation harness for the month simulation.
- Gates: a model or prompt change cannot ship if it regresses a blocking suite; results are recorded per release. Formats and thresholds: [evals/README](../../evals/README.md).

## Injection and untrusted-content defences
1. Content from connectors, documents, emails and web pages is **untrusted data**, wrapped and labelled, never concatenated into instructions.
2. The tool plan is decided by trusted context only; untrusted content cannot add tools, change roles or alter approval rules.
3. **Tainted calls**: any write proposed while untrusted content is in context is flagged; on ledger, tax or external-send tools it always requires human approval.
4. Server-side checks on every tool call (role, scope, schema, approval); the model is never the guard.
5. Output filters for secrets, other tenants' identifiers and unsafe URLs; no model-driven fetching of arbitrary URLs.
6. Canary and red-team prompts in evals; `agent.output_flagged` events reviewed.
7. No tool takes credentials, SQL, code or role names as arguments.

## Cost caps
Per-tenant monthly AI budget (plan entitlement), per-run caps, heavy-job cost previews expressed in "AI actions" not tokens (bulk migration, month simulation), batch for non-urgent work, summarised histories, caching. Metering events `meter.ai_usage` ([events](../../contracts/events.md)). Cost per tenant and gross margin are tracked ([strategy 06](../strategy/06-model-strategy.md)).

## Numbers from code
- The model never calculates totals, taxes, dates, ageing or balances. It selects a metric or tool; code returns the value; the model phrases it.
- Responses with figures must include references (metric id or record id). A post-check compares figures quoted in the reply to the tool results and blocks mismatches.
- Dates and Hijri conversions use the calendar tools ([calendars-and-locale](calendars-and-locale.md)).

## Per-tenant memory
- Stores preferences, terminology, short facts the user asked to remember; never ledger data, credentials or personal data beyond need.
- Writes are explicit events (`memory.written`) with author and source; entries expire by default and are reviewable and deletable by the tenant admin.
- Memory is injected as untrusted-lite context (labelled), cannot grant permissions.
- No memory crosses tenants; tenant memory is deleted with the tenant.

## Open questions
1. Gateway build vs adopt (licence check pending).
2. Provider shortlist and in-region inference availability (UNVERIFIED).
3. Self-hosting triggers per [strategy 06](../strategy/06-model-strategy.md): not before they fire.

Plan IDs: PLT (gateway), OPR (agents, memory), DSC (interview prompts), QA (evals), SEC (injection tests).
