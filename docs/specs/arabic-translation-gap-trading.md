# Arabic translation gap audit for the trading scope

Status: draft
Owner: partner

Plan ID: ERP-006, step 1 of the row (measure the gap). This document writes no Arabic wording. The row stays `doing` until the gap is closed and reviewed.

Measured read-only on 2026-11-14 on the pinned synthetic bench (site `erp001.localhost`; Frappe 15.126.0, ERPNext 15.124.5, HRMS 15.64.8). Scope comes from [core-module-scope-trading.md](core-module-scope-trading.md) (ERP-005), sections 2, 3 and 7.

## 1. Headline

1. **Arabic does not load on the bench at runtime.** The engine looks for compiled catalogues in `sites/assets/locale` (`frappe/gettext/translate.py`, `get_locale_dir`). On our bench that folder does not exist: the compiled `frappe.mo` and `erpnext.mo` sit in `assets/locale/ar/LC_MESSAGES` at the bench root, The upstream image's entrypoint (`/usr/local/bin/entrypoint.sh`) creates the link `sites/assets -> assets` at startup; our `infra/dev/docker/entrypoint.sh` replaces that entrypoint and does not create the link. The same missing link means the bench serves no built static assets either. There is no compiled `hrms.mo` at all, because the Dockerfile installs HRMS with pip and never compiles its catalogue into `assets/locale`. The engine's own loader (`get_translations_from_apps("ar")`) returned **0** strings. There are **0** `Translation` records for `ar` on the site. This was a bench defect, not a gap in upstream translations; it is fixed in PR #39 (section 6, task 1).
2. **The shipped Arabic source catalogues cover the in-scope screens well.** Of 1922 unique in-scope strings, 1770 (92.1%) have a non-fuzzy Arabic entry in the shipped `ar.po` files; 152 are missing. All 30 unconditional in-scope report names are translated, and so is the batch-only `Batch-Wise Balance History`.
3. **Most of the gap is in settings screens** (`Accounts Settings` 32 missing, `Stock Settings` 27, `Buying Settings` 12, `Selling Settings` 9). Tenants never see these screens directly; the platform configures them. The gap on the transaction screens (orders, invoices, delivery notes, payments) is small.
4. **Coverage is not correctness.** No one has checked that the existing Arabic accounting and tax terms are right. That needs a human Arabic-speaking accountant (section 5).

## 2. Method (rerunnable)

- **Strings counted**, per in-scope doctype (including the child tables listed in ERP-005): the doctype name; every field `label` except `Column Break` and `Fold` (section and tab labels are included); field `description` when under 300 characters; each non-numeric option of `Select` fields. Source: `frappe.get_meta(doctype).fields` on the site. Doctypes counted: the in-scope rows and the child tables named in parentheses in ERP-005 section 2, matching the ERP-006 list in its section 7. Not counted: `Repost Item Valuation` and `Stock Reposting Settings` (system-only), the engine-admin doctypes at the end of ERP-005 section 2.5 (`User` to `Print Format`), and child tables ERP-005 does not name. Report names: the 30 unconditional reports in ERP-005 section 3.1 (the batch-only report was checked separately and is translated).
- **Translation sources**: `apps/frappe/frappe/locale/ar.po`, `apps/erpnext/erpnext/locale/ar.po`, `apps/hrms/hrms/locale/ar.po`, parsed with Babel's `read_po`. Entries with a message context, plural entries and fuzzy entries are ignored. Non-empty entries across the three files: 15,996, of which 15,846 differ from the English; fuzzy entries: 0.
- **Translated** means: the source string, with leading and trailing whitespace removed, has a non-empty Arabic entry that differs from the English. The whitespace is removed because the engine's `frappe._()` strips the message before looking it up, so this matches what the engine would show. Otherwise matching is exact: case and punctuation differences count as missing.
- **Consequence:** 10 strings exist in the shipped `ar.po` only with a trailing space or newline (for example `Finished Good Quantity ` and `Select Dispatch Address `). The engine cannot find them after stripping, so they are counted as missing. Counted without stripping, the totals would be 1,925 unique, 1,783 translated, 142 missing (reviewer recomputation, 2026-11-14).
- **Runtime check**: `frappe.translate.get_translations_from_apps("ar")` and a count of `Translation` records with `language = ar`.
- The script ran inside the engine container against the site with no writes. It is a session helper and is not committed (repo rule); the bullets above are enough to rewrite it. Totals per group count a string once per doctype; the overall total counts each unique string once.

## 3. Coverage by area

