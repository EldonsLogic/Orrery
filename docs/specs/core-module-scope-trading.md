# Core module scope for trading and distribution

Status: draft
Owner: partner

Plan ID: ERP-005 (feeds ERP-006, ERP-010, ERP-011, ERP-014).

Bench ground truth: observed read-only on `2026-11-14` against the pinned synthetic bench (`frappe` `15.126.0`, `erpnext` `15.124.5`, `hrms` `15.64.8`, `change_engine` `0.1.0`). Every doctype, report, print format, role, and setting name below was observed on that bench unless marked `UNVERIFIED`. Proposals not yet decided by founders are marked `PROPOSED`.

## 1. Scope rule

A module, doctype, report, or setting earns a place in v1 only if it traces to at least one of:
1. **Golden path and trading cycle**: [golden-path-trading-sale.md](golden-path-trading-sale.md) (G1) and the full v1 quote-to-cash and procure-to-pay flows (G2).
2. **Persona job**: Owner/GM, Accountant/finance, Sales, Warehouse/stock, or Our team/reviewer ([../product/personas.md](../product/personas.md)).
3. **Compliance need**: country-pack VAT/tax templates, e-invoicing, immutable audit trail, or record export ([../compliance/country-matrix.md](../compliance/country-matrix.md)).

Everything else in the engine stays **hidden by configuration** (module profiles, role permissions, workspaces, domain settings), never by forking the engine or writing per-client code ([ADR-0008](../decisions/ADR-0008-no-client-specific-code.md)). Tenant users never access the engine's Desk or portal directly; all customer traffic goes through the platform gateway and web app ([ADR-0016](../decisions/ADR-0016-engine-invisibility.md), `ERP-020`).

Statuses: `in scope` (compiled/exposed in v1), `hidden` (present in engine, blocked from tenant roles/UI/tool API), `deferred` (reserved for a later gate or row).

## 2. DocType scope by area

Child tables (`istable=1`) are listed in parentheses under their parent so `ERP-006` and `BPL-029` have exact targets. Singletons are marked `(S)`, submittables `(Sub)`. Doctype counts per module exclude child tables.

### 2.1 Selling (`Selling` module, plus `Sales Invoice` in `Accounts`)

| DocType | Scope | Gate | Engine module | Reason (golden path / persona / compliance) |
|---|---|---|---|---|
| `Customer` | in scope | G1 | Selling | Golden path (`CUST-001`); Sales & Accountant master |
| `Customer Credit Limit` (child) | in scope | G2 | Selling | Credit limit control (`ERP-011`, Owner/Accountant) |
| `Sales Order` (Sub; `Sales Order Item`) | in scope | G1 | Selling | Golden path step 1; Sales & Warehouse handoff |
| `Quotation` (Sub; `Quotation Item`) | in scope | G2 | Selling | Sales persona quoting before order ([module-map](../product/module-map.md)) |
| `Sales Team` (child) | in scope | G2 | Selling | Sales rep attribution and commission (`ERP-011`, PROPOSED) |
| `Selling Settings` (S) | in scope | G1 | Selling | Enforces price-list rate governance and order/delivery checks |
| `Product Bundle` (`Product Bundle Item`) | hidden | - | Selling | Kit/bundle assembly not in v1 golden path (PROPOSED hidden) |
| `Installation Note` (`Installation Note Item`) | hidden | - | Selling | Field-service installation out of trading v1 scope |
| `Party Specific Item` | hidden | - | Selling | Customer-specific item codes not needed in v1 (PROPOSED hidden) |
| `Industry Type`, `Sales Partner Type`, `SMS Center` (S) | hidden | - | Selling | Legacy CRM/SMS utilities unused by the platform |

### 2.2 Buying (`Buying` module)

| DocType | Scope | Gate | Engine module | Reason |
|---|---|---|---|---|
| `Supplier` | in scope | G2 | Buying | Vendor master for purchasing and AP (Accountant/Warehouse) |
| `Purchase Order` (Sub; `Purchase Order Item`) | in scope | G2 | Buying | Core purchasing flow (`F-10`, Warehouse/Owner) |
| `Buying Settings` (S) | in scope | G2 | Buying | Enforces PO/PR matching and supplier rate controls |
| `Request for Quotation`, `Supplier Quotation` (Sub) | hidden | - | Buying | RFQ bidding omitted from core v1 flow (PROPOSED hidden; `Material Request` covers internal requests) |
| `Supplier Scorecard*` (5 doctypes) | hidden | - | Buying | Vendor scoring analytics out of v1 scope |

