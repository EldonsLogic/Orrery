# Spec 03: ERP Runtime (Part 3)

Status: draft
Owner: unassigned
Plan IDs: ERP (plus CMP for compliance items, QA)

## Purpose
The rigid core that does the accounting and operations correctly: Frappe Framework plus ERPNext (and HRMS later) as the seed engine, one site per tenant, plus certified components for Saudi/UAE compliance, Arabic/RTL and bilingual documents. Decision: ADR-0002, gated by the G1 spike. Detail: [engine-adapter](../architecture/engine-adapter.md).

## Responsibilities
1. Run the pinned engine version set (Frappe + ERPNext + HRMS if used), one site per tenant, upgraded by canary ([engine-adapter](../architecture/engine-adapter.md)).
2. Own the **rigid zone**: ledger posting, tax, e-invoicing, payroll maths, audit trail. Never AI-written.
3. **ZATCA** e-invoicing through the MIT-licensed ERPGulf app (fork and embed with notice). The AGPL lavaloon app is not used (licence: [open-source research](../research/04-open-source.md)).
4. UAE e-invoicing component later, same pattern (regime details UNVERIFIED, see [regulations research](../research/03-regulations.md)).
5. **Arabic and RTL** in engine-rendered outputs: bilingual invoices and statements, Hijri date display, Arabic-Indic numerals option, correct PDF shaping (known risk, UNVERIFIED).
6. Expose a stable API to the adapter and tool API (REST; MCP where useful). The engine's own Desk UI is for internal and support use; customers use the platform's own web app.
7. Emit record events to the event stream ([events.md](../../contracts/events.md)).
8. Host **country packs** (KSA first, then UAE, then Egypt; Egypt UNVERIFIED): tax, e-invoicing, holiday calendar, work week, document templates, formats ([country-packs](../architecture/country-packs.md)).
9. Implement the **calendar layer**: dates stored as Gregorian ISO/UTC, Hijri (Umm al-Qura) as display/entry/rule layer, working-day and due-date functions in code ([calendars-and-locale](../architecture/calendars-and-locale.md)).

## Interfaces
| Contract | Use |
|---|---|
| Component manifest | Components installed as Frappe apps/fixtures declare compatibility |
| Event stream | Producer of record and document events |
| Tool API | Executes tool calls with the user's own permissions |
| Blueprint | Receives compiled configuration only via the adapter |

## Data owned
Business records per tenant: ledger, documents, stock, parties, files. One site database per tenant, separate file storage prefix, per-tenant encryption keys and backups ([data](../architecture/data.md)). The platform never reads another tenant's site.

## Key behaviours
- Posted documents are immutable; corrections are credit notes or reversals.
- ZATCA flow: onboarding (CSID), standard and simplified invoices, credit/debit notes, clearance/reporting status stored on the document, QR and hash chain per the authority's rules (details UNVERIFIED until the spike).
- Legally required layout wins over branding on documents ([theming](../architecture/theming.md)).
- Roles and permissions in the engine are generated from the Blueprint; the engine enforces them even if the chat misbehaves.
- Licence boundary: our services talk to the engine over API; the engine is never distributed to customers without legal review.

## Failure modes
| Failure | Handling |
|---|---|
| Authority endpoint down or rejects an invoice | Queue, retry with backoff, surface status to the accountant; never silently drop |
| Arabic PDF shaping wrong | Blocking RTL/PDF tests in CI; golden-file comparison |
| Engine upgrade regression | Canary tenants, rollback by version set |
| Site migration fails | Per-site backup taken first; site marked degraded; others unaffected |
| Noisy tenant | Per-site worker limits and rate limits |

## Security notes
- Site-per-tenant isolation; no cross-site queries.
- Engine admin credentials never leave the control plane; applications use per-tenant service identities with least privilege.
- Engine apps pinned by commit hash; third-party apps reviewed (licence, code, network calls).
- Support access only via just-in-time, audited sessions ([platform](05-platform.md)).

## Open questions
1. Version set: v15 vs newer, confirmed in the spike (UNVERIFIED).
2. Whether the ERPGulf app covers phase 2 fully for our document types; test against the ZATCA sandbox.
3. HRMS scope for v1: skeleton only, or exclude. GOSI/WPS gaps noted in strategy 04.
4. Hosting provider with in-country region (see [hosting rules](../security/hosting-rules.md) when published).

## Acceptance criteria
**G1 (spine proven)**
- Pinned engine set stands up from scripts; a tenant site is created by a script in one command.
- A ZATCA standard and a simplified invoice plus a credit note pass the ZATCA sandbox.
- Arabic bilingual invoice PDF with Hijri date and QR renders correctly (golden file).
- Backup and restore of a site tested once end to end.
- KSA country pack resolves `company.locale` defaults; Gregorian to Hijri conversion, working-day and Ramadan-hours test cases pass.

**G2 (pilot-ready)**
- Pilot tenant runs the pilot's real invoice and payment flows on production-grade infrastructure in-country (provider decision recorded).
- E-invoicing in the authority's required mode (simulation/production as the pilot needs) is working with monitoring on rejection rates.
- Chart of accounts, opening balances and VAT settings from the Blueprint reconcile with the owner's accountant.