| Area | Strings | Translated | Missing | Coverage |
|---|---|---|---|---|
| Selling | 557 | 537 | 20 | 96.4% |
| Buying | 348 | 326 | 22 | 93.7% |
| Stock | 1119 | 1063 | 56 | 95.0% |
| Accounts | 1486 | 1420 | 66 | 95.6% |
| Setup and masters | 369 | 356 | 13 | 96.5% |
| **Sum of areas** | 3879 | 3702 | 177 | 95.4% |
| **Unique strings overall** | 1922 | 1770 | 152 | 92.1% |
| Report names (30) | 30 | 30 | 0 | 100.0% |

Missing by kind: 107 labels, 45 select options, 25 descriptions, 0 doctype names (counted per doctype).

## 4. Missing strings (complete list)

Each entry is `English source` (kind). Repeated strings appear once per doctype.

- **Customer** (5 of 73): `CUST-.YYYY.-` (select option); `From Opportunity` (label); `From Prospect` (label); `Internal Customer` (label); `Mention if non-standard Receivable account` (description)
- **Sales Order** (1 of 150): `SAL-ORD-.YYYY.-` (select option)
- **Sales Order Item** (2 of 100): `Additional Discount per Stock Unit` (label); `Tax-exclusive additional discount carried from a source document, per stock unit.` (description)
- **Quotation** (1 of 112): `SAL-QTN-.YYYY.-` (select option)
- **Quotation Item** (2 of 66): `Additional Discount per Stock Unit` (label); `Tax-exclusive additional discount carried from a source document, per stock unit.` (description)
- **Selling Settings** (9 of 45): `Allow Negative rates for Items` (label); `Calculate Product Bundle Price based on Child Items' Rates` (label); `Don't Reserve Sales Order Qty on Sales Return` (label); `Enable Discount Accounting for Selling` (label); `How often should Project and Company be updated based on Sales Transactions? Daily refreshes nightly; Monthly refreshes on the 1st of each month.` (description); `Role Allowed to Override Stop Action` (label); `Sales Update Frequency in Company and Project` (label); `Set Incoming Rate as Zero for Expired Batch` (label); `Use Prices from Default Price List as Fallback` (label)
- **Supplier** (4 of 65): `Internal Supplier` (label); `SUP-.YYYY.-` (select option); `Supplier Primary Address` (label); `Supplier Primary Contact` (label)
- **Purchase Order** (3 of 134): `Base Tax Withholding Net Total` (label); `PUR-ORD-.YYYY.-` (select option); `Tax Withholding Net Total` (label)
- **Purchase Order Item** (3 of 92): `Additional Discount per Stock Unit` (label); `Apply TDS` (label); `Tax-exclusive additional discount carried from a source document, per stock unit.` (description)
- **Buying Settings** (12 of 57): `Auto Create Purchase Receipt` (label); `Auto Create Subcontracting Order` (label); `Bill for Rejected Quantity in Purchase Invoice` (label); `Disable Last Purchase Rate` (label); `How often should Project be updated of Total Purchase Cost ?` (description); `Naming Series and Price Defaults` (label); `Role Allowed to Override Stop Action` (label); `Set Valuation Rate for Rejected Materials` (label); `Show Pay Button in Purchase Order Portal` (label); `Update frequency of Project` (label); `Validate Consumed Qty (as per BOM)` (label); `While making a Purchase Receipt or Purchase Invoice from a Purchase Order, use the exchange rate on its posting date rather than inheriting it from the Purchase Order.` (description)
- **Item** (3 of 116): `FIFO` (select option); `LIFO` (select option); `STO-ITEM-.YYYY.-` (select option)
- **Item Barcode** (10 of 18): `EAN` (select option); `EAN-12` (select option); `EAN-8` (select option); `GS1` (select option); `GTIN` (select option); `ISBN-10` (select option); `ISBN-13` (select option); `ISSN` (select option); `PZN` (select option); `UPC-A` (select option)
- **Delivery Note** (2 of 139): `MAT-DN-.YYYY.-` (select option); `MAT-DN-RET-.YYYY.-` (select option)
- **Delivery Note Item** (2 of 87): `Additional Discount per Stock Unit` (label); `Tax-exclusive additional discount carried from a source document, per stock unit.` (description)
- **Purchase Receipt** (4 of 127): `Base Tax Withholding Net Total` (label); `MAT-PR-RET-.YYYY.-` (select option); `MAT-PRE-.YYYY.-` (select option); `Tax Withholding Net Total` (label)
- **Purchase Receipt Item** (3 of 111): `Additional Discount per Stock Unit` (label); `Apply TDS` (label); `Tax-exclusive additional discount carried from a source document, per stock unit.` (description)
- **Stock Entry** (2 of 86): `Finished Good Quantity` (label); `MAT-STE-.YYYY.-` (select option)
- **Stock Entry Detail** (1 of 61): `Is Scrap Item` (label)
- **Stock Reconciliation** (1 of 20): `MAT-RECO-.YYYY.-` (select option)
- **Material Request** (1 of 49): `MAT-MR-.YYYY.-` (select option)
- **Stock Settings** (27 of 91): `Allow Internal Transfers at Arm's Length Price` (label); `Auto Create Serial and Batch Bundle For Outward` (label); `Auto Insert Item Price If Missing` (label); `Auto Reserve Serial and Batch Nos` (label); `Auto Reserve Stock for Sales Order on Purchase` (label); `Convert Item Description to Clean HTML in Transactions` (label); `Disable Serial No And Batch Selector` (label); `Do Not Update Serial / Batch on Creation of Auto Bundle` (label); `Do Not Use Batch-wise Valuation` (label); `Enable Stock Reservation` (label); `FIFO` (select option); `Have Default Naming Series for Batch ID?` (label); `If enabled, do not update serial / batch values in the stock transactions on creation of auto Serial
 / Batch Bundle.` (description); `LIFO` (select option); `Over Picking Allowance` (label); `Over Transfer Allowance` (label); `Partial stock can be reserved. For example, If you have a Sales Order of 100 units and the Available Stock is 90 units then a Stock Reservation Entry will be created for 90 units.` (description); `Quality Inspection Settings` (label); `Role Allowed to Create/Edit Back-dated Transactions` (label); `Serial & Batch Item Settings` (label); `Show Barcode Field in Stock Transactions` (label); `Stock Transactions Settings` (label); `Stock UOM Quantity` (label); `Update Existing Price List Rate` (label); `Update Price List Based On` (label); `Use Serial / Batch Fields` (label); `Validate Material Transfer Warehouses` (label)
