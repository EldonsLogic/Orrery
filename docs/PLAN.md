# Master plan

Status: accepted
Owner: eldon

This table is the single list of work. Order is by dependency and gates, not by date. Gates are defined in [GATES.md](GATES.md). Rules:
- One row per task. IDs are permanent; never reuse one. Add new rows at the end of their prefix block.
- Status is one of `todo`, `doing`, `done`, `blocked`. Owner is `eldon`, `partner` or `unassigned`.
- Pick a `todo` row whose `Depends` are all `done`. Set it to `doing` with an owner in the same PR that starts the work.
- A row is `done` only when its output is merged and linked from the session log.
- `scripts/check_docs.py` parses this table; keep the 7 columns and the ID format `PREFIX-NNN`.

Prefixes: GOV governance and workflow, LEG legal and company, SEC security, DAT data, CMP compliance, BPL Blueprint and library (Part 2), DSC discovery (Part 1), ERP runtime (Part 3), OPR operate (Part 4), PLT platform (Part 5), INF infrastructure, BRD brand and design system, WEB marketing site and app screens, QA quality, GTM go-to-market, FND fundraising. CE-SEC is the change-engine security series.

| ID | Item | Part | Gate | Depends | Owner | Status |
|---|---|---|---|---|---|---|
| GOV-001 | Private GitHub repo exists (EldonsLogic/Orrery) | Governance | G0 | - | eldon | done |
| GOV-002 | Create GitHub organisation, transfer repo, decide final repo name | Governance | G0 | GOV-001 | eldon | todo |
| GOV-003 | Rewrite AGENTS.md, CLAUDE.md, GEMINI.md as canonical agent rules | Governance | G0 | GOV-001 | eldon | done |
| GOV-004 | Docs skeleton: START-HERE, PLAN, GATES, STATUS, logs, ADR folder | Governance | G0 | GOV-003 | eldon | done |
| GOV-005 | Docs scripts: check_docs, build_status, new_log, session_start, scan_secrets | Governance | G0 | GOV-004 | eldon | done |
| GOV-006 | CI workflow: docs gate, secret scan, PR log gate | Governance | G0 | GOV-005 | eldon | done |
| GOV-007 | First green CI run on GitHub after bootstrap push | Governance | G0 | GOV-006 | eldon | done |
| GOV-008 | Branch protection on main: PRs only, required checks, no force push, admins included (done via public repo, ADR-0021) | Governance | G0 | GOV-007 | eldon | done |
| GOV-009 | Add partner (sayegh9) as admin; confirm CODEOWNERS review works | Governance | G0 | GOV-002 | eldon | done |
| GOV-010 | Install pre-commit hooks on both founders' machines | Governance | G0 | GOV-005 | unassigned | todo |
| GOV-011 | Agent role specs, routing rules, model registry | Governance | G0 | GOV-003 | eldon | done |
| GOV-012 | Fill model registry rows for Codex and Antigravity | Governance | G0 | GOV-011 | partner | todo |
| GOV-013 | Partner reviews ADR-0001..0014 and strategy decisions D-P2-1..11 | Governance | G0 | GOV-009 | partner | todo |
| GOV-014 | Trial the cross-model PR review routine on the first real PR | Governance | G0 | GOV-008 | unassigned | todo |
| GOV-015 | Draft ADR-0001..0014 | Governance | G0 | GOV-004 | eldon | done |
| GOV-016 | Autonomy metrics file and monthly reporting template (strategy/08) | Governance | G1 | GOV-004 | unassigned | todo |
| GOV-017 | Exceptions register process (every manual step logged with reason) | Governance | G2 | GOV-016 | unassigned | todo |
| GOV-018 | Retire docs/HANDOFF.md in favour of docs/log and STATUS | Governance | G0 | GOV-004 | eldon | done |
| GOV-019 | Pick issue/PR labels and project board mapping to PLAN IDs | Governance | G0 | GOV-008 | unassigned | todo |
| GOV-020 | Periodic plan review: re-rank, close stale rows, check gate criteria | Governance | G1 | GOV-016 | unassigned | todo |
| GOV-021 | Repo hygiene checker and strict two-person and file-placement rules (AGENTS.md, scripts/check_repo_hygiene.py, CI) | Governance | G0 | GOV-004 | eldon | done |
| GOV-022 | Onboarding guide with one-time setup, founder lanes, first tasks and pending decisions (docs/ONBOARDING.md) | Governance | G0 | GOV-004 | eldon | done |
| GOV-023 | Task-trail gate in CI (log has valid plan IDs, rows not left todo when code changes) and per-founder queues in STATUS | Governance | G0 | GOV-006 | eldon | done |
| GOV-024 | Enforcement layers: commit-msg and pre-push hooks, finish_session gate, main-guard audit workflow, ADR-0019 | Governance | G0 | GOV-023 | eldon | done |
| GOV-025 | Lane guard: scripts/lanes.json and check_lanes.py in CI, pre-push and finish_session; cross-lane waiver in the session log (ADR-0020) | Governance | G0 | GOV-024 | eldon | done |
| GOV-026 | Public repo with branch protection, secret scanning, outsider limits (ADR-0021) | Governance | G0 | GOV-008 | eldon | done |
| GOV-027 | Repo is public only for a while (founder, 2026-11-07): before switching back to private, decide the GitHub plan, because branch protection needs a paid plan on a private repo; forks and caches of anything published stay public | Governance | G2 | GOV-008 | eldon | todo |
| GOV-028 | Cloud-session support: gh-optional finish gate, founder detection fallbacks, CI check that every commit names a plan ID, cloud guidance in onboarding | Governance | G0 | GOV-024 | eldon | done |
| GOV-029 | One personal GitHub account per founder in lanes, owners and docs; recover unmerged work (ADR-0023) | Governance | G0 | GOV-028 | eldon | done |
| LEG-001 | Founders' agreement: roles, equity, decision rights, IP assignment incl. partner prototype | Legal | G0 | - | eldon | todo |
| LEG-002 | Add LICENSE file policy (proprietary, all rights reserved) and per-folder licence notes (interim LICENSE added; counsel to finalise) | Legal | G0 | GOV-004 | eldon | doing |
| LEG-003 | Engage counsel in KSA, UAE and Egypt; scope of work | Legal | G0 | - | eldon | todo |
| LEG-004 | Third-party licence register (every adopted OSS component, version, licence; partner first lists every Frappe or ERPNext app and add-on used locally) | Legal | G0 | GOV-004 | partner | todo |
| LEG-005 | Register domains and social handles for the working name (hold only) | Legal | G0 | - | eldon | todo |
| LEG-006 | GPL licence-boundary review: SaaS-only engine, separate services, no distribution | Legal | G1 | LEG-003 | unassigned | todo |
| LEG-007 | Counsel opinion: vendor certification needed to sell ZATCA-compliant software | Legal | G1 | LEG-003 | unassigned | todo |
| LEG-008 | Name clearance: trademark search and counsel opinion (KSA, UAE, Egypt, international) | Legal | G1 | LEG-003 | unassigned | todo |
| LEG-009 | Trademark policy check: no ERPNext or Frappe in product name or ads | Legal | G1 | LEG-006 | unassigned | todo |
| LEG-010 | Company entity decision (KSA, UAE, Egypt, or several) and incorporation | Legal | G2 | LEG-003,LEG-001 | eldon | todo |
| LEG-011 | UAE entity serving KSA clients: counsel review | Legal | G2 | LEG-010 | unassigned | todo |
| LEG-012 | Counsel opinion: PDPL cross-border processing by LLM providers | Legal | G2 | LEG-003 | unassigned | todo |
| LEG-013 | Customer contract template: fixed setup, anonymised-reuse clause, IP clause, no free pilots | Legal | G2 | LEG-010 | unassigned | todo |
| LEG-014 | Contractor and employee agreements; AI-tool confidentiality policy | Legal | G2 | LEG-010 | unassigned | todo |
| LEG-015 | Terms of service, privacy policy, data processing agreement | Legal | G3 | LEG-012,LEG-013 | unassigned | todo |
| LEG-016 | Insurance: professional indemnity and cyber | Legal | G3 | LEG-010 | unassigned | todo |
| LEG-017 | Hybrid or on-prem distribution legal review (GPL) | Legal | G5 | LEG-006 | unassigned | todo |
| LEG-018 | Counsel: is any customer-visible open-source notice required for the engine in a SaaS (single allowed exception to ADR-0016)? | Legal | G1 | LEG-006 | unassigned | todo |
| CE-SEC-001 | Change engine: stop accepting caller-supplied roles from request kwargs on whitelisted endpoints | Security | G0 | BPL-001 | partner | done |
| CE-SEC-002 | Change engine: role lookup must fail closed, never fall back to System Manager on error | Security | G0 | BPL-001 | partner | done |
| CE-SEC-003 | Change engine: permission check on runtime-policy registration; persist policies per site, not in process memory | Security | G0 | BPL-001 | partner | doing |
| CE-SEC-004 | Change engine: LLM test-connection endpoint must not accept client-supplied API key or base URL | Security | G0 | BPL-001 | partner | done |
| CE-SEC-005 | Change engine: CI against a real Frappe bench instead of mocks | Security | G1 | BPL-001,ERP-001 | partner | todo |
| SEC-001 | Threat model for the five parts and four contracts | Security | G1 | GOV-015 | eldon | done |
| SEC-002 | Secrets management design (store, rotate, never in repo) | Security | G1 | SEC-001 | unassigned | todo |
| SEC-003 | Prompt-injection defence design: untrusted-content tagging, tool allowlists, no instruction following from data | Security | G1 | SEC-001 | unassigned | todo |
| SEC-004 | Cross-tenant isolation test suite | Security | G1 | ERP-003 | unassigned | todo |
| SEC-005 | MFA for owners, staff and support access | Security | G2 | PLT-005 | unassigned | todo |
| SEC-006 | Brand asset upload security: PNG/JPG/SVG only, size limits, SVG sanitiser, malware scan, per-tenant storage | Security | G2 | PLT-017 | unassigned | todo |
| SEC-007 | Dependency and SBOM scanning for Python and Node (beyond dependabot actions) | Security | G2 | GOV-006 | unassigned | todo |
| SEC-008 | Audit log integrity: append-only, hash-chained, exported off-box | Security | G2 | PLT-015 | unassigned | todo |
| SEC-009 | Rate limits and abuse controls on chat and gateway | Security | G2 | PLT-009 | unassigned | todo |
| SEC-010 | Sandbox and static analysis for factory-built components | Security | G2 | BPL-015 | unassigned | todo |
| SEC-011 | Encryption at rest and in transit; per-tenant key management | Security | G3 | INF-005 | unassigned | todo |
| SEC-012 | Security baseline checklist for paying customers | Security | G3 | SEC-004,SEC-008 | unassigned | todo |
| SEC-013 | Incident response plan and PDPL breach notification process | Security | G3 | LEG-012 | unassigned | todo |
| SEC-014 | Red-team of agents: injection via uploaded documents and connectors | Security | G3 | QA-006 | unassigned | todo |
| SEC-015 | Egress and credential controls for the isolated browser runner | Security | G4 | INF-009 | unassigned | todo |
| SEC-016 | Independent penetration test | Security | G3 | SEC-012 | unassigned | todo |
| SEC-017 | Security certification readiness (ISO 27001 or SOC 2; pick one with counsel) | Security | G5 | SEC-016 | unassigned | todo |
| DAT-001 | Data classification and retention policy | Data | G1 | SEC-001 | unassigned | todo |
| DAT-002 | Anonymised sample datasets for dev, demos and evals (no real customer data) | Data | G1 | - | unassigned | todo |
| DAT-003 | Data residency map: what is stored where, which model region sees what | Data | G2 | DAT-001,INF-001 | unassigned | todo |
| DAT-004 | Per-tenant backups and point-in-time restore | Data | G3 | INF-005 | unassigned | todo |
| DAT-005 | Restore drills with timed results | Data | G3 | DAT-004 | unassigned | todo |
| DAT-006 | Tenant export in an open format | Data | G3 | PLT-004 | unassigned | todo |
| DAT-007 | Tenant deletion with verification and certificate | Data | G3 | PLT-004 | unassigned | todo |
| DAT-008 | Anonymisation pipeline for promoting generalised patterns across tenants | Data | G4 | DAT-001,LEG-013 | unassigned | todo |
| DAT-009 | Synthetic data generator for dev, demos and previews (no real data; ADR-0018) | Data | G1 | DAT-002 | unassigned | todo |
| CMP-001 | Re-verify UNVERIFIED regulation rows in research/03 against official sources | Compliance | G1 | LEG-003 | unassigned | todo |
| CMP-002 | Evaluate ERPGulf ZATCA app: licence, Phase 2 coverage, maintenance | Compliance | G1 | ERP-001 | partner | todo |
| CMP-003 | ZATCA Phase 1 invoice generation (QR, mandatory fields) | Compliance | G1 | CMP-002 | partner | todo |
| CMP-004 | ZATCA Phase 2 invoice passes ZATCA sandbox (signing, hash chain, clearance and reporting) | Compliance | G1 | CMP-003 | partner | todo |
| CMP-005 | Hijri date support in fields, display and print | Compliance | G1 | ERP-001 | unassigned | todo |
| CMP-006 | KSA chart of accounts template and tax codes | Compliance | G1 | ERP-001 | unassigned | todo |
| CMP-007 | ZATCA onboarding automation per tenant (CSID, certificates, environments) | Compliance | G2 | CMP-004,PLT-003 | unassigned | todo |
| CMP-008 | ZATCA regression suite run on every engine or component change | Compliance | G2 | CMP-004,QA-001 | unassigned | todo |
| CMP-009 | UAE e-invoicing: choose accredited service provider | Compliance | G2 | CMP-001 | unassigned | todo |
| CMP-010 | KSA VAT return report | Compliance | G2 | CMP-006 | unassigned | todo |
| CMP-011 | UAE e-invoicing integration via the chosen provider | Compliance | G3 | CMP-009 | unassigned | todo |
| CMP-012 | UAE VAT return report | Compliance | G3 | CMP-011 | unassigned | todo |
| CMP-013 | Zakat report | Compliance | G3 | CMP-010 | unassigned | todo |
| CMP-014 | UAE corporate tax report | Compliance | G3 | CMP-012 | unassigned | todo |
| CMP-015 | Payroll with WPS file output (KSA, then UAE) | Compliance | G3 | ERP-010 | unassigned | todo |
| CMP-016 | GOSI contribution calculation and reporting | Compliance | G3 | CMP-015 | unassigned | todo |
| CMP-017 | PDPL programme: records of processing, consent, subject requests, DPO decision | Compliance | G3 | LEG-012 | unassigned | todo |
| CMP-018 | NCA controls applicability review | Compliance | G3 | CMP-001 | unassigned | todo |
| CMP-019 | Review of Saudi AI and data-hosting rules that affect the gateway and hosting | Compliance | G1 | CMP-001 | unassigned | todo |
| CMP-020 | Regulation change watcher feeding versioned compliance components | Compliance | G4 | CMP-008 | unassigned | todo |
| BPL-001 | Import the prototype change engine into apps/engine as the change-engine module (renamed) | Blueprint | G0 | LEG-001 | partner | done |
| BPL-002 | Blueprint schema v0 in contracts/ | Blueprint | G1 | GOV-015 | eldon | done |
| BPL-003 | Blueprint validator | Blueprint | G1 | BPL-002 | eldon | done |
| BPL-004 | Compiler: Blueprint to engine configuration | Blueprint | G1 | BPL-003,ERP-012 | eldon | todo |
| BPL-005 | Hand-written trading and distribution Blueprint fixture | Blueprint | G1 | BPL-002 | eldon | done |
| BPL-006 | Blueprint diff | Blueprint | G1 | BPL-003 | eldon | todo |
| BPL-007 | Apply with preview and DDL plan gate (change engine) | Blueprint | G1 | BPL-004,BPL-001 | partner | todo |
| BPL-008 | Rollback to a previous Blueprint version | Blueprint | G1 | BPL-007 | partner | todo |
| BPL-009 | Component manifest schema v0 in contracts/ | Blueprint | G1 | GOV-015 | eldon | done |
| BPL-010 | Component registry (list, version, compatibility) | Blueprint | G1 | BPL-009 | eldon | done |
| BPL-011 | Event stream contract implementation | Blueprint | G1 | BPL-002 | eldon | todo |
| BPL-012 | Engine adapter interface so the engine stays replaceable | Blueprint | G1 | GOV-015 | partner | todo |
| BPL-013 | Branding section in the Blueprint schema (ADR-0014) | Blueprint | G1 | BPL-002 | unassigned | done |
| BPL-014 | Component certification levels and test harness | Blueprint | G2 | BPL-010 | unassigned | todo |
| BPL-015 | Component factory sandbox: build and test components in isolation | Blueprint | G2 | BPL-014 | unassigned | todo |
| BPL-016 | Component request pipeline: gap to AI-drafted request with spec and tests | Blueprint | G2 | BPL-014,DSC-006 | unassigned | todo |
| BPL-017 | Factory: AI drafts component code and tests from a request | Blueprint | G2 | BPL-015,PLT-009 | unassigned | todo |
| BPL-018 | Simulator: replay a month of the owner's data on the compiled tenant | Blueprint | G2 | BPL-007,DSC-010 | unassigned | todo |
| BPL-019 | Simulation report: expected versus actual, anomalies, owner sign-off view | Blueprint | G2 | BPL-018 | unassigned | todo |
| BPL-020 | Build state machine draft to live, with the human gate | Blueprint | G2 | BPL-007,PLT-013 | unassigned | todo |
| BPL-021 | Blueprint versioning and schema migration | Blueprint | G2 | BPL-006 | unassigned | todo |
| BPL-022 | Reuse metrics and Platform Autonomy Rate computation | Blueprint | G2 | BPL-010,GOV-016 | unassigned | todo |
| BPL-023 | Exceptions register tooling | Blueprint | G2 | GOV-017 | unassigned | todo |
| BPL-024 | Promotion of generalised patterns into the library | Blueprint | G4 | DAT-008,BPL-016 | unassigned | todo |
| DSC-001 | Interview protocol v0, Arabic and English | Discovery | G1 | GTM-002 | eldon | todo |
| DSC-002 | Template Blueprint: trading and distribution | Discovery | G1 | BPL-005 | eldon | done |
| DSC-003 | Connector interface spec and tier definitions | Discovery | G1 | GOV-015 | unassigned | done |
| DSC-004 | Template-first discovery flow: show draft, owner corrects | Discovery | G2 | DSC-002,OPR-010 | unassigned | todo |
| DSC-005 | Interview agent in Arabic and English | Discovery | G2 | DSC-001,OPR-010 | unassigned | todo |
| DSC-006 | Gap analysis: Blueprint versus library | Discovery | G2 | BPL-010,DSC-004 | unassigned | todo |
| DSC-007 | Owner-readable visual Blueprint viewer | Discovery | G2 | BPL-003,WEB-003 | unassigned | todo |
| DSC-008 | Quote generator from Blueprint and gap analysis | Discovery | G2 | DSC-006 | unassigned | todo |
| DSC-009 | Owner approval flow (draft to owner_approved) | Discovery | G2 | DSC-007,BPL-020 | unassigned | todo |
| DSC-010 | Connector framework: tiers, sandboxing, audit, untrusted-content handling | Discovery | G2 | DSC-003,SEC-003 | unassigned | todo |
| DSC-011 | Excel and CSV import connector | Discovery | G2 | DSC-010 | unassigned | todo |
| DSC-012 | Odoo extractor: read-only API access, export mapping | Discovery | G2 | DSC-010 | unassigned | todo |
| DSC-013 | Odoo to Blueprint field-mapping library | Discovery | G2 | DSC-012 | unassigned | todo |
| DSC-014 | Document intake with Arabic OCR (invoices, receipts, photos) | Discovery | G2 | DSC-010,QA-002 | unassigned | todo |
| DSC-015 | Email and WhatsApp forwarding intake | Discovery | G3 | DSC-014 | unassigned | todo |
| DSC-016 | Accountant review view in discovery | Discovery | G3 | DSC-007 | unassigned | todo |
| DSC-017 | Owner-driven isolated read-only browser session (no stored credentials) | Discovery | G4 | DSC-010,SEC-015,INF-009 | unassigned | todo |
| DSC-018 | Second vertical template chosen from pilot evidence | Discovery | G4 | GTM-005 | unassigned | todo |
| ERP-001 | G1 spike: pin Frappe, ERPNext, HRMS versions (likely v15) and stand up a bench | Runtime | G1 | LEG-004 | partner | todo |
| ERP-002 | Spike: 50-tenant load test on one bench pool | Runtime | G1 | ERP-003 | partner | todo |
| ERP-003 | Scripted site-per-tenant creation | Runtime | G1 | ERP-001 | partner | todo |
| ERP-004 | Version pin and upgrade policy document | Runtime | G1 | ERP-001 | partner | todo |
| ERP-005 | Core module scope for trading and distribution (selling, buying, stock, accounts) | Runtime | G1 | ERP-001 | partner | todo |
| ERP-006 | Arabic and RTL translation completion for in-scope modules | Runtime | G1 | ERP-005 | partner | todo |
| ERP-007 | Bilingual tax invoice PDF print format | Runtime | G1 | CMP-003,ERP-006 | partner | todo |
| ERP-008 | Blueprint roles to engine roles and user permissions mapping | Runtime | G1 | BPL-002 | partner | todo |
| ERP-009 | Engine event emitter feeding the event stream | Runtime | G1 | BPL-011 | partner | todo |
| ERP-010 | HRMS skeleton: employees, leave, payroll structure, only what v1 needs | Runtime | G2 | ERP-005 | unassigned | todo |
| ERP-011 | Component pack v1 for trading and distribution (price lists, credit limits, rep commission) | Runtime | G2 | BPL-014,ERP-005 | unassigned | todo |
| ERP-012 | Frappe implementation of the engine adapter | Runtime | G1 | BPL-012,ERP-001 | partner | todo |
| ERP-013 | Opening balances and master data importer | Runtime | G2 | DSC-011 | unassigned | todo |
| ERP-014 | Accounting correctness property tests (ledger balances, tax, rounding) | Runtime | G1 | ERP-005,QA-001 | unassigned | todo |
| ERP-015 | Inventory valuation correctness tests | Runtime | G2 | ERP-014 | unassigned | todo |
| ERP-016 | Tenant-branded document templates: tax invoice, quote, PO, with compliance layout locked | Runtime | G2 | BRD-006,CMP-003,ERP-007 | unassigned | todo |
| ERP-017 | Branded email templates | Runtime | G3 | ERP-016 | unassigned | todo |
| ERP-018 | Component pack for a second vertical | Runtime | G4 | DSC-018 | unassigned | todo |
| OPR-001 | Agent runtime: loop, tool calls, traces, budgets | Operate | G2 | PLT-009 | unassigned | todo |
| OPR-002 | Intent router: discover, ask, act, change | Operate | G2 | OPR-001 | unassigned | todo |
| OPR-003 | Tool API generator: typed actions per tenant from the Blueprint | Operate | G2 | BPL-003 | unassigned | todo |
| OPR-004 | Tool permission enforcement with the caller's own role and scope | Operate | G2 | OPR-003,ERP-008 | unassigned | todo |
| OPR-005 | Confirm-before-write previews for chat actions | Operate | G2 | OPR-004 | unassigned | todo |
| OPR-006 | Semantic layer for metrics | Operate | G2 | BPL-003,ERP-009 | unassigned | todo |
| OPR-007 | Approval inbox backend | Operate | G2 | OPR-004 | unassigned | todo |
| OPR-008 | Report builder | Operate | G2 | OPR-006 | unassigned | todo |
| OPR-009 | Change-by-chat through the Blueprint path | Operate | G2 | OPR-002,BPL-007 | unassigned | todo |
| OPR-010 | Chat service: sessions, streaming, Arabic and English | Operate | G2 | OPR-001 | unassigned | todo |
| OPR-011 | Role-based view generation (screens and tools per role) | Operate | G2 | OPR-003,WEB-011 | unassigned | todo |
| OPR-012 | Chat transcript audit and retention | Operate | G2 | SEC-008,DAT-001 | unassigned | todo |
| OPR-013 | Scheduled agents with budgets | Operate | G3 | OPR-001,PLT-021 | unassigned | todo |
| OPR-014 | Per-tenant memory | Operate | G3 | OPR-001,DAT-001 | unassigned | todo |
| OPR-015 | WhatsApp or push channel for the chat | Operate | G4 | OPR-010,DSC-015 | unassigned | todo |
| PLT-001 | Tenancy ADR-0006: site per tenant on shared in-country infrastructure | Platform | G0 | GOV-015 | eldon | done |
| PLT-002 | Identity ADR-0007: decide central identity with per-tenant roles | Platform | G0 | GOV-015 | eldon | doing |
| PLT-003 | Tenant provisioning service | Platform | G1 | ERP-003,PLT-001 | unassigned | todo |
| PLT-004 | Tenant lifecycle states: trial, active, suspended, exported, deleted | Platform | G2 | PLT-003 | unassigned | todo |
| PLT-005 | Identity service (users, sessions, per-tenant roles) | Platform | G2 | PLT-002 | unassigned | todo |
| PLT-006 | Plans and entitlements model, everything unlocked at first | Platform | G2 | PLT-004 | unassigned | todo |
| PLT-007 | Usage metering for AI actions, storage, users | Platform | G2 | PLT-006,BPL-011 | unassigned | todo |
| PLT-008 | Billing and payments for our subscriptions | Platform | G3 | PLT-007,LEG-010 | unassigned | todo |
| PLT-009 | AI model gateway: routing, budgets, caching, logs | Platform | G2 | QA-003 | unassigned | todo |
| PLT-010 | Gateway regional routing and provider fallback | Platform | G3 | PLT-009,CMP-019 | unassigned | todo |
| PLT-011 | Per-tenant AI cost attribution and caps | Platform | G2 | PLT-009,PLT-007 | unassigned | todo |
| PLT-012 | Internal team console | Platform | G2 | PLT-005 | unassigned | todo |
| PLT-013 | Human review queue (team_reviewed gate) | Platform | G2 | PLT-012 | unassigned | todo |
| PLT-014 | Component factory review screens | Platform | G2 | PLT-012,BPL-016 | unassigned | todo |
| PLT-015 | Observability: logs, metrics, traces, alerts | Platform | G2 | INF-004 | unassigned | todo |
| PLT-016 | Feature flags | Platform | G2 | PLT-012 | unassigned | todo |
| PLT-017 | Per-tenant brand asset storage | Platform | G2 | PLT-003,INF-011 | unassigned | todo |
| PLT-018 | Entitlement to remove the Powered-by mark | Platform | G2 | PLT-006,BRD-007 | unassigned | todo |
| PLT-019 | Audited just-in-time support access | Platform | G3 | PLT-012,SEC-008 | unassigned | todo |
| PLT-020 | Status page and tenant notifications | Platform | G3 | PLT-015 | unassigned | todo |
| PLT-021 | Per-tenant AI budget and quota enforcement | Platform | G2 | PLT-011 | unassigned | todo |
| PLT-022 | Custom domains per tenant | Platform | G5 | PLT-017,INF-010 | unassigned | todo |
| PLT-023 | Self-serve signup and plan gating switched on | Platform | G5 | PLT-008,GTM-008 | unassigned | todo |
| PLT-024 | Gateway: own API paths, block or rewrite engine paths, strip engine headers, rename cookies, map engine errors to our error model (ADR-0016) | Platform | G1 | PLT-001 | unassigned | todo |
| INF-001 | Hosting decision: in-country provider shortlist and choice | Infrastructure | G1 | LEG-003,CMP-019 | unassigned | todo |
| INF-002 | Infrastructure as code baseline | Infrastructure | G1 | INF-001 | unassigned | todo |
| INF-003 | CI/CD for services (build, test, deploy to staging) | Infrastructure | G1 | GOV-007 | partner | todo |
| INF-004 | Staging environment | Infrastructure | G1 | INF-002 | unassigned | todo |
| INF-005 | Production environment | Infrastructure | G3 | INF-004,SEC-002 | unassigned | todo |
| INF-006 | Container build and image scanning | Infrastructure | G2 | INF-003 | unassigned | todo |
| INF-007 | Cost monitoring per tenant and per service | Infrastructure | G3 | PLT-007 | unassigned | todo |
| INF-008 | Disaster recovery plan and failover test | Infrastructure | G4 | DAT-005 | unassigned | todo |
| INF-009 | Decide where the isolated browser runner lives (open question) | Infrastructure | G3 | SEC-003 | unassigned | todo |
| INF-010 | Capacity plan and hosting at volume | Infrastructure | G5 | ERP-002,INF-007 | unassigned | todo |
| INF-011 | Asset delivery (CDN) for tenant brand assets | Infrastructure | G2 | INF-004 | unassigned | todo |
| INF-012 | Dev server and access: one small shared dev host for the engine and our services using infra/dev/docker, behind a login; founders create the account, project and access (ADR-0018) | Infrastructure | G1 | GOV-009 | eldon | todo |
| INF-013 | Vercel project connected to the repo with per-PR preview links; founders create the project (ADR-0018) | Infrastructure | G0 | GOV-009 | eldon | todo |
| BRD-001 | Brand guidelines v1 (Quadrant) and placeholder logo | Brand | G0 | - | eldon | done |
| BRD-002 | Design tokens: light and dark, CSS and JSON | Brand | G0 | BRD-001 | eldon | done |
| BRD-003 | Identity decision: final name, logo direction, Arabic spelling | Brand | G1 | LEG-008 | eldon | todo |
| BRD-004 | Token layering: base, product theme, tenant overrides, user preference | Brand | G1 | BRD-002 | eldon | todo |
| BRD-005 | Theme engine: light, dark, system, per-user persistence | Brand | G2 | BRD-004 | unassigned | todo |
| BRD-006 | Tenant colour guardrails: WCAG AA check in both themes, auto-adjust or reject | Brand | G2 | BRD-004 | eldon | doing |
| BRD-007 | Brand asset pipeline: logo variants, auto-derived dark variant, size generation | Brand | G2 | BRD-004,SEC-006 | eldon | doing |
| BRD-008 | Favicon generation from the tenant logo | Brand | G2 | BRD-007 | unassigned | todo |
| BRD-009 | Design system rollout: generate all logo files, sizes, favicons, social sizes, the product design system and brand guidelines | Brand | G2 | BRD-003,LEG-008 | unassigned | todo |
| BRD-010 | UI component library built from tokens | Brand | G2 | BRD-005 | unassigned | todo |
| BRD-011 | Font licence and Arabic typography verification | Brand | G1 | BRD-001 | eldon | doing |
| BRD-012 | Icon set licence check | Brand | G1 | BRD-001 | unassigned | todo |
| WEB-001 | Marketing website v1, bilingual | Web | G2 | BRD-009 | unassigned | todo |
| WEB-002 | Contact and waitlist form with PDPL consent | Web | G2 | WEB-001,LEG-012 | unassigned | todo |
| WEB-003 | App shell: sign-in, workspace switcher, navigation | Web | G2 | PLT-005,BRD-010 | unassigned | todo |
| WEB-004 | Chat screen with modes | Web | G2 | WEB-003,OPR-010 | unassigned | todo |
| WEB-005 | Approval inbox screen | Web | G2 | WEB-003,OPR-007 | unassigned | todo |
| WEB-006 | Reports and dashboard screens | Web | G2 | WEB-003,OPR-008 | unassigned | todo |
| WEB-007 | Settings: Branding screen with live preview and contrast feedback | Web | G2 | WEB-003,BRD-006,BRD-007 | unassigned | todo |
| WEB-008 | Login page with tenant branding | Web | G2 | WEB-003,BRD-007 | unassigned | todo |
| WEB-009 | Settings: document templates for tenant-branded invoices | Web | G2 | WEB-007,ERP-016 | unassigned | todo |
| WEB-010 | Settings: users, roles and scopes | Web | G2 | WEB-003,ERP-008 | unassigned | todo |
| WEB-011 | Role-based navigation and views | Web | G2 | WEB-003,ERP-008 | unassigned | todo |
| WEB-012 | First-run onboarding screens | Web | G2 | WEB-004 | unassigned | todo |
| WEB-013 | Mobile responsive layout and installable web app | Web | G3 | WEB-004 | unassigned | todo |
| WEB-014 | Pricing page | Web | G3 | GTM-008,WEB-001 | unassigned | todo |
| WEB-015 | Bilingual help centre | Web | G3 | WEB-001 | unassigned | todo |
| QA-001 | Eval framework and CI hook | Quality | G1 | GOV-006 | eldon | done |
| QA-002 | Arabic eval set v0 (100 prompts: accounting terms, dialects, numbers) | Quality | G1 | QA-001 | eldon | done |
| QA-003 | Model bake-off on the Arabic eval set | Quality | G1 | QA-002 | eldon | todo |
| QA-004 | Compiler snapshot tests on Blueprint fixtures | Quality | G1 | BPL-004 | eldon | todo |
| QA-005 | Agent behaviour evals (tool choice, refusal, confirm-before-write) | Quality | G2 | OPR-002,QA-001 | unassigned | todo |
| QA-006 | Prompt-injection eval suite | Quality | G2 | SEC-003,QA-001 | unassigned | todo |
| QA-007 | Contrast tests for tenant themes in light and dark | Quality | G2 | BRD-006 | unassigned | todo |
| QA-008 | RTL visual regression tests, including tenant-branded screens and documents | Quality | G2 | BRD-010 | unassigned | todo |
| QA-009 | End-to-end rehearsal: discovery to simulated Blueprint to live on synthetic data | Quality | G2 | BPL-020,DSC-009,OPR-010 | unassigned | todo |
| QA-010 | Eval thresholds enforced in CI as release gate | Quality | G2 | QA-005,QA-002 | unassigned | todo |
| QA-011 | Simulator accuracy test against known outcomes | Quality | G2 | BPL-018 | unassigned | todo |
| QA-012 | Release checklist | Quality | G2 | QA-010 | unassigned | todo |
| QA-013 | Load and soak tests | Quality | G3 | ERP-002,INF-005 | unassigned | todo |
| QA-014 | Accessibility audit (WCAG AA) | Quality | G3 | WEB-013 | unassigned | todo |
| GTM-001 | Niche decision: trading and distribution first | GTM | G0 | - | eldon | done |
| GTM-002 | 20-30 buyer and accountant interviews in the niche | GTM | G1 | - | eldon | todo |
| GTM-003 | Interview synthesis: ICP, pains, who vetoes, willingness to pay | GTM | G1 | GTM-002 | eldon | todo |
| GTM-004 | Dubai Create AI Agents Championship: choose the narrow agent and plan (dates UNVERIFIED) | GTM | G1 | - | eldon | todo |
| GTM-005 | Pilot A: sign a paid pilot with the anonymised-reuse clause | GTM | G2 | LEG-013,GTM-003 | unassigned | todo |
| GTM-006 | Pilot A: run discovery to live | GTM | G2 | GTM-005,QA-009 | unassigned | todo |
| GTM-007 | Pricing tests (Van Westendorp and anchor tests) | GTM | G2 | GTM-003 | unassigned | todo |
| GTM-008 | Pricing and packaging v1 | GTM | G3 | GTM-007,PLT-006 | unassigned | todo |
| GTM-009 | Sales deck and demo script | GTM | G2 | GTM-003 | unassigned | todo |
| GTM-010 | Pilot B: Odoo migration pilot | GTM | G3 | GTM-006,DSC-013 | unassigned | todo |
| GTM-011 | Support process: channels, hours, severity, escalation | GTM | G3 | PLT-019 | unassigned | todo |
| GTM-012 | Accountant channel programme | GTM | G3 | GTM-003 | unassigned | todo |
| GTM-013 | Case study from Pilot A | GTM | G3 | GTM-006 | unassigned | todo |
| GTM-014 | Customer success playbook | GTM | G4 | GTM-011 | unassigned | todo |
| GTM-015 | Second market (UAE) launch plan | GTM | G5 | CMP-011 | unassigned | todo |
| GTM-016 | Partner and reseller programme | GTM | G5 | GTM-014 | unassigned | todo |
| FND-001 | Investor shortlist from research/05, re-verified | Fundraising | G1 | - | eldon | todo |
| FND-002 | Accelerator evaluation (Hub71+, Antler) after the spike | Fundraising | G1 | ERP-001 | unassigned | todo |
| FND-003 | Financial model | Fundraising | G2 | GTM-007 | unassigned | todo |
| FND-004 | Pitch deck | Fundraising | G2 | GTM-006 | unassigned | todo |
| FND-005 | Data room | Fundraising | G2 | LEG-010 | unassigned | todo |
| FND-006 | Autonomy and reuse chart for investors | Fundraising | G3 | BPL-022,GTM-006 | unassigned | todo |
| FND-007 | Cap table and funding terms with counsel | Fundraising | G3 | LEG-010 | unassigned | todo |
| CMP-021 | Country pack framework: pack contents, selection by company profile, allowed overrides (ADR-0015) | Compliance | G1 | BPL-002,BPL-009 | partner | todo |
| CMP-022 | Calendar and Hijri (Umm al-Qura) conversion library choice, licence and tests | Compliance | G1 | CMP-005 | unassigned | todo |
| CMP-023 | Per-company calendar and week settings (week start, weekend, working days and hours, Ramadan hours, number system) | Compliance | G2 | CMP-021,CMP-022 | unassigned | todo |
| CMP-024 | Holiday calendars per country with admin-editable moon-sighting overrides | Compliance | G2 | CMP-023 | unassigned | todo |
| CMP-025 | Fiscal-year type and start handling; zakat period handling | Compliance | G2 | CMP-023,CMP-013 | unassigned | todo |
| CMP-026 | Timezone handling and Egypt daylight-saving rules (UNVERIFIED) | Compliance | G2 | CMP-023 | unassigned | todo |
| CMP-027 | Egypt market research: e-invoicing, VAT, data protection, payroll (all UNVERIFIED) | Compliance | G3 | CMP-001 | unassigned | todo |
| CMP-028 | Egypt country pack | Compliance | G4 | CMP-027,CMP-021 | unassigned | todo |
| CMP-029 | UAE country pack and KSA country pack built on the framework | Compliance | G2 | CMP-021,CMP-006 | unassigned | todo |
| ERP-019 | Dual-date display (Gregorian plus Hijri) on documents, locked regions respected | Runtime | G2 | CMP-022,ERP-016 | unassigned | todo |
| ERP-020 | Engine headless and internal-only: disable Desk and default web routes for tenants; no direct internet exposure (ADR-0016) | ERP runtime | G1 | ERP-001 | unassigned | todo |
| WEB-016 | Date pickers and entry in both Gregorian and Hijri calendars, RTL | Web | G2 | CMP-022,BRD-010 | unassigned | todo |
| WEB-017 | Own login, password-reset, error pages, emails and print formats; no engine templates reach customers (ADR-0016) | Web | G1 | BRD-001 | unassigned | todo |
| WEB-018 | Decide the web stack (short ADR) before building screens; then host the design-system preview pages first, then clickable chat screens (ADR-0018) | Web | G0 | BRD-002 | eldon | doing |
| WEB-019 | Host the static design-system preview pages from docs/brand on the preview project | Web | G1 | INF-013 | unassigned | todo |
| QA-015 | Evals and property tests for date handling (conversion, week and fiscal rules, overrides, timezones) | Quality | G2 | CMP-022,QA-001 | unassigned | todo |
| QA-016 | Engine-invisibility crawl test on staging: pages, API responses, headers, cookies, bundles contain no engine markers (ADR-0016) | Quality | G1 | PLT-001 | unassigned | todo |
| QA-017 | Smoke check that a preview URL loads and shows no engine markers (ADR-0016, ADR-0018) | Quality | G1 | INF-013 | unassigned | todo |
| GTM-017 | Egypt go-to-market assessment (third market; depends on verified regulations) | GTM | G4 | CMP-027 | unassigned | todo |
| GTM-018 | Attach primary sources to co-founder research figures (ERP failure rate, go-live timelines, 90 pct and 75 pct targets, Egypt/KSA/UAE compliance leads) before any external use | Go-to-market | G1 | GTM-001 | partner | todo |
