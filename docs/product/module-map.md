# Module map

Status: draft
Owner: eldon

MVP = trading and distribution firms, 10-100 staff ([../strategy/02-niche-and-launch-country.md](../strategy/02-niche-and-launch-country.md)). Modules are delivered as engine core plus certified components; none are written per client.

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
| HR basics (employee records, leave) | Later (R2) | HRMS skeleton | Arabic coverage of HRMS is low (UNVERIFIED, [../strategy/04-architecture-and-seed.md](../strategy/04-architecture-and-seed.md)) |
| Payroll with WPS/Mudad (KSA) and SIF (UAE) file export, GOSI rate tables | Later (R2) | Component to build | Needs verified rules; see [../compliance/country-matrix.md](../compliance/country-matrix.md) |
| Projects and job costing | Later (R3) | ERPNext core | Second niche candidate (contracting) |
| Manufacturing (BOM, batches) | Later (R3+) | ERPNext core | Rejected for now |
| CRM beyond sales basics | Later | | |
| Zakat/CIT worksheet exports | Later | Reports | Export only, no filing |
| Multi-entity, consolidation | Later (Scale plan) | | |
| Direct integrations (Mudad, GOSI, Qiwa APIs, banks) | Later | Connectors | May need partner status (UNVERIFIED) |
| Payments, financing | Later (revenue line idea) | | Investor story, not scope |

## Explicit not-doing list (v1)
- No custom ledger, tax engine or payroll maths written or altered by AI.
- No per-client code or forks; a need no component covers becomes a candidate component.
- No POS-first retail or F&B, clinics, manufacturing depth, or e-commerce platforms as customers (rejected for now).
- No on-premise or hybrid delivery; no VPS per client.
- No tax or zakat filing on the customer's behalf; we provide data only.
- No native mobile apps; responsive web only.
- No browser-session connector in v1 (late fallback only).
- No selling model tokens; customers see AI actions.
- No custom domains per tenant in v1.
- No third-party marketplace for components in v1.

## Country packs and per-company calendars (added)
- Markets: KSA, UAE, Egypt and Qatar (all phase 1, no fixed launch order, ADR-0024). Compliance, tax codes, document templates, payroll files, currency and calendar defaults are delivered as country packs, specified in [../architecture/country-packs.md](../architecture/country-packs.md) (written by another agent). Egypt and Qatar pack contents: research needed.
- Calendars, week, holidays, fiscal year and time zone are per-company settings with country defaults: [../architecture/calendars-and-locale.md](../architecture/calendars-and-locale.md). UI: Settings > Company calendar and week ([app-screens.md](app-screens.md)).