### 2.3 Stock (`Stock` module)

| DocType | Scope | Gate | Engine module | Reason |
|---|---|---|---|---|
| `Item` (`Item Barcode`, `Item Default`, `Item Tax`, `UOM Conversion Detail`) | in scope | G1 | Stock | Golden path (`ITEM-001`), sales/buying/stock master |
| `Item Price` | in scope | G1 | Stock | Golden path price-list rate lookup (`BPL-029`) |
| `Price List` | in scope | G1 | Stock | Required by `Item Price` and multi-tier pricing (`ERP-011`) |
| `Warehouse` | in scope | G1 | Stock | Golden path (`W1`), multi-branch stock balance |
| `Delivery Note` (Sub; `Delivery Note Item`) | in scope | G1 | Stock | Golden path step 2; posts COGS and Inventory |
| `Purchase Receipt` (Sub; `Purchase Receipt Item`) | in scope | G2 | Stock | Receiving against PO; posts Inventory and SRBNB |
| `Stock Entry` (Sub; `Stock Entry Detail`), `Stock Entry Type` | in scope | G1 | Stock | Warehouse transfers, adjustments, opening stock |
| `Stock Reconciliation` (Sub; `Stock Reconciliation Item`) | in scope | G1 | Stock | Opening stock balance and physical counts (Warehouse persona) |
| `Material Request` (Sub; `Material Request Item`) | in scope | G2 | Stock | Reorder and internal purchase/transfer requests ([module-map](../product/module-map.md)) |
| `Stock Ledger Entry`, `Bin` | in scope | G1 | Stock | Read-only engine ledger & bin qty; `ERP-014`/`ERP-015` checks |
| `Stock Settings` (S) | in scope | G1 | Stock | Valuation method, negative-stock block, over-delivery block |
| `Repost Item Valuation` (Sub), `Stock Reposting Settings` (S) | in scope | G1 | Stock | Engine internal valuation reposting (system-only, hidden from tenant roles) |
| `Batch`, `Serial and Batch Bundle` (Sub) | hidden | - | Stock | Optional per tenant (`module-map`: batches optional); enabled only via `ERP-011` component (PROPOSED) |
| `Landed Cost Voucher` (Sub) | hidden | - | Stock | Import landed-cost allocation; deferred/optional `ERP-011` candidate (PROPOSED) |
| `Serial No`, `Quality Inspection*`, `Pick List`, `Packing Slip`, `Delivery Trip`, `Delivery Settings` (S), `Shipment*`, `Putaway Rule`, `Item Alternative`, `Item Attribute`, `Item Variant Settings` (S), `Item Manufacturer`, `Manufacturer`, `Customs Tariff Number`, `Inventory Dimension`, `Quick Stock Balance` (S), `Closing Stock Balance`, `Stock Reservation Entry`, `UOM Category` | hidden | - | Stock | Advanced warehousing, variants, QA, and shipping logistics out of v1 trading scope |

### 2.4 Accounts (`Accounts` module)