- **Account** (2 of 61): `Lft` (label); `Rgt` (label)
- **Sales Invoice** (4 of 197): `ACC-SINV-.YYYY.-` (select option); `ACC-SINV-RET-.YYYY.-` (select option); `Changes` (label); `Issue a debit note with 0 qty against an existing Sales Invoice` (description)
- **Sales Invoice Item** (4 of 94): `Additional Discount per Stock Unit` (label); `Asset Gross Value` (label); `Asset Value After Depreciation` (label); `Tax-exclusive additional discount carried from a source document, per stock unit.` (description)
- **Sales Taxes and Charges** (2 of 30): `Basis for tax calculation` (description); `Dont Recompute tax` (label)
- **Purchase Invoice** (6 of 178): `ACC-PINV-.YYYY.-` (select option); `ACC-PINV-RET-.YYYY.-` (select option); `Base Tax Withholding Net Total` (label); `Select Dispatch Address` (label); `Tax Withheld Vouchers` (label); `Tax Withholding Net Total` (label)
- **Purchase Invoice Item** (3 of 98): `Additional Discount per Stock Unit` (label); `Apply TDS` (label); `Tax-exclusive additional discount carried from a source document, per stock unit.` (description)
- **Purchase Taxes and Charges** (1 of 35): `Basis for tax calculation` (description)
- **Payment Entry** (4 of 94): `ACC-PAY-.YYYY.-` (select option); `Account Balance (From)` (label); `Account Balance (To)` (label); `Payment Term Discounts Calculated` (label)
- **Payment Entry Reference** (2 of 22): `Discount applied in the reference document currency.` (description); `Payment Term Discount` (label)
- **Journal Entry** (1 of 70): `ACC-JV-.YYYY.-` (select option)
- **Bank Transaction** (1 of 33): `ACC-BTN-.YYYY.-` (select option)
- **Bank Statement Import** (1 of 32): `If your CSV uses a different delimiter, add that character here, ensuring no spaces or additional characters are included.` (description)
- **Pricing Rule** (3 of 94): `Conditions will be applied on all the selected items combined.` (description); `PRLE-.####` (select option); `System will notify to increase or decrease quantity or amount` (description)
- **Accounts Settings** (32 of 124): `Allow multi-currency invoices against single party account` (label); `Auto Reconcile Payments` (label); `Auto Reconciliation Job Trigger` (label); `Automatically Add Taxes from Taxes and Charges Template` (label); `Automatically Fetch Payment Terms from Order/Quotation` (label); `Book Tax Loss on Early Payment Discount` (label); `Chart Of Accounts` (label); `Credit Limit Settings` (label); `Data Fetch Method` (label); `Delete Accounting and Stock Ledger Entries on deletion of Transaction` (label); `Fetch Valuation Rate for Internal Transaction` (label); `Financial reports will be generated using GL Entry doctypes (should be enabled if Period Closing Voucher is not posted for all years sequentially or missing)` (description); `Ignore Account Closing Balance` (label); `Learn about <a href="https://docs.erpnext.com/docs/v13/user/manual/en/accounts/articles/common_party_accounting#:~:text=Common%20Party%20Accounting%20in%20ERPNext,Invoice%20against%20a%20primary%20Supplier.">Common Party</a>` (description); `Maintain Same Rate Throughout Internal Transaction` (label); `Merge Similar Account Heads` (label); `POS Setting` (label); `Payment Entry Settings` (label); `Payment Request created from Sales Order or Purchase Order will be in Draft status. When disabled document will be in unsaved state.` (description); `Period Closing Settings` (label); `Posting Date Inheritance for Exchange Gain / Loss` (label); `Reconciliation Queue Size` (label); `Role Allowed to Over Bill` (label); `Role Allowed to Override Stop Action` (label); `Role allowed to bypass Credit Limit` (label); `Round Tax Amount Row-wise` (label); `Show Account Balance` (label); `Show Balances in Chart Of Accounts` (label); `Show Party Balance` (label); `Show Taxes as Table in Print` (label); `The percentage you are allowed to bill more against the amount ordered. For example, if the order value is $100 for an item and tolerance is set as 10%, then you are allowed to bill up to $110` (description); `Use Legacy Controller For Period Closing Voucher` (label)
- **Company** (3 of 115): `If <b>Enabled</b> - Reconciliation happens on the <b>Advance Payment posting date</b><br>
If <b>Disabled</b> - Reconciliation happens on oldest of 2 Dates: <b>Invoice Date</b> or the <b>Advance Payment posting date</b><br>` (description); `Lft` (label); `Rgt` (label)
- **Currency** (10 of 24): `# ###,##` (select option); `# ###.##` (select option); `#'###.##` (select option); `#, ###.##` (select option); `#,###` (select option); `#,###.##` (select option); `#,###.###` (select option); `#,##,###.##` (select option); `#.###` (select option); `#.###,##` (select option)

