# KSA VAT return report: design

Status: Design draft for Tier 3 line-by-line founder review and Saudi accountant review. No code in this file. Not tax advice.

Plan ID: CMP-010 (G2, rigid zone, Tier 3). Depends on CMP-006 ([KSA chart and VAT codes](ksa-coa-and-tax-codes.md)).

Method: the CMP-003 and ERP-015 method applies, as the partner confirmed for this task. An agent drafts deterministic code against this design. A founder reviews it line by line (Tier 3, [ADR-0031](../decisions/ADR-0031-rigid-zone-code-authorship.md), [ADR-0035](../decisions/ADR-0035-risk-tiered-review.md)), and a Saudi accountant reviews it before any production use. Until that review, the output is a **draft worksheet**, never a fileable return.

## 1. Scope and shape

- **What it is.** A pure function `build_vat_return_draft(input) -> ReturnDraft` turns a closed list of deterministic tax lines into return boxes. It makes no engine calls, does no I/O, uses no model and reads no clock (the period comes in with the input).
- **What feeds it.** A separate extractor, outside this design and needing its own plan row, reads the engine's posted documents and produces the input. The engine stays the calculation authority for each document's VAT (ADR-0031). This function only **sums** amounts that are already rounded. It never recomputes the VAT it reports.
- **All or nothing.** If any refusal fires, the output carries the refusals and **no box values**. A partial return is worse than no return.
- **Traceability (principle 8).** Every box value lists the `line_id`s it sums.
- **Proposed location** (for the implementation row to confirm): `components/compliance/zatca_sa/vat_return.py`, with tests in `components/compliance/zatca_sa/tests/test_vat_return.py`, next to the existing rigid `compliance.zatca_sa` component.

## 2. Evidence labels and sources

All sources below were accessed **2026-11-25**. Labels:
- **FETCHED**: the official ZATCA file was downloaded and its text read this session.
- **UNVERIFIED**: no official text was read. Software vendor guides seen in search results (Zoho, Tally, ClearTax, Odoo apps) are SECONDARY and are not cited as authority.

The English guidelines state that the Arabic version prevails.