| DocType | Scope | Gate | Engine module | Reason |
|---|---|---|---|---|
| `Account` | in scope | G1 | Accounts | Chart of accounts tree (Golden path, `CMP-006`) |
| `Sales Invoice` (Sub; `Sales Invoice Item`, `Sales Taxes and Charges`, `Sales Invoice Advance`) | in scope | G1 | Accounts | Golden path step 3, credit notes (`is_return`), VAT, e-invoicing (`CMP-003`) |
| `Purchase Invoice` (Sub; `Purchase Invoice Item`, `Purchase Taxes and Charges`, `Purchase Invoice Advance`) | in scope | G2 | Accounts | Supplier bills, debit notes (`is_return`), input VAT |
| `Payment Entry` (Sub; `Payment Entry Reference`, `Payment Entry Deduction`) | in scope | G2 | Accounts | Customer receipts, supplier payments, internal transfers (`F-10`) |
| `Journal Entry` (Sub; `Journal Entry Account`) | in scope | G1 | Accounts | Opening balances (Golden path) and manual accounting adjustments |
| `GL Entry`, `Payment Ledger Entry` | in scope | G1 | Accounts | Read-only immutable postings; Accountant audit & `ERP-014` |
| `Fiscal Year` | in scope | G1 | Accounts | Required for all GL postings and `CMP-025` |
| `Accounting Period`, `Period Closing Voucher` (Sub) | in scope | G2 | Accounts | Period lock and year-end close ([module-map](../product/module-map.md)) |
| `Sales Taxes and Charges Template`, `Purchase Taxes and Charges Template`, `Item Tax Template`, `Tax Category`, `Tax Rule` | in scope | G1 | Accounts | Deterministic country-pack VAT setup (`CMP-006`, `CMP-021`) |
| `Mode of Payment`, `Bank`, `Bank Account` | in scope | G2 | Accounts | Payment methods, bank accounts, invoice bank details |
| `Bank Transaction` (Sub), `Bank Reconciliation Tool` (S), `Bank Statement Import` | in scope | G2 | Accounts | Bank reconciliation for Accountant persona ([module-map](../product/module-map.md)) |
| `Payment Term`, `Payment Terms Template` | in scope | G2 | Accounts | Credit terms on orders and invoices |
| `Cost Center` | in scope | G2 | Accounts | Default cost centre required by Company; branch/dept tracking |
| `Pricing Rule` | in scope | G2 | Accounts | Tier/volume discounts if enabled by `ERP-011` |
| `Exchange Rate Revaluation` (Sub) | in scope | G2 | Accounts | Multi-currency period revaluation ([module-map](../product/module-map.md)) |
| `Accounts Settings` (S) | in scope | G1 | Accounts | Over-billing, immutable ledger, credit controller, bill uniqueness |
| `POS Invoice*`, `POS Profile`, `POS Opening Entry`, `POS Closing Entry`, `POS Settings` (S), `Cashier Closing` | hidden | - | Accounts | POS explicitly excluded for v1 ([module-map](../product/module-map.md)) |
| `Loyalty Program`, `Loyalty Point Entry`, `Coupon Code`, `Promotional Scheme` | hidden | - | Accounts | Loyalty and promotions out of v1 scope |
| `Subscription*`, `Process Subscription`, `Process Deferred Accounting`, `Budget`, `Finance Book`, `Dunning*`, `Invoice Discounting`, `Shareholder`, `Share Transfer`, `Share Type`, `Shipping Rule`, `Payment Order`, `Payment Request`, `Bank Guarantee`, `Cheque Print Template`, `Advance Payment Ledger Entry`, `Unreconcile Payment`, `Repost*`, `Opening Invoice Creation Tool` (S), `Chart of Accounts Importer` (S), `Process Statement Of Accounts`, `Ledger Health*`, `Bisect*`, `Account Closing Balance` | hidden | - | Accounts | Deferred/subscription/treasury/internal utilities not exposed to v1 tenant roles (`Opening Invoice Creation Tool` / `Ledger Merge` admin-only if used in `ERP-013`) |
| `Tax Withholding Category` | deferred | G2/G3 | Accounts | Hidden in G1; enable only if verified KSA/Egypt/Qatar pack requires WHT (`K11`, `E3`, `Q1`) |

### 2.5 Shared setup, masters, and core engine (`Setup`, `Contacts`, `Geo`, `Core`, `Custom`, `Workflow`, `Printing`, `HR`, `Payroll`)

