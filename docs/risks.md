# Risk register

Status: accepted
Owner: eldon

R-001 to R-011 come from [strategy/01-gaps-and-risks.md](strategy/01-gaps-and-risks.md) (ranked there; evidence and "what would change my mind" are in that file). R-012 onward are new. Review at every gate change. Status: open, mitigating, accepted, closed.

| ID | Risk | Impact | Mitigation | Owner | Status |
|---|---|---|---|---|---|
| R-001 | Owners do not want to "build an ERP", they want a problem gone | No demand | Sell the outcome (compliant and running, changes by chat); 20-30 interviews (GTM-002) | eldon | open |
| R-002 | Price anchor collision with Wafeq, Qoyod, Odoo | Cannot charge enough for software margins | Price against implementation plus retainer; pricing tests (GTM-007) | eldon | open |
| R-003 | Compliance liability: a wrong generated invoice fines the customer | Trust and legal exposure | Compliance logic only in certified, frozen, versioned components; AI cannot edit it (CMP-004, CMP-008) | unassigned | open |
| R-004 | The external accountant vetoes the purchase | Lost deals | Accountant role and view from day one (DSC-016); accountant channel (GTM-012) | unassigned | open |
| R-005 | Venture scale: small market at the assumed ACV | Funding difficulty | Raise ACV, GCC expansion in the story (GTM-015) | eldon | open |
| R-006 | Software-house drift from early clients | Services margins, no moat | ADR-0008 rules, autonomy metrics, no free pilots (GOV-016) | eldon | open |
| R-007 | Ledger correctness in an AI-coded codebase | Existential accounting bugs | Keep ledger in the mature engine; property tests; humans approve posting logic (ERP-014) | unassigned | open |
| R-008 | Arabic LLM quality for accounting terms and dialects | Bad product in the core language | Arabic eval set first, thresholds as release gate (QA-002, QA-010) | unassigned | open |
| R-009 | PDPL, hosting and cross-border LLM calls unverified | Legal block or fines | In-region tenants, minimal prompts, regional endpoints, counsel (LEG-012, PLT-010) | eldon | open |
| R-010 | Funded locals add AI first | Lost distribution race | Win on breadth, compliance, onboarding speed | eldon | open |
| R-011 | Our research is thin or UNVERIFIED in places | Wrong scope decisions | Re-verify before it drives scope (CMP-001) | unassigned | open |
| R-012 | Two founders, different AI tools: drift, conflicting edits, lost context | Wasted work, inconsistent code | Repo as memory, per-session logs, CI docs gate, cross-model review (ADR-0009) | eldon | mitigating |
| R-013 | GPL boundary: engine accidentally distributed or linked into our services | Forced source disclosure | SaaS-only, services separate over API, counsel review (LEG-006, ADR-0002) | eldon | open |
| R-014 | Trademark: working name not cleared; trademark policy of Frappe and ERPNext | Rebrand cost | Name clearance before launch assets (LEG-008, LEG-009); rename must be one edit | eldon | open |
| R-015 | Prototype change engine has known security flaws and no licence file | Compromise of a tenant, IP ambiguity | CE-SEC-001..005, LEG-001, LEG-002; treat as untrusted until fixed | partner | open |
| R-016 | Prompt injection via customer documents, Odoo data or browser sessions | Data leakage, wrong actions | Untrusted-content handling, tool allowlists, injection evals (SEC-003, QA-006, SEC-014) | unassigned | open |
| R-017 | Cross-tenant data leak | Existential trust loss | Site-per-tenant isolation, isolation test suite, identity review (ADR-0006, SEC-004) | unassigned | open |
| R-018 | ERPGulf ZATCA app is community-maintained and lacks automated test coverage | Compliance break | Evaluated in CMP-002 (MIT confirmed, core Python crypto/UBL clean); vendor/fork core logic, strip Desk UI, make PIH hash chaining transactional, and build automated sandbox suite (CMP-004, CMP-020) | partner | mitigating |
| R-019 | Frappe/ERPNext version upgrades break components | Stuck on old version | Pinned set, upgrade policy, regression suites (ERP-004) | unassigned | open |
| R-020 | AI cost grows with usage while price is per company | Margin leak | Gateway budgets, AI-actions caps, per-tenant cost attribution (PLT-009, PLT-011, PLT-021) | unassigned | open |
| R-021 | Tenant branding breaks contrast, RTL or legally required invoice layout | Accessibility failure, compliance failure | Guardrails, locked compliance regions, contrast and RTL tests (ADR-0014, BRD-006, QA-007, QA-008) | unassigned | open |
| R-022 | Malicious or broken brand asset upload (SVG scripts, malware) | XSS, malware | Allowlist types, SVG sanitiser, scan, per-tenant storage (SEC-006) | unassigned | open |
| R-023 | Component factory ships a flawed component to all tenants | Wide blast radius | Engineer certification, sandbox tests, staged rollout, rollback (BPL-014, BPL-015, SEC-010) | unassigned | open |
| R-024 | Hand-built first clients take all founder time | No platform progress | Autonomy targets, second build reuses 30%, stop-selling rule (ADR-0008) | eldon | open |
| R-025 | Key-person risk: only the partner knows the prototype | Delay | Import and document it as a module (BPL-001, ADR-0013) | partner | open |
| R-026 | Free-first adoption without paying signal | Misread demand | Paid fixed-price pilots; entitlements and metering built in (ADR-0005, PLT-006) | eldon | open |
| R-027 | Backups or restore untested | Data loss | Timed restore drills before paying customers (DAT-004, DAT-005) | unassigned | open |
| R-028 | Isolated browser session fallback risks credential exposure and ToS breaches | Legal and security incident | Late fallback only, owner-driven, no stored credentials, egress controls (DSC-017, SEC-015) | unassigned | open |
| R-029 | Model provider outage or policy change | Product down or non-compliant | Gateway with provider fallback and regional routing (PLT-010) | unassigned | open |
| R-030 | Hijri date and Arabic-numeral handling errors in documents | Invalid invoices, user distrust | Dedicated tests and accountant review of PDFs (CMP-005, ERP-007) | unassigned | open |
| R-031 | Calendar and country-pack complexity (Hijri moon sighting, differing work-weeks, Egypt rules unverified, DST) | Wrong dates on documents, payroll or deadlines; slow country expansion | Gregorian canonical storage, tested conversion library, admin overrides, country packs as certified components, date evals (ADR-0015, CMP-021..026, QA-015) | unassigned | open |
