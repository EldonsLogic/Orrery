# Start here

Status: accepted
Owner: eldon

The platform (working name Orrery, not trademark-cleared) is an AI-native business platform for owner-led companies in the Middle East. One chat, in Arabic or English, interviews the owner, drafts a Blueprint, assembles an ERP from vetted components, simulates a month, then runs the business. We are a product company, not a software house.

## First 10 minutes
1. Read [AGENTS.md](../AGENTS.md) (rules for every agent and human).
2. Read [STATUS.md](STATUS.md) (generated: gate, progress, latest logs).
3. Read the latest 3 files in [log/](log/README.md), newest first.
4. Pick a `todo` row in [PLAN.md](PLAN.md) whose dependencies are `done`.

## Map
| Need | Go to |
|---|---|
| What gate are we at, what is needed next | [GATES.md](GATES.md), [STATUS.md](STATUS.md) |
| All work items | [PLAN.md](PLAN.md) |
| Why we decided X | [decisions/INDEX.md](decisions/INDEX.md), [strategy/decisions.md](strategy/decisions.md) |
| What could go wrong | [risks.md](risks.md) |
| Unresolved questions | [open-questions.md](open-questions.md) |
| Evidence and market | [research/](research/01-competitors.md) and [strategy/](strategy/01-gaps-and-risks.md) |
| Product, architecture, contracts, security, compliance, legal | `docs/product/`, `docs/architecture/`, `contracts/`, `docs/security/`, `docs/compliance/`, `docs/legal/` (written by other tasks; empty until populated) |
| Which model for which job | [agents/routing.md](../agents/routing.md) |
| Terms | [glossary.md](glossary.md) |
| What changed | [CHANGELOG.md](CHANGELOG.md) |

## Five parts and four contracts
Parts: 1 Discovery, 2 Blueprint and Library (the spine), 3 ERP Runtime (Frappe + ERPNext), 4 Operate (the chat after go-live), 5 Platform (tenants, identity, billing, AI gateway, team console). Contracts: Blueprint schema, Component manifest, Tool API, Event stream. Decision: [ADR-0003](decisions/ADR-0003-five-parts-four-contracts.md).

## Rules that bite
- No client-specific code. Configuration over code.
- Ledger, tax, e-invoicing, payroll maths are deterministic, never AI-written.
- Every session ends with a log file and an updated PLAN. No log, no merge.
- Colours come from design tokens only.
