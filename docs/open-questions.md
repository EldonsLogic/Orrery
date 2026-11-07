# Open questions

Status: accepted
Owner: eldon

The canonical list from Phase 1-2 is [strategy/open-questions.md](strategy/open-questions.md). Keep adding there for strategy items. This file adds platform and build questions raised during foundation work. Answered items move into an ADR and are struck here with the ADR number.

| # | Question | Owner | Needed by | Related |
|---|---|---|---|---|
| Q-1 | RESOLVED 2026-11-07 (ADR-0007 accepted: central identity with per-tenant roles). Was: identity model, one central identity with per-tenant roles, or identity per tenant? | eldon | G0 | PLT-002 |
| Q-2 | Where does the isolated read-only browser runner live (our infrastructure, owner's device, third-party)? Affects credentials, egress and PDPL | unassigned | G3 | INF-009, SEC-015 |
| Q-3 | Final GitHub repo name and organisation name (working name is not cleared) | eldon | G0 | GOV-002, ADR-0001 |
| Q-4 | Arabic spelling and transliteration of the product name for search and brand | eldon | G1 | BRD-003 |
| Q-5 | Tenant branding limits: which plan may remove "Powered by", how many colours, custom fonts allowed (default no) | eldon | G2 | PLT-018, ADR-0014 |
| Q-6 | Which Frappe/ERPNext/HRMS version set to pin and when to move? ERP-001 proposes v15.126.0, v15.124.5 and v15.64.8 respectively; compatibility on a dedicated bench is UNVERIFIED. | partner | G1 | ERP-001, ERP-004 |
| Q-7 | Licence for our own repo and for contracts/ if we ever publish them | eldon | G0 | LEG-002 |
| Q-8 | Which accounting standard and chart of accounts default for KSA, UAE, Egypt and Qatar templates | unassigned | G1 | CMP-006 |
| Q-9 | Which cloud or hosting provider can keep tenant data in-country with acceptable cost | unassigned | G1 | INF-001 |
| Q-10 | Do first clients accept data going to a foreign-region model endpoint, or must we use in-region only | eldon | G2 | LEG-012, PLT-010 |
| Q-11 | Egypt regulations (e-invoicing, VAT, data protection, payroll) and whether Coptic calendar or Egypt DST matter for the product: all UNVERIFIED | unassigned | G3 | CMP-027, ADR-0015 |
| Q-12 | Which Hijri conversion library (Umm al-Qura), and how moon-sighting overrides are authored and audited | unassigned | G1 | CMP-022, ADR-0015 |
| Q-13 | RESOLVED 2026-11-07 (ADR-0021: repo made public, protection enabled). Was: GitHub refuses branch protection on a private repo without a paid plan (HTTP 403). Upgrade to GitHub Pro or Team so `main` takes only reviewed PRs with passing checks, or accept discipline-only enforcement for now? | eldon | G0 | GOV-008 |
| Q-14 | Where does the central identity store live with four markets (KSA, UAE, Egypt, Qatar)? One store per country with cross-country linking, or one store with legal sign-off for cross-border personal data (names, contacts, MFA factors, login logs)? Also: may staff abroad access in-country tenant data? | eldon | G1 | PLT-005, ADR-0007, LEG-003 |
| Q-15 | Pin the dev Redis image to 7.2.x or switch to Valkey? ERP-001 proposes `redis:7.2.7-alpine`; the upstream licence reading and bench verification remain UNVERIFIED pending review. Partner changes infra/dev/docker; counsel confirms the licence reading. | partner | G1 | LEG-004, ERP-001 |
