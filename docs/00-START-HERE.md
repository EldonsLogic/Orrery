# Start here

Status: accepted
Owner: eldon

The platform (working name Orrery, not trademark-cleared) is an AI-native business platform for owner-led companies in Saudi Arabia, the UAE and Egypt. One chat, in Arabic or English, interviews the owner, drafts a Blueprint, assembles an ERP from vetted components, simulates a month, then runs the business and changes it through the same chat. We are a product company, not a software house. Two founders work here in parallel with different AI tools.

## First 10 minutes (any agent, any tool)
1. Read [AGENTS.md](../AGENTS.md), then [RULES.md](RULES.md) (every standing founder rule).
2. Read [STATUS.md](STATUS.md) (generated: gate, what is built, what is ready to start) and the latest 3 files in [log/](log/README.md), newest first.
3. Take a row from "Ready to start" in STATUS.md or a `todo` row in [PLAN.md](PLAN.md) whose dependencies are `done`. Claim it (`doing` plus owner), work on a branch named with its plan ID.
4. Delegate scoped sub-tasks by model tier: [agents/delegation-playbook.md](../agents/delegation-playbook.md) (it also holds a paste-ready starter prompt).
5. Finish with a log file, updated PLAN, regenerated STATUS, passing checks, a pushed branch and a PR. Do not merge your own PR.

## What exists today
| Area | State | Where |
|---|---|---|
| Repo, rules, CI, checks, agent roles | Done | [AGENTS.md](../AGENTS.md), [RULES.md](RULES.md), `.github/`, `scripts/`, `agents/` |
| Decisions | ADR-0001 to ADR-0016 (partner review pending; ADR-0007 identity Proposed) | [decisions/](decisions/INDEX.md) |
| Contracts | Blueprint schema v0 (with locale, country pack and branding) and example, Component manifest schema v0, Tool API, Events, Connector interface, Build states: specifications only; no validator or compiler yet | `contracts/` |
| Specs and architecture | Five part specs; overview, tenancy and identity, data, AI layer, engine adapter, change engine, component library, theming, country packs, calendars | `docs/specs/`, `docs/architecture/` |
| Product, security, compliance, legal | Written as plans and rules (website, post-sign-in screens, journey, threat model, hosting rules, country matrix incl. Egypt, legal checklist) | `docs/product/`, `docs/security/`, `docs/compliance/`, `docs/legal/` |
| Research and strategy | Evidence with caveats; strategy figures are hypotheses | `docs/research/`, `docs/strategy/` |
| Design system | Brand guidelines v1 (Quadrant), PROPOSED v1.1 additions, tenant theming derivation with tests, logo set with outlined wordmark; logo is a placeholder until the name is cleared | `docs/brand/` |
| Change engine module | Guarded apply layer (guardrails, DDL plan gate, audited deploy, rollback, workflow and report validators, runtime policies); 74 standalone tests pass; roles from session only; policy persistence and real-bench CI still open | `apps/engine/change_engine/` |
| Everything else | Not built: engine bench and tenant creation, Blueprint validator and compiler, ZATCA, Discovery, Operate and Platform services, the web app and marketing site, connectors, components, evals, infrastructure | `services/`, `web/`, `connectors/`, `components/`, `evals/`, `infra/` (placeholders) |

## The path, in order (plan IDs in [PLAN.md](PLAN.md); gates in [GATES.md](GATES.md))
- **G0 Foundation (now):** branch protection and partner access (GOV-008, GOV-009), pre-commit on both machines (GOV-010), fill the model registry (GOV-012), partner reviews the ADRs (GOV-013), founders' agreement and licence policy (LEG-001, LEG-002), counsel engaged for KSA, UAE and Egypt (LEG-003), decide identity (PLT-002), finish policy persistence (CE-SEC-003).
- **G1 Spine proven:** pin versions and stand up a real bench (ERP-001), scripted tenant creation (ERP-003), Blueprint validator, compiler, diff, apply and rollback (BPL-003 to BPL-008), engine adapter (BPL-012, ERP-012), ZATCA invoice through the sandbox and an Arabic bilingual PDF (CMP-002 to CMP-004, ERP-007), Arabic eval set and model bake-off (QA-002, QA-003), engine invisibility at the gateway (ERP-020, PLT-024, QA-016), interviews with owners and accountants (GTM-002), identity decision (BRD-003).
- **G2 Pilot-ready:** Discovery with template-first drafts and connectors (DSC-004 to DSC-014), the one chat and tool API (OPR-001 to OPR-012), tenants, identity, plans, metering and the AI gateway (PLT-003 to PLT-021), component factory and simulator (BPL-014 to BPL-023), web app and tenant branding (WEB-003 to WEB-012, BRD-004 to BRD-010), Pilot A (GTM-005, GTM-006).
- **G3 Paying-customer-ready:** security baseline, tested backups and restore, billing, legal documents, support process, independent penetration test.
- **G4 Repeatable, G5 Scale:** autonomy and reuse targets met; second market, self-serve gating, certifications.

## Map
| Need | Go to |
|---|---|
| Gate, progress, what to do next | [GATES.md](GATES.md), [STATUS.md](STATUS.md) |
| All work items | [PLAN.md](PLAN.md) |
| Standing founder rules | [RULES.md](RULES.md) |
| Why we decided X | [decisions/INDEX.md](decisions/INDEX.md), [strategy/decisions.md](strategy/decisions.md) |
| What could go wrong | [risks.md](risks.md) |
| Unresolved questions | [open-questions.md](open-questions.md) |
| Architecture | [architecture/overview.md](architecture/overview.md), [specs/](specs/01-discovery.md), `contracts/` |
| Product, website, screens | [product/PRD.md](product/PRD.md), [product/website.md](product/website.md), [product/app-screens.md](product/app-screens.md) |
| Security, hosting rules | [security/hosting-rules.md](security/hosting-rules.md), [security/threat-model.md](security/threat-model.md) |
| Compliance per country | [compliance/country-matrix.md](compliance/country-matrix.md) |
| Brand and design system | [brand/README.md](brand/README.md) |
| Which model for which job | [../agents/routing.md](../agents/routing.md), [../agents/delegation-playbook.md](../agents/delegation-playbook.md) |
| Terms | [glossary.md](glossary.md) |

## Five parts and four contracts
Parts: 1 Discovery, 2 Blueprint and Library (the spine), 3 ERP Runtime, 4 Operate (the chat after go-live), 5 Platform (tenants, identity, billing, AI gateway, team console). Contracts: Blueprint schema, Component manifest, Tool API, Event stream. Decision: [ADR-0003](decisions/ADR-0003-five-parts-four-contracts.md).
