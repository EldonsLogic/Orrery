# KSA chart of accounts and VAT codes

Status: Draft for Tier 3 and Arabic-speaking accountant review

Plan ID: CMP-006

## Chart design

The [Saudi trading chart](../../apps/engine/compliance/ksa/sa_trading_chart_of_accounts.json) follows the Saudi-adopted IFRS for SMEs presentation for an eligible trading or distribution company. It groups current and non-current balances and separates inventory, trade receivables and payables, equity, sales, cost of goods sold and operating expenses. The numbers are platform defaults. SOCPA's endorsement includes Saudi modifications and specifies the transition from the 2015 edition to the 2025 edition for annual periods beginning on or after 2027-01-01, with early application permitted. [SOCPA endorsement, sections 63–64, accessed 2026-11-18](https://www.socpa.org.sa/Socpa/Professional-standards/Accounting-standards/Auditing-Standards-Endorsed.aspx) · [IFRS for SMEs, sections 4, 5, 13 and 17, accessed 2026-11-18](https://www.ifrs.org/content/dam/ifrs/supporting-implementation/smes/2025/ifrs-for-smes-standard-markup.pdf)

| Use | Account numbers and native types |
|---|---|
| Cash, bank and trade balances | `1110 Cash`, `1120 Bank`, `1130 Receivable`, `2110 Payable` |
| Perpetual inventory | `1140 Stock`, `2120 Stock Received But Not Billed`, `5110 Cost of Goods Sold`, `5120 Stock Adjustment`, `5130 Expenses Included In Valuation` |
| Assets and valuation | `1210 Fixed Asset`, `1220 Accumulated Depreciation`, `1230 Capital Work in Progress`, `2130 Asset Received But Not Billed`, `5230 Depreciation`, `5260 Expenses Included In Asset Valuation` |
| Equity and sales | `3100`–`3300 Equity`, `4100 Income Account`, `4200 Direct Income` (sales returns and allowances) |
| Opening and rounding | `1190 Temporary`, `2170 Round Off for Opening` (balance sheet), `5310 Round Off` (profit and loss) |
| VAT | `1151`–`1153 Tax` under assets, `2210` and `2220 Tax` under liabilities, `2230 Current Liability` for settlement |