| DocType | Scope | Gate | Engine module | Reason |
|---|---|---|---|---|
| `Company` | in scope | G1 | Setup | Tenant legal entity, currency, perpetual inventory, default accounts |
| `Global Defaults` (S) | in scope | G1 | Setup | Default company, currency, rounding toggle |
| `UOM`, `UOM Conversion Factor` | in scope | G1 | Setup | Golden path (`piece`), carton/unit conversions |
| `Item Group`, `Customer Group`, `Supplier Group`, `Territory`, `Brand` | in scope | G1/G2 | Setup | Master classification, default accounts, territory scoping |
| `Sales Person`, `Sales Partner` | in scope | G2 | Setup | Sales rep commission (`ERP-011`, `Sales Partner` optional) |
| `Holiday List` | in scope | G1 | Setup | Country-pack holidays and working days (`CMP-024`) |
| `Currency Exchange`, `Country`, `Currency` | in scope | G1/G2 | Setup / Geo | Country defaults and multi-currency FX rates |
| `Address`, `Contact` | in scope | G1 | Contacts | Customer/supplier addresses and contacts (required on VAT invoices) |
| `Terms and Conditions` | in scope | G2 | Setup | Standard quote/order/invoice terms |
| `User`, `Role`, `Role Profile`, `Module Profile`, `Custom DocPerm`, `User Permission`, `Translation`, `Version`, `Activity Log` | in scope | G1 | Core | Engine RBAC (`ERP-008`), translations (`ERP-006`), audit trail |
| `Custom Field`, `Property Setter`, `Workflow`, `Print Format` | in scope | G1 | Custom / Workflow / Printing | Blueprint-compiled schema extensions, approvals, platform print formats |
| `Employee`, `Department`, `Designation`, `Branch` | deferred | G2 | Setup | Deferred to `ERP-010` (HRMS skeleton; `Branch` earlier only if needed for warehouse scoping, PROPOSED) |
| `HR` (78 doctypes) and `Payroll` (22 doctypes) | deferred | G2/G3 | HR / Payroll | Hidden in G1; minimal subset scoped in `ERP-010` (see Section 4) |
| `Regional` (`UAE VAT Settings`, `UAE VAT Account` (child), `Import Supplier Invoice`, `Lower Deduction Certificate`, `South Africa VAT Settings`) | hidden | - | Regional | Hidden in G1; compliance logic is delivered by the compliance rows (`CMP-002`..`006`, `CMP-021`), not by these built-in records |
| `Driver`, `Vehicle`, `Email Digest`, `Print Heading`, `Authorization Rule`, `Authorization Control` (S), `Transaction Deletion Record`, `Quotation Lost Reason`, `Incoterm`, `Employee Group` | hidden | - | Setup | Fleet/legacy setup features not in v1 (approvals use `Workflow` + gateway policy `SEC-019`) |

## 3. Reports and print formats in scope

### 3.1 Observed reports in scope

All report names below were observed on `erp001.localhost` (and surfaced via the platform semantic layer `OPR-006` / reports UI, never raw Desk):

| Area | Report (observed name) | Gate | Ref DocType | Compliance-relevant |
|---|---|---|---|---|
| Accounts | `General Ledger` | G1 | GL Entry | Yes (statutory audit trail, `ERP-014`) |
| Accounts | `Trial Balance` | G1 | GL Entry | Yes (golden path tie-out, statutory books, `ERP-014`) |
| Accounts | `Accounts Receivable`, `Accounts Receivable Summary` | G1/G2 | Sales Invoice | No (credit/collections; golden path step 4) |
| Accounts | `Accounts Payable`, `Accounts Payable Summary` | G2 | Purchase Invoice | No (supplier ageing) |
| Accounts | `Profit and Loss Statement`, `Balance Sheet`, `Cash Flow` | G2 | GL Entry | Yes (financial statements) |
| Accounts | `Sales Register`, `Item-wise Sales Register` | G2 | Sales Invoice | Yes (output VAT reconciliation) |
| Accounts | `Purchase Register`, `Item-wise Purchase Register` | G2 | Purchase Invoice | Yes (input VAT reconciliation) |
| Accounts | `Customer Ledger Summary`, `Supplier Ledger Summary`, `Gross Profit`, `Delivered Items To Be Billed`, `Received Items To Be Billed`, `Bank Reconciliation Statement` | G2 | Sales/Purchase Invoice, Journal Entry | No (operational finance tie-outs) |
| Stock | `Stock Ledger` | G1 | Stock Ledger Entry | Yes (perpetual inventory audit trail, `ERP-015`) |
| Stock | `Stock Balance` | G1 | Stock Ledger Entry | No (golden path step 4 value tie-out) |
| Stock | `Stock and Account Value Comparison` | G1 | Stock Ledger Entry | Yes (stock vs Inventory GL tie-out, `ERP-014`/`015`) |
| Stock | `Stock Projected Qty`, `Item Shortage Report`, `Stock Ageing`, `Batch-Wise Balance History` (if batches enabled) | G2 | Item, Bin, Stock Ledger Entry | No (warehouse/reorder operations) |
| Selling | `Sales Order Analysis`, `Customer Credit Balance`, `Sales Person-wise Transaction Summary` | G2 | Sales Order, Customer | No (Sales persona & `ERP-011`) |
| Buying | `Purchase Order Analysis`, `Procurement Tracker` | G2 | Purchase Order | No (purchasing operations) |

