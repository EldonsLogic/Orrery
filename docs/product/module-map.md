# Module map

Status: draft
Owner: eldon

MVP = trading and distribution firms, 10-100 staff ([../strategy/02-niche-and-launch-country.md](../strategy/02-niche-and-launch-country.md)). Modules are delivered as engine core plus certified components; none are written per client. Phase 1 adds ten modules on top of the core ([ADR-0076](../decisions/ADR-0076-phase-1-module-scope.md), Proposed); each is a Blueprint component behind our own UI, with the engine invisible (ADR-0016).

Status key for the phase-1 additions: **contracts now** (Blueprint or connector contract and ADR may start; builds are blocked until G2, or both founders' written agreement); **build after GPL** (no add-on engine app is pinned, installed or used until ADR-0074, PR #388, is Accepted); **deferred** (no contract or build yet); **rigid zone** (deterministic code, Tier 3, accountant sign-off before real use; payroll, zakat and POS receipts human-written, ADR-0076 item 9). Manufacturing's stock and ledger postings and the web shop's invoices, VAT and e-invoicing are rigid zone too (Tier 3), computed by the engine (ADR-0076 item 10).

| Module | Release | Engine basis | Notes |
|---|---|---|---|
| Accounting (GL, AR, AP, bank, multi-currency, period close) | MVP | ERPNext core | Rigid zone: AI never edits posting logic |
| VAT and e-invoicing KSA (ZATCA Phase 1 and 2) | MVP | ERPGulf MIT app (spike gated) | See [../compliance/e-invoicing.md](../compliance/e-invoicing.md) |
| UAE e-invoicing (via accredited provider) | MVP design, build before UAE go-live | Partner integration | UNVERIFIED dates; see compliance docs |
| Sales (quotes, orders, delivery, invoices, credit limits) | MVP | ERPNext core | |
| Purchasing (requests, orders, receipts, supplier invoices) | MVP | ERPNext core | |
| Inventory (items, warehouses, batches optional, stock counts, valuation) | MVP | ERPNext core | Multi-branch |
| Role views and approval inbox | MVP | Platform + Operate | Generated from Blueprint |
| Reports library and basic builder | MVP | Operate | Numbers from code via semantic layer |
| Tenant branding, light/dark themes | MVP | Platform | [theming-and-tenant-branding.md](theming-and-tenant-branding.md) |
| Document intake (Arabic OCR) for supplier invoices and receipts | MVP (basic), later (depth) | Discovery/Operate | Content is untrusted input |
| CRM (leads, opportunities, contacts, pipeline) | Phase 1: contracts now | ERPNext core CRM doctypes | Never the AGPL CRM, Helpdesk, Insights or Gameplan apps. BPL-052, BPL-056, WEB-031 |
| Projects and boards (board, timeline and calendar views) | Phase 1: contracts now | ERPNext core Task and Timesheet | Job costing follows; contracting is the second niche candidate. BPL-053, BPL-057, WEB-032 |
| Manufacturing (BOM, work orders, batches) | Phase 1: contracts now | ERPNext core | Stock and ledger postings rigid zone (Tier 3). BPL-054, BPL-058, WEB-033 |
| Marketing (campaigns, segments, consent) | Phase 1: contracts now | ERPNext core plus messaging connector | Sends need opt-in. BPL-055, BPL-059, WEB-034 |
| Omnichannel inbox (WhatsApp, Instagram, Facebook) | Phase 1: contracts now | Messaging connector (Meta's business platform), SMS | Inbound text is untrusted; Meta verification and templates are the customer's go-live items. Separate from the chat channel [opr-015-messaging-channel.md](opr-015-messaging-channel.md). DSC-022, DSC-024, WEB-035 |
| Payments (bring your own gateway) | Phase 1: contracts now | Payments connector | Hosted checkout or tokens, no card data, no Seshna merchant account; the gateway account is the customer's go-live item. DSC-021, DSC-023 |
| HR basics (employee records, leave) | Phase 1: build after GPL | HRMS functions | HRMS is in the pinned image but unused for this until ADR-0074; Arabic coverage of HRMS is low (UNVERIFIED, [../strategy/04-architecture-and-seed.md](../strategy/04-architecture-and-seed.md)). ERP-043 |
| Payroll with WPS/Mudad (KSA) and SIF (UAE) file export, GOSI rate tables | Phase 1: build after GPL; rigid zone, built last | Our own service on country packs, outside the engine (ADR-0080, Proposed) | Needs verified rules; see [../compliance/country-matrix.md](../compliance/country-matrix.md). CMP-048 (CMP-015 is its WPS slice) |
| E-commerce (web shop) | Phase 1: build after GPL | Webshop app (GPL-3.0) | Behind our UI; Webshop pages and assets never reach customers. Invoices and VAT rigid zone (Tier 3). ERP-042 |
| Zakat worksheet and base | Phase 1: rigid zone, built last | Reports plus country pack | Seshna prepares, the company files. CMP-049 (CMP-013 is its report slice) |
| Point of sale | Phase 1: deferred | Saudi POS app (not yet named; claim UNVERIFIED) | Receipts are rigid zone. Waits for the ZATCA claim review CMP-050; build CMP-051 |
| CIT worksheet exports | Later | Reports | Export only, no filing |
| Multi-entity, consolidation | Later (Scale plan) | | |
| Direct integrations (Mudad, GOSI, Qiwa APIs, banks) | Later | Connectors | May need partner status (UNVERIFIED) |
| Financing | Later (revenue line idea) | | Investor story, not scope |

## Explicit not-doing list (v1)
- No custom ledger, tax engine or payroll maths written or altered by AI.
- No per-client code or forks; a need no component covers becomes a candidate component.
- No POS-first retail or F&B, clinics, manufacturers or e-commerce platforms as customer segments (rejected for now, [../strategy/02-niche-and-launch-country.md](../strategy/02-niche-and-launch-country.md)). ADR-0076 adds point of sale (deferred), manufacturing and e-commerce as modules for the trading niche; it does not change the segment.
- No on-premise or hybrid delivery; no VPS per client.
- No tax or zakat filing on the customer's behalf; we provide data and worksheets only.
- No native mobile apps; responsive web only.
- No browser-session connector in v1 (late fallback only).
- No selling model tokens; customers see AI actions.
- No custom domains per tenant in v1.
- No third-party marketplace for components in v1.
- No AGPL engine apps (CRM, Helpdesk, Insights, Gameplan and others), ever (ADR-0076).
- No card data and no Seshna merchant account; payments go through the customer's own gateway.

## Country packs and per-company calendars (added)
- Markets: KSA, UAE, Egypt and Qatar (all phase 1, no fixed launch order, ADR-0024). Compliance, tax codes, document templates, payroll files, currency and calendar defaults are delivered as country packs, specified in [../architecture/country-packs.md](../architecture/country-packs.md) (written by another agent). Egypt and Qatar pack contents: research needed.
- Calendars, week, holidays, fiscal year and time zone are per-company settings with country defaults: [../architecture/calendars-and-locale.md](../architecture/calendars-and-locale.md). UI: Settings > Company calendar and week ([app-screens.md](app-screens.md)).