The Arabic-first bilingual node keys become native account names. On a fresh synthetic company, the pinned importer accepts the `tree` object via `create_charts(company, custom_chart=tree)`. Groups follow from child nodes and each root supplies `root_type`. The [company defaults](../../apps/engine/compliance/ksa/company_account_defaults.json) reference account numbers and cover bilingual names that the engine's name-based fallback cannot resolve. Resolve each number to a unique posting account for the company and set the named Company field to that account's document ID. Opening entries require balance-sheet accounts. [Pinned importer](https://github.com/frappe/erpnext/blob/e5cde8c4b9e3f7f567a92ca3e65fd411402b89ce/erpnext/accounts/doctype/account/chart_of_accounts/chart_of_accounts.py) · [Pinned Account fields](https://github.com/frappe/erpnext/blob/e5cde8c4b9e3f7f567a92ca3e65fd411402b89ce/erpnext/accounts/doctype/account/account.json) · [Pinned Company defaults](https://github.com/frappe/erpnext/blob/e5cde8c4b9e3f7f567a92ca3e65fd411402b89ce/erpnext/setup/doctype/company/company.py) · [Pinned GL Entry validation](https://github.com/frappe/erpnext/blob/e5cde8c4b9e3f7f567a92ca3e65fd411402b89ce/erpnext/accounts/doctype/gl_entry/gl_entry.py), accessed 2026-11-18.

## VAT treatments and sources

The [VAT configuration](../../apps/engine/compliance/ksa/vat_treatments.json) records seven treatments and all 16 reason codes from the published ZATCA XML code list. The reason descriptions are bilingual reviewer labels. For `Z` and `E`, select the reason that applies to the transaction. `VATEX-SA-OOS` requires a case-specific reason from the taxpayer. ZATCA uses `0` in the invoiced-item percentage for `E`, while the underlying treatment is exempt. For `O`, `null` records that the invoice line has no applicable rate. [ZATCA XML implementation standard v1.2, §§8.2 and 11.2.4, BR-Z-05, BR-E-05, BR-KSA-11 and BR-KSA-CL-04, accessed 2026-11-18](https://www.zatca.gov.sa/ar/E-Invoicing/SystemsDevelopers/Documents/20230519_ZATCA_Electronic_Invoice_XML_Implementation_Standard_%20vF.pdf)

| Treatment | Issued invoice code and VAT | Account mapping and primary source |
|---|---|---|
| Domestic standard sale | `S`, 15%, no reason code | `2210` output. [ZATCA VAT rate, accessed 2026-11-18](https://zatca.gov.sa/en/RulesRegulations/VAT/Pages/About-Vat.aspx) |
| Domestic standard purchase with fully deductible VAT | 15%, no issued invoice code | `1151` eligible input. [ZATCA VAT rate](https://zatca.gov.sa/en/RulesRegulations/VAT/Pages/About-Vat.aspx) · [VAT Implementing Regulations, Art. 49–51](https://www.zatca.gov.sa/en/RulesRegulations/Taxes/Documents/Implmenting%20Regulations%20of%20the%20VAT%20Law_EN.pdf), accessed 2026-11-18. |
| Zero-rated sale | `Z`, 0%, 12 eligible reason codes | `2210` at zero. [ZATCA XML §11.2.4 and BR-Z-05](https://www.zatca.gov.sa/ar/E-Invoicing/SystemsDevelopers/Documents/20230519_ZATCA_Electronic_Invoice_XML_Implementation_Standard_%20vF.pdf) · [VAT Implementing Regulations, Ch. 6](https://www.zatca.gov.sa/en/RulesRegulations/Taxes/Documents/Implmenting%20Regulations%20of%20the%20VAT%20Law_EN.pdf), accessed 2026-11-18. |
| Exempt sale | `E`, invoice percentage 0, three eligible reason codes | `2210` at zero. [ZATCA XML §11.2.4 and BR-E-05](https://www.zatca.gov.sa/ar/E-Invoicing/SystemsDevelopers/Documents/20230519_ZATCA_Electronic_Invoice_XML_Implementation_Standard_%20vF.pdf) · [VAT Implementing Regulations, Art. 29–30](https://www.zatca.gov.sa/en/RulesRegulations/Taxes/Documents/Implmenting%20Regulations%20of%20the%20VAT%20Law_EN.pdf), accessed 2026-11-18. |
| Out-of-scope sale | `O`, no applicable rate, `VATEX-SA-OOS` | Classification only. [ZATCA XML §§8.2 and 11.2.4, accessed 2026-11-18](https://www.zatca.gov.sa/ar/E-Invoicing/SystemsDevelopers/Documents/20230519_ZATCA_Electronic_Invoice_XML_Implementation_Standard_%20vF.pdf) |
| Standard-rated goods imports paid at customs | 15%, no issued invoice code | `1152` eligible input. Use the customs declaration as evidence for the amount and the right to deduct. [ZATCA imports and exports guideline, §§4.1–4.4 and 10.3](https://zatca.gov.sa/en/HelpCenter/guidelines/Documents/Guideline-on-Imports-and-Exports-under-VAT-Provision.pdf) · [ZATCA input tax deduction guideline, §4.4](https://www.zatca.gov.sa/en/HelpCenter/guidelines/Documents/Input%20Tax%20Deduction.pdf), accessed 2026-11-18. |
| Standard-rated imported services subject to reverse charge | 15%, no issued invoice code | `2220` self-assessed output and `1153` input to the extent deductible. [ZATCA VAT rate](https://zatca.gov.sa/en/RulesRegulations/VAT/Pages/About-Vat.aspx) · [VAT Implementing Regulations, Art. 47(1)](https://www.zatca.gov.sa/en/RulesRegulations/Taxes/Documents/Implmenting%20Regulations%20of%20the%20VAT%20Law_EN.pdf) · [ZATCA imports and exports guideline, §§6.3 and 10.4](https://zatca.gov.sa/en/HelpCenter/guidelines/Documents/Guideline-on-Imports-and-Exports-under-VAT-Provision.pdf), accessed 2026-11-18. |

Each `engine_template` with a value describes native sales or purchase tax rows for a single treatment. Provide the company and a title from the label, resolve each `account_role` through `posting_accounts` to the same company's `account_head`, and set the row description from the locale label. The four templates require explicit selection. Imports and reverse charge record account roles for reviewed accounting entries. The engine remains the calculation authority. This directory is self-contained so CMP-029 can wrap it using the CMP-021 country-pack framework.

## Accountant review and verification

- **UNVERIFIED** for adoption. Confirm the Arabic labels, applicable SOCPA edition and financial statement mapping, including VAT settlement, refund receivable presentation, opening clearing and equity by entity type (Q-8).
- **UNVERIFIED** end to end. Confirm eligibility and evidence for each reason in the company's actual trade. Verify the invoice component's reason text, mixed-category invoices and credit notes against ZATCA rules. The catalogue alone does not establish transaction eligibility.
- **UNVERIFIED** posting and return treatment. Confirm the workflow for customs declarations, partial and non-deductible input VAT, self-assessed output and settlement against the VAT return (CMP-010). Import VAT accounted for through the return with ZATCA approval needs its own workflow. [ZATCA imports and exports guideline, §5.3, accessed 2026-11-18](https://zatca.gov.sa/en/HelpCenter/guidelines/Documents/Guideline-on-Imports-and-Exports-under-VAT-Provision.pdf)

Run from the repository root:

```sh
python3 -m unittest apps/engine/change_engine/change_engine/tests/test_cmp_006_ksa_accounts.py -v
```

The checks cover native tree structure, unique numbers, bilingual names, valid posting types, company defaults and VAT links. A pinned-bench smoke run imported 58 accounts and saved 20 company defaults and four tax templates on a synthetic site. The four defaults that required explicit links were `round_off_for_opening`, `write_off_account`, `exchange_gain_loss_account` and `disposal_account`. Tier 3 requires line-by-line founder review and security review under [ADR-0031](../decisions/ADR-0031-rigid-zone-code-authorship.md) and [ADR-0035](../decisions/ADR-0035-risk-tiered-review.md).
