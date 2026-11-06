# 03 - What "AI-native" means for us, and the moat

Date: 2026-11-04.

## Definition (testable, investor-proof)
We are AI-native if the product's core job is impossible without models, and everything the models do is bounded, reviewable and reversible.

**Five properties (each is demonstrable in a demo and measurable):**
1. **Conversation compiles to a typed Blueprint.** The interview output is a versioned, schema-validated JSON "Blueprint" (entities, workflows, roles, approvals, reports, integrations, compliance profile). Not free text, not generated code.
2. **Configuration, not code.** The compiler maps the Blueprint onto a library of pre-built, pre-certified components and per-tenant configuration. Per-client code is forbidden (see `08`).
3. **Every change is a diff.** Any chat request ("add a 2% early payment discount", "new approval for orders over SAR 50k") becomes a Blueprint diff, simulated against the tenant's own history, shown in plain Arabic/English, approved by a human, applied atomically and reversible.
4. **Agents act within scoped permissions.** Agents draft and propose (invoices, reminders, reconciliations, purchase suggestions); posting to the ledger, tax filings and payroll runs need human approval. Every agent action is logged with inputs, model version and approver.
5. **Evals are a product asset.** An Arabic/English evaluation set and a replay-simulation harness gate every model or prompt change. We can state autonomy and accuracy numbers at any time.

**Not AI-native (what investors have seen too often):** a chat widget that queries an ERP; AI that writes arbitrary code into a client's instance; "AI-powered" labels on OCR. Test: remove the LLM; if the product still configures itself, it was a bolted-on chat. If the owner cannot get from blank to go-live without our team typing, we are a software house with a chatbot.

**Where models are actually load-bearing:** interview-to-blueprint, source-ERP mapping and migration, Blueprint diffing/explanation, month-of-business simulation test generation, document understanding, repetitive-work agents. Everything else stays deterministic.

## Investor-facing metrics that prove it
- Platform Autonomy Rate (share of a client Blueprint produced without human edits), target path in `08`.
- Human hours per go-live, time to go-live, component reuse ratio.
- Inference cost per tenant per month and gross margin including it (`06`).
- Arabic eval pass rate per release.

## Moat (honest ranking; at zero clients, a moat is a plan)
| Candidate | Strength today | Strength at 20 clients | Copyable by funded locals? |
|---|---|---|---|
| **Certified component library + regulatory change pipeline** (ZATCA waves, UAE e-invoicing, WPS/GOSI updates shipped to all tenants) | Low (we have nothing) | High: every wave we ship once and all tenants get it | Yes over 12-24 months; Wafeq, Rewaa, Foodics have capital |
| **Blueprint schema + compiler + simulation harness** | Medium (design is ours) | High: a hard-to-copy engineering stack | Slowly |
| **Corpus: real Blueprints, migration mappings, Arabic eval cases from paid clients** | None | High: every build adds data competitors lack | Not without our customers |
| **Distribution: accountants and implementers as channel, plus AI accelerator for partners** | None | Medium | Yes, but partners tend to be exclusive-ish |
| **System-of-record switching costs** | None | Medium | n/a |
| The model, the open-source engine, the chat UI | **Not a moat** | Not a moat | Trivial |

**Position to defend with investors:** the moat is the compounding loop (every implementation adds components, mappings and eval cases that make the next one cheaper and safer) plus regulatory freshness. That is only true if the metrics in `08` improve; if they do not, we are a software house and should say so.

**Engine independence is a design goal:** the Blueprint is the asset, the engine (Frappe/ERPNext, see `04`) is replaceable behind an adapter. This also answers the GPL/seed risk.