Country-specific VAT return reports (`CMP-010` KSA, `CMP-012` UAE, and Egypt/Qatar equivalents) are delivered as certified country-pack reports (`compliance` app) rather than relying on unverified built-in `Regional` reports (`UAE VAT 201`, `VAT Audit Report` observed on bench).

### 3.2 Print formats

Per [ADR-0016](../decisions/ADR-0016-engine-invisibility.md) (`WEB-017`), none of the engine's built-in `Print Format` records observed on the bench (`Sales Invoice Print`, `Sales Invoice Return`, `Tax Invoice`, `Simplified Tax Invoice`, `Detailed Tax Invoice`, `Purchase eInvoice`, `Bank and Cash Payment Voucher`, `Credit Note`, `Pick List`, `POS Invoice`, `Return POS Invoice`) may reach customers.

In-scope platform print formats (custom `Print Format` / Jinja or web PDF templates built from brand tokens, `ERP-007`, `ERP-016`):
- **Bilingual Tax Invoice & Credit Note** (`Sales Invoice`, including `is_return=1`) — **G1, compliance-relevant** (`ERP-007`, `CMP-003`). Country-neutral Arabic/English layout for Phase 1A golden path (`GOV-037`); country-pack locked legal layout + QR/hash for regulated markets (`CMP-003`, `CMP-004`).
- **Quotation, Sales Order, Delivery Note, Purchase Order, Payment Voucher** — **G2** (`ERP-016`), tenant-branded bilingual layouts.

## 4. Out of scope for v1 and HRMS deferral

Observed engine modules excluded/hidden in v1:
- **`Manufacturing`** (15 doctypes: `BOM`, `Work Order`, `Job Card`, etc.): deferred (`R3+`, [module-map](../product/module-map.md)); v1 targets trading and distribution, not production.
- **`Projects`** (10 doctypes: `Project`, `Task`, `Timesheet`, etc.): deferred (`R3`, contracting vertical candidate).
- **`Assets`** (14 doctypes: `Asset`, `Asset Depreciation Schedule`, etc.): deferred; fixed-asset subledger not required for v1 trading flows.
- **`CRM`** (16 doctypes: `Lead`, `Opportunity`, `Campaign`, etc.): deferred; sales starts at `Quotation` / `Sales Order`.
- **`Support`** (6 doctypes: `Issue`, `Warranty Claim`, `Service Level Agreement`, etc.): excluded from v1 trading scope.
- **`Subcontracting`** (3 doctypes), **`Quality Management`** (8 doctypes), **`Maintenance`** (2 doctypes): excluded; manufacturing/service-specific.
- **`Website`** (26 doctypes), **`Portal`** (2 doctypes): disabled for tenants ([ADR-0016](../decisions/ADR-0016-engine-invisibility.md), `ERP-020`); customers use the platform web app only.
- **`EDI`**, **`Telephony`**, **`Bulk Transaction`**, **`Communication`**, **`Social`**: hidden from tenant views.
- **Excluded features inside core modules**: Point of Sale (`POS*`, `Cashier Closing`), Loyalty/Coupons/Promotions, Subscriptions, Deferred Accounting, Budgets, Dunning, Drop-shipping/Delivery Trips/Shipments, Item Variants.

**HRMS deferral to `ERP-010` (G2):**
Observed on bench: `hrms` `15.64.8` exposes 78 `HR` doctypes and 22 `Payroll` doctypes. For G1, `Employee` (Setup), `HR`, and `Payroll` are completely hidden. `ERP-010` (G2 skeleton) scopes only: `Employee`, `Department`, `Designation`, `Branch` (Setup); `Leave Type`, `Leave Period`, `Leave Policy`, `Leave Allocation`, `Leave Application` (HR); and `Salary Component`, `Salary Structure`, `Salary Structure Assignment` (Payroll) to prepare for WPS/SIF export (`CMP-015` in G3). Recruitment, onboarding, appraisal, training, expense claims, attendance/check-in, fleet logs, and payroll calculation runs remain excluded until `CMP-015`/`CMP-016` (G3).

## 5. Settings and feature flags to enforce the scope

All settings and fields below were observed on `erp001.localhost` (values shown are observed bench defaults vs required v1 configuration):

