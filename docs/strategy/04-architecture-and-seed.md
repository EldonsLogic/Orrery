# 04 - Architecture and seed choice

Date: 2026-11-04. Basis: `docs/research/04-open-source.md` (licence files read by the research agent). Status: RECOMMENDATION, subject to a 2-week spike. No application code yet.

## Seed verdict
**Seed: Frappe Framework (MIT) + ERPNext core (GPL-3) as the rigid engine, run as SaaS-only and undistributed; everything we differentiate on lives outside the engine, in our own proprietary layers.** I partly overturn the research agent's #1 ("build a thin engine of our own") and keep the brief's Frappe hypothesis with changes.

Why not build our own ledger/tax/payroll engine: months of work, accounting bugs are existential, two founders using AI coding tools will ship plausible-but-wrong GL code, and we would be re-implementing what ERPNext has hardened for 10+ years (real double-entry GL, consolidation, multi-currency, stock; 04 §4.4). Speed to a compliant pilot matters more than purity.

Why the agent's objections to Frappe are manageable:
| Objection | Assessment |
|---|---|
| GPL-3 on ERPNext/HRMS | No network clause. SaaS use does not force source release (04 §1). Problem only if we ship the engine to customers (on-prem/hybrid). Mitigation: keep our AI layer, compiler, UI and control plane as separate services talking over REST/MCP, not linked into the GPL process; do not distribute. Counsel to confirm. |
| ERPNext trademark | Do not use "ERPNext" in product, domain or ads. We are not rebranding their product, we are a different product. |
| Site-per-tenant DB | Not a defect for our customers: gives clean isolation, per-tenant export/backup, per-region placement (helps PDPL). Cost: ops (migrations per site). Frappe Cloud shows it runs at scale; our scale is small for years. Redefine "one shared engine" as "one codebase and library" (`01`). |
| HRMS Arabic 33%, no GOSI/WPS found | Real gap. Use only payroll skeleton; build KSA/UAE payroll as our own certified component later (second niche). v1 niche does not need payroll depth. |
| AGPL ZATCA app (lavaloon) | Do not use. Use ERPGulf MIT app as the base (04 §4.5), tested against ZATCA's sandbox in the spike. |
| flow/MCP on `develop` only | Do not depend on it. Our AI layer calls REST/whitelisted methods; adopt Frappe's MCP only if it lands in a stable release. |
| Version mismatch | Research shows Frappe v16.55.2 but ERPNext v15.124.5 and HRMS v15.64.8 as latest releases. Pin one consistent, supported set (likely v15) and verify in the spike. |

Rejected: Odoo Community (advanced accounting reportedly Enterprise-only, hostile owner, not metadata-first), Open Mercato (no GL, no Arabic, vendor sells the agent layer, `sayegh9` fork is an unmodified mirror), Twenty (CRM only, AGPL+enterprise files; borrow MIT `twenty-ui` ideas only), NocoBase (licence forbids our business even when paid), n8n/NocoDB/Invoice Ninja/Akaunting (cannot be hosted as a service). Reusable around the engine: Activepieces core (MIT) for tenant automations, Frappe Builder (MIT), ERPGulf ZATCA (MIT), Blnk (Apache) only if a separate ledger primitive is needed.

## Layers
```
L5 Control plane   tenant provisioning, billing, usage metering, observability, admin
L4 Interface       Arabic-first chat + role-based simple views (own web app, RTL, i18n); not Frappe Desk
L3 AI layer        interviewer, source-ERP mapper, planner, simulator, ops agents; model gateway + evals
L2 Blueprint       typed schema + compiler + diff/apply/rollback + simulator
L1 Component lib   versioned, tested, certified packages (DocTypes, workflows, roles, print formats, reports)
L0 Engine          Frappe + ERPNext (ledger, tax, stock, selling, buying), ZATCA component
```
- **Rigid zone (never AI-written):** ledger posting, tax, ZATCA/UAE invoice generation, payroll calculation, audit trail.
- **Configurable zone (AI composes from L1):** custom fields, workflows, approvals, roles, print formats, dashboards, notifications, role views.
- **Quarantine zone:** a request no component covers becomes a candidate component: written once, reviewed by a human, tested, added to L1 for everyone. Never a per-client patch (`08`).

## Engine adapter
L2 compiles the Blueprint to a neutral intermediate form, then an adapter emits Frappe fixtures/Custom Fields/Workflows. If GPL, scale or maintenance forces a change, we swap the adapter, not the product. This is the escape hatch that makes the seed decision reversible.

## Multi-language
All user-facing strings through one i18n layer with keys; Arabic and English first; the model produces labels in the tenant's language; adding a language = translation pack + eval set + RTL/LTR check. Glossary at `docs/glossary.md` feeds prompts.

## Two-week spike (feeds Phase 4's 90-day plan)
1. Stand up pinned Frappe+ERPNext, add ERPGulf ZATCA, run against ZATCA sandbox: onboarding, standard and simplified invoices, credit note.
2. Compile a hand-written Blueprint for a toy trading company into fixtures; apply, diff, roll back.
3. Arabic/bilingual invoice PDF with Hijri date and QR (PDF Arabic shaping is a known risk; UNVERIFIED).
4. 50 empty tenants on one bench: provisioning time, migration time, memory.
5. Arabic eval v0 (100 prompts) through two model families.
6. Read-only extractor against an Odoo test instance (Pilot B shape).
Exit: go / no-go on the seed, with a written cost of switching adapters.

## Founder collaboration constraint
Repo on GitHub; the Blueprint schema, component library and eval set are the shared core, so both founders (different models) work from contracts and tests, not from each other's prompts. See `docs/strategy/09-original-ideas-verdicts.md` for the workflow verdict.