| Id | Source (official) | Used for |
|---|---|---|
| S1 | [ZATCA Guideline on Imports and Exports under VAT Provision, Second Edition, May 2026](https://zatca.gov.sa/en/HelpCenter/guidelines/Documents/Guideline-on-Imports-and-Exports-under-VAT-Provision.pdf), §5.3, §6.3 (example 7), §10.4 | Field 8 holds import VAT paid to ZATCA. Field 9 holds reverse charge, and import VAT paid through the return once approved. The columns are Amount, Adjustment and VAT Amount. Partial deduction goes in the Field 9 adjustment. |
| S2 | [ZATCA Guideline on Input Tax Deduction under VAT Provisions, Third Version, May 2026](https://zatca.gov.sa/en/HelpCenter/guidelines/Documents/Guideline-on-Input-Tax-Deduction-under-VAT-Provisions.pdf), §4.2, §4.3, §4.4, §10 | Box 7 is standard-rated domestic purchases. Box 8 is imports. In Box 9 the return form deducts reverse-charge VAT automatically, so full deduction leaves no VAT payable. Credit-note input adjustments. |
| S3 | [ZATCA Guideline for Tax Invoicing and Records under VAT Provisions, Version 3, May 2026](https://zatca.gov.sa/en/HelpCenter/guidelines/Documents/Guideline-for-Tax-Invoicing-and-Records-under-VAT-Provisions.pdf), §4.2.4, §7.1.1 | VAT is rounded to the nearest halala, and "the rounded figures used must be the same figures used for the purposes of filing the VAT return". Credit and debit notes go in the Amount or Adjustments field. The §4.2.4 example 6 is internally inconsistent: it says 1,091.30 is "rounded" to 1,195.24, while 1,255.00 − 163.70 = 1,091.30. Do not rely on that example. |
| S4 | [VAT Implementing Regulations (English, amended to Resolution 2-7-21 of 2021-11-09)](https://www.zatca.gov.sa/en/RulesRegulations/Taxes/Documents/Implmenting%20Regulations%20of%20the%20VAT%20Law_EN.pdf), articles headed *Tax Period*, *Payment of Tax*, *Tax Returns*, *Correction of Returns* (Art. 63), *Adjustment to Value of a Supply* (Art. 40), *Credit and Debit Notes*, *Currency Conversion* | Monthly or three-month periods. The return is due by the last day of the following month. Disclosure items. Correction routes. Credit-note period rules. SAMA rate conversion. The extracted text carries no article numbers, so articles are cited by heading. Numbers are given only where S4 itself or S2 confirms them (Art. 40, Art. 63). |
| S5 | [ZATCA Electronic Invoice XML Implementation Standard v1.2 (2023-05-19)](https://zatca.gov.sa/ar/E-Invoicing/SystemsDevelopers/Documents/20230519_ZATCA_Electronic_Invoice_XML_Implementation_Standard_%20vF.pdf), §10 Rounding, BR-CO-17, BR-S-09 | Half-up rounding. VAT category tax amount (BT-117) = taxable amount (BT-116) × rate / 100, rounded to two decimals at document level. This was also read by CMP-037 ([official sources](../research/cmp-037-official-sources.md) §5). |

## 3. Return boxes

Every box has three columns: **Amount (SAR)**, **Adjustment (SAR)** and **VAT Amount (SAR)** (S1 §6.3 table, S2 §4.3 table). Only Boxes 7, 8 and 9 were confirmed by number in official text this session. The other numbers and labels follow the commonly published 16-box layout and are **UNVERIFIED**: confirm them on the ZATCA portal before an implementation hard-codes them. The code uses stable internal box keys, so renumbering is a data change.

| Key | Box | Label (working) | Number evidence | Draft may calculate |
|---|---|---|---|---|
| `sales_standard` | 1 | Standard-rated sales | UNVERIFIED | Yes |
| `sales_citizen_state_borne` | 2 | Private healthcare and education (and possibly first home) to citizens | UNVERIFIED | **No**, refused (R-ZMAP) |
| `sales_zero_domestic` | 3 | Zero-rated domestic sales | UNVERIFIED | Yes, `VATEX-SA-35` only |
| `sales_export` | 4 | Exports | UNVERIFIED | Yes, `VATEX-SA-32` and `-33` only |
| `sales_exempt` | 5 | Exempt sales | UNVERIFIED | Yes, all three `E` codes |
| `sales_total` | 6 | Total sales | UNVERIFIED | Yes (sum of 1–5) |
| `purch_standard_domestic` | 7 | Standard-rated domestic purchases | **FETCHED** S2 §4.2 | Yes, full deduction only |
| `purch_import_customs` | 8 | Imports subject to VAT paid at customs | **FETCHED** S1 §5.3, S2 §4.4 | Yes, full deduction only |
| `purch_reverse_charge` | 9 | Imports subject to VAT accounted for through the reverse charge mechanism | **FETCHED** S1 §6.3, §10.4; S2 §4.3 | Yes, full deduction only. Import VAT through the return is refused (R-IMPRET). |
| `purch_zero` | 10 | Zero-rated purchases | UNVERIFIED | **Not computed**: no CMP-006 treatment exists |
| `purch_exempt` | 11 | Exempt purchases | UNVERIFIED | **Not computed**: no CMP-006 treatment exists |
| `purch_total` | 12 | Total purchases | UNVERIFIED | Yes (sum of 7–9), marked incomplete while 10–11 are not computed |
| `vat_due_current` | 13 | Total VAT due for the current period | UNVERIFIED | Yes (§5) |
| `corrections_prior` | 14 | Corrections from previous periods | UNVERIFIED | **No**, refused (R-CORR) |
| `credit_carried_forward` | 15 | VAT credit carried forward | UNVERIFIED | **No**, refused if non-zero (R-CFWD) |
| `net_vat_due` | 16 | Net VAT due (or claim) | UNVERIFIED | **No**: needs 14 and 15. The draft shows `vat_due_current` only. |

S4 (*Tax Returns*, para 2) lets ZATCA require these disclosures: (a) basic-rate and zero-rate supplies and their output tax; (b) supplies received and deductible input tax; (c) nominal supplies; (d) reverse-charge supplies; (e) internal supplies; (f) import tax through the return and input tax on imports; (g) exempt supplies; (h) other supplies; (i) Art. 51/52 input adjustments; (j) Art. 63(2) corrections. Items (c), (e), (h) and (i) have no CMP-006 treatment. Any line that would need them is refused (R-TREAT).

## 4. Exact mapping: CMP-006 treatment to box

The input `treatment` must be one of the seven keys in `apps/engine/compliance/ksa/vat_treatments.json`. The mapping is closed. Any pair not listed below is refused (R-TREAT).

| `direction` | `treatment` | Invoice category and reason | Box key | Column rule |
|---|---|---|---|---|
| output | `domestic_sale_standard` | `S`, reason `null` | `sales_standard` | §6 |
| output | `sale_zero_rated` | `Z`, `VATEX-SA-35` | `sales_zero_domestic` | §6, VAT must be `0.00` |
| output | `sale_zero_rated` | `Z`, `VATEX-SA-32`, `VATEX-SA-33` | `sales_export` | §6, VAT must be `0.00` |
| output | `sale_zero_rated` | `Z`, `VATEX-SA-EDU`, `VATEX-SA-HEA` | refused R-ZMAP | Box 2 mapping and state-borne VAT handling need accountant sign-off |
| output | `sale_zero_rated` | `Z`, `VATEX-SA-34-1`…`34-5`, `VATEX-SA-36`, `VATEX-SA-MLTRY` | refused R-ZMAP | Box 3 or Box 4 is not settled for transport, metals and military goods |
| output | `sale_exempt` | `E`, `VATEX-SA-29`, `-29-7`, `-30` | `sales_exempt` | §6, VAT must be `0.00` |
| output | `sale_out_of_scope` | `O`, `VATEX-SA-OOS` | none | Excluded from every box. Listed in `excluded_out_of_scope` with a total for the accountant to check (UNVERIFIED that out-of-scope sales are never reported). |
| input | `domestic_purchase_standard` | none | `purch_standard_domestic` | §6, `deductible_share` must be `full` |
| input | `goods_import_standard_at_customs` | none | `purch_import_customs` | Amount = customs value, VAT = customs VAT, `full` only |
| input | `services_reverse_charge_standard` | none | `purch_reverse_charge` | Amount = SAR value of the service, VAT = self-assessed VAT, `full` only. Adds the same VAT to `self_assessed_output` and `deductible_rcm_input`, net zero (S2 §4.3). |

`Z` and `E` both post to `2210` at 0% (CMP-006). The split above is therefore by **category and reason code** on the line, never by account balance. If Q-8 later creates split accounts, the input contract does not change.

## 5. Calculation

All arithmetic runs on integer halalas (1 SAR = 100 halalas) after strict parsing. No floats are used, and no rounding happens anywhere in this function (§7).

For each box key `k`:
- `amount[k]` = Σ signed `taxable_amount` over lines in the Amount column.
- `adjustment[k]` = Σ signed `taxable_amount` over lines in the Adjustment column.
- `vat[k]` = Σ signed `vat_amount` over all lines of `k`, both columns.
- `sales_total` = component-wise sum of Boxes 1, 3, 4 and 5 (Box 2 is refused, so it is always empty when a draft is emitted). `purch_total` = component-wise sum of Boxes 7–9.
- `output_vat` = `vat[sales_total]` + `self_assessed_output`.
- `input_vat` = `vat[purch_standard_domestic]` + `vat[purch_import_customs]` + `deductible_rcm_input`.
- `vat_due_current` = `output_vat` − `input_vat`. A negative value is a claim position. The draft does not decide between refund and carry-forward: that is Box 15 and 16 territory, refused.
- `filing_due_date` = the last day of the month after `period.end` (S4 *Tax Returns* para 1 and *Payment of Tax* para 1, FETCHED).

The draft also shows **`vat_recomputed[k]`** = half-up(|(`amount[k]` + `adjustment[k]`) × rate|) with the sign restored, for `sales_standard` and `purch_standard_domestic`, plus the difference from `vat[k]`. It is shown as information and is never used as a box value. Whether the portal computes the VAT column itself or takes the taxpayer's figure is **UNVERIFIED**. S3 §4.2.4 points to the invoice figures. An accountant decides.

## 6. Signs, credit and debit notes, and periods

**Signs.** Input amounts are **non-negative magnitudes**. The sign comes only from `document_kind`: `invoice` is +1, `debit_note` is +1, `credit_note` is −1. A negative string in the input is refused (R-NEG). This keeps the questions of rounding negative values and of credit notes mirroring invoices (Q-601, ADR-0033) out of the return.

**Column rule for output lines (S3 §7.1.1, FETCHED; S4 Art. 40 paras 4–5):**

| Case | Period | Column |
|---|---|---|
| `invoice` | period containing `tax_date` | Amount |
| `credit_note` or `debit_note`, and the original supply is in the same period, or `original_return_filed` is `false` | period containing `tax_date` (the note's issue date) | Amount, netted |
| `credit_note`, and `original_return_filed` is `true` | the later of the note's issue date and `adjustment_event_date` | Adjustment (negative) |
| `debit_note`, and `original_return_filed` is `true` | period containing `adjustment_event_date` | Amount |

For a note, `tax_date` is its issue date and `adjustment_event_date` is required. The date the rule selects must fall within the period, or the line is refused (R-PERIOD). The function never moves a line to another period by itself. **UNVERIFIED**: whether the portal expects the Adjustment column as a negative number or as a positive amount it subtracts. S1's Box 9 example shows a positive 30,000 that reduces the deduction. The draft emits signed values and flags the presentation for the accountant.

**Input-side notes.** S2 §10 and S4 Art. 40(6) say the customer corrects input tax in the period the note was issued. The draft nets a purchase note into the Amount column only when the original purchase is in the same period. A cross-period purchase note is refused (R-PNOTE) until the accountant confirms its column.

**Periods (S4 *Tax Period*, FETCHED).** Monthly applies when annual taxable supplies exceed SAR 40,000,000. Otherwise the standard period is three months, and ZATCA may approve or direct a change. The function does **not** derive the frequency. `period.frequency` is an input that records what ZATCA assigned. The function checks that `start` is the first day of a month, `end` is the last day of the same month (monthly) or of the second month after it (quarterly), and every invoice's `tax_date`, and every note's selected date (above), falls within [`start`, `end`]. Quarter alignment (calendar or registration-based) is **UNVERIFIED**, so any three whole consecutive months are accepted, with a warning. A period starting before 2020-07-01 is refused (R-RATE): the earlier 5% rate and transitional rules are out of scope.

**Corrections (S4 Art. 63, FETCHED).** An understatement must be notified within 20 days through a correction submission. If the understatement of Net Tax is under SAR 5,000, it may instead be adjusted in the next return. An overstatement may be adjusted in any later return, and never after five years from the end of the calendar year of the period. A correction must state the periods, the output and input tax corrected per period, and the reason. Whether the SAR 5,000 test applies per error, per period or in aggregate is a legal reading, so the draft refuses every correction entry (R-CORR) and quotes these routes in the refusal text. Bad-debt (Art. 40 paras 10–11) and capital-asset adjustments are also refused (R-TREAT).

## 7. Rounding stages

| Stage | Where | Rule | Evidence |
|---|---|---|---|
| 0. Document VAT | Upstream: the engine and the invoice component (CMP-003), with ZATCA XML for CMP-004 | Half-up. BT-117 = BT-116 × rate / 100, rounded to 2 decimals per VAT category **at document level**, not summed from rounded line amounts. Round final results only. | S5 §10, BR-CO-17, BR-S-09 (FETCHED). Whether this e-invoice standard binds the ledger is an open legal point (CMP-037 §5, Q-601). |
| 0a. Platform setting | Engine | "Commercial Rounding", ties away from zero, including negatives | ADR-0033, a founder decision and not a ZATCA rule. For positive values it matches S5 half-up. Python `Decimal` `ROUND_HALF_UP` also rounds ties away from zero, checked locally: `-0.015` → `-0.02`. |
| 1. Input check | This function | No rounding. Any amount with more than 2 decimals is refused (R-PREC). For **output** `S` lines, `vat_amount` must equal half-up(`taxable_amount` × 15 / 100) on magnitudes, or the line is refused (R-BRCO17): our own documents must satisfy BR-CO-17. For **input** lines a mismatch is a warning, not a refusal, because the supplier's tax invoice states the deductible VAT. That is a design choice for the accountant to confirm. | S5; S3 §4.2.4 |
| 2. Aggregation | This function | Exact integer sum of halalas. No rounding. "The rounded figures used must be the same figures used for the purposes of filing the VAT return." | S3 §4.2.4 (FETCHED) |
| 3. Presentation | Portal entry | **UNVERIFIED** whether the portal accepts halalas or whole riyals. The draft keeps halalas and performs **no** whole-riyal rounding. | none found |

The draft never re-rounds a sum, so tension between the S5 page 17 and §10 rules (CMP-037 §5) cannot arise inside this function.

## 8. Closed input contract (`cmp-010.input.v0`)

Every object has a fixed key set: an unknown or missing key is refused (R-SCHEMA). Amounts are JSON **strings** matching `^(0|[1-9][0-9]{0,11})(\.[0-9]{1,2})?$`; a JSON number is R-TYPE, a leading minus is R-NEG, more than 2 decimals is R-PREC, more than 12 integer digits is R-BOUND, and any other mismatch (exponent, plus sign, whitespace) is R-TYPE. Dates are `YYYY-MM-DD` Gregorian.

```text
ReturnInput {
  schema_version: "cmp-010.input.v0"
  taxpayer: { vat_number: string /^3\d{13}3$/ }          # BR-KSA-40 format, as in phase1.py
  period: { frequency: "monthly" | "quarterly", start: date, end: date }
  lines: TaxLine[1..1_000_000]
  prior_period_corrections: []                          # must be empty (R-CORR)
  credit_carried_forward: "0.00"                        # must be "0.00" (R-CFWD)
}
TaxLine {                       # one VAT breakdown (BG-23) entry of one document, not an item line
  line_id: string /^[A-Za-z0-9._:-]{1,64}$/, unique      # R-DUP
  source_doctype: "sales_invoice" | "purchase_invoice" | "customs_declaration" | "reverse_charge_record"
  source_document_id: string /^[A-Za-z0-9._:\/-]{1,140}$/
  direction: "output" | "input"
  treatment: one of the 7 CMP-006 treatment keys
  invoice_category: "S" | "Z" | "E" | "O" | null         # must equal the treatment's category
  reason_code: CMP-006 reason key | null                 # null for S and for input lines
  vat_rate_percent: "15" | "0" | null                    # must equal the treatment's rate
  document_kind: "invoice" | "credit_note" | "debit_note"
  tax_date: date                                         # date VAT became due, or the note's issue date
  original_tax_date: date | null                         # required for notes, else null
  original_return_filed: boolean | null                  # required for notes, else null
  adjustment_event_date: date | null                     # required for notes, else null
  taxable_amount: amount                                 # SAR, magnitude
  vat_amount: amount                                     # SAR, magnitude, as on the document
  deductible_share: "full" | "partial" | "none" | null   # input lines only; anything but "full" is R-PARTIAL
  currency: "SAR"                                        # conversion happens upstream at the SAMA rate (S4)
}
```

**Bounds.** At most SAR 999,999,999,999.99 per amount. At most 1,000,000 lines. Box sums are exact integers, so they cannot overflow in Python, and a sum above 10^15 halalas is refused (R-BOUND) as implausible. `source_doctype` must agree with `direction` and `treatment`: for example, `customs_declaration` only with `goods_import_standard_at_customs`. Otherwise R-TREAT.

**Output `ReturnDraft`.**
- `status`: always `"draft-unreviewed"`.
- `boxes`: `{key: {amount, adjustment, vat, line_ids, number_evidence}}`, or `null` if any refusal fired.
- The calculated totals `self_assessed_output`, `deductible_rcm_input`, `output_vat`, `input_vat`, `vat_due_current`, `vat_recomputed` and `filing_due_date`.
- `excluded_out_of_scope`, `not_computed: ["purch_zero", "purch_exempt", "corrections_prior", "credit_carried_forward", "net_vat_due"]`, `refusals[]` and `warnings[]`.
- Each refusal carries `{code, line_id | null, message_key}`. Messages go through i18n, and the rule's wording lives in the message catalogue, not the code.

## 9. What the draft may calculate, and what it refuses

**May calculate (draft, unreviewed):** Boxes 1, 3 (`-35`), 4 (`-32`, `-33`), 5 and 6; Boxes 7, 8 and 9 with full deduction; Box 12 marked incomplete; `vat_due_current`; `filing_due_date`; out-of-scope exclusions; the recomputation comparison.

**Refuses pending accountant sign-off:**

| Code | Trigger | Open question |
|---|---|---|
| R-ZMAP | `Z` reasons other than `-32`, `-33`, `-35` | Box 2 and 3 or 4 mapping, state-borne VAT (Q-267) |
| R-PARTIAL | `deductible_share` other than `full` (proportional deduction, restricted input VAT, Box 9 adjustment) | Q-267 |
| R-IMPRET | Import VAT accounted through the return (S1 §5.3) | Q-267 (import evidence and approval workflow) |
| R-CORR | Any prior-period correction | Art. 63 reading |
| R-CFWD | Non-zero carried-forward credit | Refund or carry-forward workflow |
| R-PNOTE | Cross-period purchase credit or debit note | Column for input notes |
| R-TREAT | Pairs not in §4: nominal or internal supplies, bad debt, capital assets, unknown treatment, doctype mismatch | Q-8, Q-267 |
| R-RATE | Period before 2020-07-01, or a rate other than the treatment's | none |
| R-BRCO17 | Output `S` VAT ≠ half-up(base × 15%) | none: an upstream defect |
| R-SCHEMA, R-TYPE, R-NEG, R-PREC, R-DUP, R-PERIOD, R-BOUND | Contract violations (§6, §8) | none |

## 10. Worked synthetic example (monthly, 2026-10-01 to 2026-10-31, VAT number `300000000000003`)

| line | treatment / reason | kind | notes | taxable | VAT | box, column |
|---|---|---|---|---|---|---|
| L1 | `domestic_sale_standard` | invoice | | 10,000.00 | 1,500.00 | 1, Amount |
| L2 | `domestic_sale_standard` | invoice | 333.33 × 15% = 49.9995 → 50.00 | 333.33 | 50.00 | 1, Amount |
| L3 | `sale_zero_rated` / `VATEX-SA-32` | invoice | | 5,000.00 | 0.00 | 4, Amount |
| L4 | `sale_exempt` / `VATEX-SA-30` | invoice | | 2,000.00 | 0.00 | 5, Amount |
| L5 | `domestic_sale_standard` | credit_note | issued 2026-10-20, original 2026-10-05, same period | 1,000.00 | 150.00 | 1, Amount (−) |
| L6 | `domestic_sale_standard` | credit_note | issued 2026-10-15, original 2026-08-10, return filed, event 2026-10-12 | 400.00 | 60.00 | 1, Adjustment (−) |
| L7 | `domestic_purchase_standard` | invoice | full | 6,000.00 | 900.00 | 7, Amount |
| L8 | `goods_import_standard_at_customs` | invoice | full | 2,000.00 | 300.00 | 8, Amount |
| L9 | `services_reverse_charge_standard` | invoice | full | 2,000.00 | 300.00 | 9, Amount |
| L10 | `sale_out_of_scope` / `VATEX-SA-OOS` | invoice | | 750.00 | 0.00 | excluded |

Expected results:
- Box 1: amount 9,333.33; adjustment −400.00; VAT 1,500.00 + 50.00 − 150.00 − 60.00 = **1,340.00**. Recomputed: 8,933.33 × 15% = 1,339.9995 → 1,340.00, a difference of 0.00.
- Box 4: 5,000.00 / 0 / 0.00. Box 5: 2,000.00 / 0 / 0.00. Box 6: 16,333.33 / −400.00 / 1,340.00.
- Box 7: 6,000.00 / 0 / 900.00. Box 8: 2,000.00 / 0 / 300.00. Box 9: 2,000.00 / 0 / 300.00. Box 12: 10,000.00 / 0 / 1,500.00 (incomplete).
- `self_assessed_output` = `deductible_rcm_input` = 300.00.
- `output_vat` = 1,340.00 + 300.00 = 1,640.00. `input_vat` = 900.00 + 300.00 + 300.00 = 1,500.00. **`vat_due_current` = 140.00**.
- `excluded_out_of_scope` = 750.00 (L10). `filing_due_date` = 2026-11-30.

## 11. Test vectors for the implementation row

Each vector reuses the §10 input with one change. The first group must produce `boxes = null` plus exactly the named refusal.

| # | Change | Expect |
|---|---|---|
| T1 | §10 unchanged | the §10 results, exactly |
| T2 | L1 `vat_amount` `"1500.005"` | R-PREC |
| T3 | L1 `taxable_amount` as JSON number `10000` | R-TYPE |
| T4 | L5 `taxable_amount` `"-1000.00"` | R-NEG |
| T5 | L9 `deductible_share` `"partial"` | R-PARTIAL |
| T6 | L3 reason `VATEX-SA-EDU` | R-ZMAP |
| T7 | L1 `tax_date` 2026-11-01 | R-PERIOD |
| T8 | `prior_period_corrections` has one entry | R-CORR |
| T9 | L1 VAT `"1500.01"` | R-BRCO17 |
| T10 | an extra key `"note"` on L1 | R-SCHEMA |
| T11 | L6 `original_return_filed` `null` | R-SCHEMA |
| T12 | L7 as a credit note (note fields complete) with `original_tax_date` 2026-09-03 | R-PNOTE |
| T13 | L1 `currency` `"USD"` | R-SCHEMA |
| T14 | duplicate `line_id` L2 | R-DUP |
| T15 | `period.start` 2020-06-01 | R-RATE |
| T16 | `credit_carried_forward` `"10.00"` | R-CFWD |
| T17 | L8 `source_doctype` `"purchase_invoice"` | R-TREAT |
| T18 | L1 `taxable_amount` `"1000000000000.00"` (13 integer digits) | R-BOUND |
| T19 | standalone input: output S 0.10 / 0.02 (0.015 → 0.02) and 0.03 / 0.00 (0.0045 → 0.00) | accepted, Box 1 VAT 0.02 |
| T20 | T19 plus a same-period credit note 0.10 / 0.02 | Box 1 amount 0.03, VAT 0.00 (the note mirrors the invoice) |
| T21 | L7 VAT `"900.01"` | accepted, with a warning |
| T22 | refusals T2 and T6 together | both listed, `boxes = null` |
| T23 | input order shuffled | identical output (order-independent sums, `line_ids` sorted) |
| T24 | quarterly 2026-08-01 to 2026-10-31 | accepted, with the quarter-alignment warning |

Property checks: `vat_due_current` equals Σ output signed VAT − Σ full-deductible input VAT over the accepted lines. Every accepted `line_id` appears in exactly one box or in `excluded_out_of_scope`. Doubling every amount doubles every sum exactly.

## 12. Accountant questions (open; nothing here closes them)

- **Q-267 (OPEN)**: customs import evidence; restricted and partial input VAT recovery; reverse-charge posting and settlement against the return; import VAT through the return; Box 2 state-borne citizen supplies; mapping of `VATEX-SA-34-*`, `-36` and `-MLTRY`.
- **Q-8 (OPEN)**: whether `2210` should be split into zero-rated and exempt output accounts. The design does not depend on the answer, because it splits by category and reason. Also the presentation of VAT settlement (`2230`) and refund receivables.
- **Q-601 (OPEN)**: whether S5 half-up binds the ledger; rounding of negative amounts. The return avoids both by design (§6, §7).
- **Q-615 to Q-622 (OPEN)**: box numbering and labels for Boxes 1–6 and 10–16 on the current portal (Q-615); the VAT column (portal-computed or taxpayer-entered, Q-616); the sign of the Adjustment column (Q-617); halala or riyal entry (Q-618); out-of-scope reporting (Q-619); how the Art. 63 SAR 5,000 test is applied (Q-620); quarter alignment (Q-621); the column for cross-period purchase notes (Q-622).

## 13. Not claimed

This design is not verified against the ZATCA portal and not reviewed by an accountant. It is not production-ready. It does not close CMP-010.