1. **Module and UI hiding (configuration, no fork)**:
   - `Module Profile` (`block_modules` table using `Block Module`) assigned on `User.module_profile`: block all out-of-scope `Module Def` names (`Manufacturing`, `Projects`, `Assets`, `CRM`, `Support`, `Subcontracting`, `Quality Management`, `Maintenance`, `Website`, `Portal`, `EDI`, `HR`, `Payroll`, `Regional`).
   - `Domain Settings` (`active_domains` table; observed `Domain` records: `Manufacturing`, `Retail`): keep empty so domain-specific doctypes/fields stay inactive.
   - `Workspace` (`is_hidden = 1` on unused workspaces) and `Role.desk_access = 0` for all tenant roles (`ERP-020`).
2. **Role and permission enforcement (`ERP-008`, `SEC-019`)**:
   - `Role` and `Role Profile` (`User.role_profile_name`): assign narrow platform roles (`platform_owner`, `platform_sales`, `platform_warehouse`, `platform_finance` per `engine-mapping-golden-path.json`) instead of broad built-in roles.
   - `Custom DocPerm`: grant exact CRUD/submit/cancel/export rights and `permlevel` field masks (e.g., hide `Item.valuation_rate` from Sales; hide rates/totals from Warehouse).
   - `User Permission` + `System Settings.apply_strict_user_permissions` (observed default `0`): set `1` when multi-branch/warehouse scoping is active.
3. **Accounting, stock, and rounding guardrails**:
   - `Company.enable_perpetual_inventory` (observed default `1`): keep `1` so `Delivery Note` / `Purchase Receipt` / `Stock Entry` post to GL automatically.
   - `Stock Settings.valuation_method` (observed default `"FIFO"`; `Item.valuation_method` options: `FIFO`, `Moving Average`, `LIFO`): **mismatch with [golden-path-trading-sale.md](golden-path-trading-sale.md)** which specifies Moving Average; resolve before `ERP-014`/`ERP-022` (see Section 8).
   - `Stock Settings.allow_negative_stock` (`0`) and `over_delivery_receipt_allowance` (`0`): keep `0`.
   - `Accounts Settings.over_billing_allowance` (`0`), `unlink_payment_on_cancellation_of_invoice` (`1`), `unlink_advance_payment_on_cancelation_of_order` (`1`): keep as observed.
   - `Accounts Settings.enable_immutable_ledger` (observed default `0`): `PROPOSED` set to `1` ([03-erp-runtime.md](03-erp-runtime.md)); verify cancellation/credit-note behaviour on the bench (`ERP-021`).
   - `Accounts Settings.check_supplier_invoice_uniqueness` (observed default `0`): `PROPOSED` set to `1`.
   - `Selling Settings.editable_price_list_rate` (observed default `0`): keep `0` to enforce price lists (`ERP-011`).
   - `Sales Invoice.update_stock` (observed default `0`): keep `0` when invoicing from `Delivery Note` so stock is not deducted twice.
   - `System Settings.rounding_method` (observed default `"Banker's Rounding (legacy)"`; options: `Banker's Rounding (legacy)`, `Banker's Rounding`, `Commercial Rounding`): **mismatch with `BPL-029` mapping fixture** (`half_up`); resolve before `ERP-014` (Section 8). `Global Defaults.disable_rounded_total` (observed `0`): confirm per country pack.
4. **Engine invisibility (`ADR-0016`, `ERP-020`)**:
   - `System Settings`: `enable_telemetry = 0` (observed `1`), `disable_system_update_notification = 1` (observed `0`), `enable_onboarding = 0` (observed `0`), and replace `app_name` (observed `"ERPNext"`) and `otp_issuer_name` (observed `"Frappe Framework"`). Gateway strips engine paths/headers/cookies (`PLT-024`).

## 6. Consequences for the four phase-1 markets

