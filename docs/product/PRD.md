# Product Requirements Document (PRD)

Status: draft
Owner: eldon

Platform name: Orrery (working name, not cleared; see ADR-0001). Say "the platform" in prose where possible.

## 1. Problem
Owner-led companies (10-100 staff) in KSA and UAE run on Excel, WhatsApp and a mix of tools. Moving to an ERP means a partner project costing 5-14x the licence in year one (UNVERIFIED partner pricing, see [../research/02-market-and-customer.md](../research/02-market-and-customer.md) section 3), and customised ERPs become a liability at upgrade time (same file, section 4). Compliance deadlines (ZATCA Phase 2 waves, UAE e-invoicing) force a decision. Evidence of buyer demand is thin and must be tested in interviews ([../strategy/01-gaps-and-risks.md](../strategy/01-gaps-and-risks.md) risk 1).

## 2. Product
One chat, in Arabic or English. The AI interviews the owner (or reads their existing tools), drafts a visual Blueprint, assembles an ERP from vetted components, simulates a month of the business, then runs it. After go-live the same chat asks, acts, reports and changes the system. Every client build improves the platform (no client-specific code).

## 3. Users
See [personas.md](personas.md). Primary buyer: the owner. Strong influencer: the external accountant or VAT consultant (hypothesis). Daily users: accountant, sales, warehouse, HR. Internal: our review team.

## 4. Goals and non-goals
| Goals (v1) | Non-goals (v1) |
|---|---|
| Trading and distribution firm live on a compliant ERP, set up by chat, with a human-reviewed build | A general "build any app" tool |
| ZATCA Phase 1 and 2 compliant invoicing (KSA) | Own ledger, own tax engine, own payroll maths written by AI |
| Arabic-first, RTL, bilingual documents | Mobile native apps (responsive web first) |
| One chat with modes: discover, ask, act, change | Two separate UIs for builders and users |
| Simulation of a month of the owner's data before go-live | On-premise or hybrid delivery |
| Per-tenant branding and light/dark themes | Per-client code forks |
| Entitlements and metering in place from day one | Public self-serve gating (free-first at launch) |

Full not-doing list: [module-map.md](module-map.md).

## 5. Principles
Taken from the context brief and AGENTS.md: open source first, configuration over code, deterministic ledger/tax/e-invoicing/payroll/audit, Arabic-first, compliance never "later", numbers from code and words from the model, customer content is untrusted input, everything logged, no client-specific code.

## 6. Functional requirements (by part)
| ID | Requirement | Part | Priority |
|---|---|---|---|
| F-01 | Sign up with email or phone OTP, company details, consent | Platform | MVP |
| F-02 | Discovery chat (interview and template-first draft for trading and distribution) | Discovery | MVP |
| F-03 | Connect sources: file uploads (Excel/CSV/PDF/photos), Odoo API/export; other tiers per connector framework | Discovery | MVP (uploads, Odoo); later (others) |
| F-04 | Gap analysis and questions; Blueprint draft rendered visually; owner edits and approves | Discovery, Blueprint | MVP |
| F-05 | Quote from Blueprint (setup + plan) | Discovery | MVP |
| F-06 | Team review gate (human) before any build | Platform | MVP, mandatory |
| F-07 | Compile Blueprint to engine configuration; sandbox build; diff, apply, rollback | Blueprint, Runtime | MVP |
| F-08 | Simulation: replay a month of the owner's data; report differences | Blueprint | MVP |
| F-09 | Go-live checklist and cut-over | Platform | MVP |
| F-10 | Accounting, VAT, ZATCA e-invoicing (Phase 1 and 2), sales, purchasing, inventory | Runtime | MVP |
| F-11 | Chat modes after go-live: ask, act, change; acts with the user's permissions | Operate | MVP |
| F-12 | Role views: screens and tools generated from role, function, scope | Operate | MVP |
| F-13 | Approval inbox; reports library and builder; notifications; documents inbox; audit log | Operate | MVP (core), later (builder depth) |
| F-14 | Tenant branding and light/dark themes ([theming-and-tenant-branding.md](theming-and-tenant-branding.md)) | Platform | MVP |
| F-15 | Data export (full) and delete | Platform | MVP |
| F-16 | Plans, entitlements, AI-action metering | Platform | MVP (built), gating off |
| F-17 | Internal console: review queue, component factory, tenant ops, audited support access | Platform | MVP |
| F-18 | Bilingual website, help centre, status page | Web | MVP |

## 7. Non-functional requirements
| Area | Requirement |
|---|---|
| Language | Arabic and English; every string via i18n; RTL tested on every screen |
| Compliance | Effective-dated config for rates/thresholds/waves; never hard-coded |
| Security | [../security/security-baseline.md](../security/security-baseline.md) |
| Residency | KSA tenants in-Kingdom, UAE tenants in-UAE ([../security/hosting-rules.md](../security/hosting-rules.md)) |
| Accessibility | WCAG 2.2 AA target for web and app (target, not yet audited) |
| Performance | Targets set in website.md; app targets TBD after the spike |
| Audit | Every AI action and every config change logged and traceable |
| AI cost | Hard per-tenant monthly budget; customers see "AI actions", never tokens |

## 8. Success measures
Autonomy and reuse targets live in [../strategy/08-product-vs-software-house.md](../strategy/08-product-vs-software-house.md). Pilot criteria: [pilots.md](pilots.md). Business hypotheses to test: [pricing.md](pricing.md).

## 9. Risks and open points
See [../strategy/01-gaps-and-risks.md](../strategy/01-gaps-and-risks.md) and [../open-questions.md](../open-questions.md) (if present; legacy: [../strategy/open-questions.md](../strategy/open-questions.md)). Biggest: unproven buyer demand, compliance liability, Arabic LLM quality, PDPL treatment of cross-border AI calls.

## 10. Related
[personas.md](personas.md), [module-map.md](module-map.md), [journey.md](journey.md), [website.md](website.md), [app-screens.md](app-screens.md), [pilots.md](pilots.md), [../compliance/country-matrix.md](../compliance/country-matrix.md).

## 11. Markets, country packs and calendars (added)
Operating markets: KSA, UAE, Egypt, launch order in that order; adding Egypt does not change the KSA-first launch. Each market is a country pack (compliance, tax, documents, payroll, currency, defaults), see [../architecture/country-packs.md](../architecture/country-packs.md). Calendars (Gregorian plus Hijri, Coptic where relevant), week start, weekend, working days and hours (incl. reduced Ramadan hours), holidays, fiscal year, time zone and number system are per-company settings with defaults from the country chosen at sign-up, owner/admin editable with preview and audit; date pickers support both calendars ([app-screens.md](app-screens.md), [../architecture/calendars-and-locale.md](../architecture/calendars-and-locale.md)). New requirement rows: F-19 country selection at sign-up with defaults; F-20 company calendar and week settings; F-21 dual-calendar date pickers. Egypt facts: research needed ([../compliance/country-matrix.md](../compliance/country-matrix.md)).