## 5. Risks a count cannot show

All UNVERIFIED unless stated.
- **Accounting and tax terms.** Existing Arabic entries for terms such as debit, credit, cost of goods sold, input and output VAT, credit note and fiscal year may be wrong or vary by market. A human Arabic-speaking accountant must review them; an AI review is not enough (AGENTS.md principle 3).
- **Right words, wrong place.** One English string can carry different meanings on different screens. Exact matching cannot show this.
- **Messages from code.** Validation errors and messages raised from Python and JavaScript were not counted. Customers see errors through our gateway, so those must be mapped to platform i18n anyway (ADR-0016).
- **Formatting.** Number, date, currency and Hijri display were not checked (CMP-005, ERP-019).
- **RTL print layout.** Not checked; the bilingual tax invoice is ERP-007.
- **Report columns.** Column labels of script reports are built in code and were not counted.

## 6. How to close the gap without forking (PROPOSED tasks)

Customers never see the engine screens (ADR-0016), so most text customers read comes from the platform's own i18n. Engine translations still matter for anything the engine renders that reaches customers (print formats, emails if any, values passed through the gateway) and for our staff.

Mechanisms observed in the engine: compiled gettext catalogues per app (`.mo` under `sites/assets/locale`), and site-level `Translation` records that override them. Neither needs a fork. Upstream contribution of missing strings is possible but not required.

1. **Fix runtime loading on the bench** (partner, `infra/dev/docker`). Make compiled catalogues available under `sites/assets/locale` and compile HRMS's catalogue at build time. Check: `get_translations_from_apps("ar")` returns more than 0 strings and a known label renders in Arabic. Done in PR #39 (ERP-001): the entrypoint now creates the link and the build compiles the HRMS catalogue; with the rebuilt image the engine loads 16,144 Arabic strings, including HRMS labels. The running bench uses the earlier image until it is recreated.
2. **Make this audit a script with a plan row** in `scripts/` or `infra/dev/docker` so CI can rerun it on every version bump (ERP-004 gate 6). Check: same numbers as section 3 on the same pins.
3. **Supply the 152 missing strings** as site `Translation` records shipped through configuration (country pack or base component), not per tenant. Draft wording PROPOSED by a model, then approved by a human. Check: coverage 100% on the in-scope list.
4. **Accountant terminology review** of the accounting and tax terms in scope, per market where wording differs. Check: signed review list in the repo; corrections shipped as `Translation` records.
5. **Platform-side mapping** of engine errors and labels that pass through the gateway into platform i18n keys (with PLT-024). Check: no untranslated engine text in Arabic UI tests.

## 7. Open questions

- Q-28: Who is the Arabic-speaking accountant reviewer for terminology, and do KSA, UAE, Egypt and Qatar need different wording for any terms? (added to [open-questions.md](../open-questions.md))
- Q-29: Should missing strings be contributed upstream as well as shipped as our own `Translation` records? (added to [open-questions.md](../open-questions.md))