Per [ADR-0024](../decisions/ADR-0024-four-phase-1-markets.md), KSA, UAE, Egypt, and Qatar have no fixed launch order. Core `Selling`, `Buying`, `Stock`, and `Accounts` doctypes remain country-neutral; market differences live in certified Country Packs ([../architecture/country-packs.md](../architecture/country-packs.md), `CMP-021`):
- **Chart of accounts and tax configuration**: `Account` tree, `Sales Taxes and Charges Template`, `Purchase Taxes and Charges Template`, `Item Tax Template`, `Tax Category`, `Tax Rule` (`CMP-006`, `CMP-028`, `CMP-029`, `CMP-031`). Tax rates and rules are out of scope here; see [../compliance/country-matrix.md](../compliance/country-matrix.md).
- **E-invoicing extensions**: custom fields, status tracking, and signing/submission hooks on `Sales Invoice` (and `Purchase Invoice` if inbound applies) — KSA ZATCA (`CMP-002`..`004`), UAE DCTCE/Peppol (`CMP-009`, `CMP-011`), Egypt (`CMP-027`, `CMP-028`, `UNVERIFIED`), Qatar (`CMP-030`, `CMP-031`, `UNVERIFIED`).
- **Print formats, language, and calendars**: legal invoice layout and mandatory Arabic fields (`ERP-007`, `ERP-016`), `Holiday List` (`CMP-024`), `Fiscal Year` (`CMP-025`), and Gregorian/Hijri display (`CMP-005`, `CMP-022`, `ERP-019`).
- **Deferred tax types**: `Tax Withholding Category` remains hidden unless verified country research (`K11`, `E3`, `Q1`) requires it.

## 7. Inputs for dependent rows

- **`ERP-006` (Arabic and RTL translation completion)**: translate and verify UI/field/report/error strings (`Translation`) for all G1+G2 in-scope masters, transactions, and child tables in Section 2 (`Customer`, `Supplier`, `Item`, `Item Price`, `Price List`, `Warehouse`, `Account`, `Cost Center`, `Fiscal Year`, `UOM`, `Address`, `Contact`, `Mode of Payment`, `Bank Account`, `Payment Terms Template`, `Quotation`/`Item`, `Sales Order`/`Item`, `Delivery Note`/`Item`, `Sales Invoice`/`Item`/`Sales Taxes and Charges`, `Material Request`/`Item`, `Purchase Order`/`Item`, `Purchase Receipt`/`Item`, `Purchase Invoice`/`Item`/`Purchase Taxes and Charges`, `Payment Entry`/`Reference`, `Journal Entry`/`Account`, `Stock Entry`/`Detail`, `Stock Reconciliation`/`Item`) and all reports in Section 3.
- **`ERP-010` (HRMS skeleton, G2)**: use only the minimal `Setup`/`HR`/`Payroll` subset in Section 4; block all other 90+ HRMS doctypes.
- **`ERP-011` (Component pack v1, G2)**: build configurable components on `Price List` + `Item Price` + `Pricing Rule`, `Customer Credit Limit` + `Accounts Settings.credit_controller`, and `Sales Person` + `Sales Team`.
- **`ERP-014` (Accounting correctness property tests, G1)**: test GL and Stock Ledger invariants across: (1) opening balance (`Journal Entry` / `Stock Reconciliation`) tying Inventory GL to stock value; (2) `Delivery Note` COGS/Inventory posting under perpetual inventory; (3) `Sales Invoice` (`update_stock=0`) AR/Sales/discount/tax posting and rounding (`System Settings.rounding_method`); (4) `Purchase Receipt` -> `Purchase Invoice` (`Stock Received But Not Billed` clearing) and `Payment Entry` (`Payment Ledger Entry` tie-out); (5) negative-stock, over-delivery, over-billing blocks, and `enable_immutable_ledger` cancellations/credit notes.

## 8. Open questions and founder decisions needed

Tracked in [../open-questions.md](../open-questions.md) as Q-21 to Q-24:
1. **Inventory valuation default (`FIFO` vs `Moving Average`)**: Bench `Stock Settings.valuation_method` defaults to `FIFO`, while [golden-path-trading-sale.md](golden-path-trading-sale.md) assumes Moving Average. Decide whether provisioning sets `Moving Average` or the golden path uses `FIFO`.
2. **Rounding method (`Banker's Rounding (legacy)` vs `Commercial Rounding`)**: Bench `System Settings.rounding_method` defaults to `Banker's Rounding (legacy)`, while `BPL-029` expects `half_up` (`Commercial Rounding`). Decide standard v1 tenant setting (`ERP-014`).
3. **Immutable ledger (`Accounts Settings.enable_immutable_ledger`)**: Observed default is `0`. Confirm setting to `1` and verify cancel/credit-note ergonomics on the bench (`ERP-021`).
4. **Optional v1 trading doctypes**: Confirm whether `Batch` / `Serial and Batch Bundle`, `Landed Cost Voucher`, and `Request for Quotation` / `Supplier Quotation` stay hidden by default and ship only as optional `ERP-011` components.
