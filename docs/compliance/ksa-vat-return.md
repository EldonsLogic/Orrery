# KSA VAT return report: design

Status: Design draft (revision 1) for Tier 3 line-by-line founder review and Saudi accountant review. No code in this file. Not tax advice.

Plan ID: CMP-010 (G2, rigid zone, Tier 3). Depends on CMP-006 ([KSA chart and VAT codes](ksa-coa-and-tax-codes.md)).

Method: the CMP-003 and ERP-015 method applies, as the partner confirmed for this task. An agent drafts deterministic code against this design. A founder reviews it line by line (Tier 3, [ADR-0031](../decisions/ADR-0031-rigid-zone-code-authorship.md), [ADR-0035](../decisions/ADR-0035-risk-tiered-review.md)), and a Saudi accountant reviews it before any production use. Until that review, the output is a **draft worksheet**, never a fileable return.

## 1. Scope and shape

- **What it is.** A pure function `build_vat_return_draft(input) -> ReturnDraft | RefusedResult` turns a closed list of deterministic tax rows into return boxes. It makes no engine calls, does no I/O, uses no model and reads no clock (the period comes in with the input).
- **What feeds it.** A separate extractor, outside this design and needing its own plan row, reads the engine's posted documents and produces the input. The engine stays the calculation authority for each document's VAT (ADR-0031). This function only **sums** amounts that are already rounded. It never recomputes the VAT it reports.
- **All or nothing.** If any refusal fires, the result is a `RefusedResult` (§8). It holds **no amounts of any kind**: no boxes, totals, diagnostics or exclusions. A partial return is worse than no return.
- **Scope.** Invoice accounting basis only (S4 Art. 45; S2 §9.1). Cash basis (Art. 46, amended in S6) is refused (R-BASIS).
- **Traceability (principle 8).** Every box value lists the `row_id`s it sums.
- **Proposed location** (for the implementation row to confirm): `components/compliance/zatca_sa/vat_return.py`, with tests in `components/compliance/zatca_sa/tests/test_vat_return.py`.

## 2. Evidence labels and sources

All sources below were accessed **2026-11-25**. Labels:
- **FETCHED**: the official file or page was downloaded and its text, or for S7 p.15 its rendered image, was read this session.
- **UNVERIFIED**: no official text was read.

Vendor guides (Zoho, Tally, ClearTax, Odoo apps) are SECONDARY and are not cited. The ZATCA RCM circular (`.../MediaCenter/Publications/Documents/VAT%20Circular%20-%20RCM-EN.pdf`) returned an HTML page instead of the PDF to our fetcher, so it is **UNVERIFIED** and not relied on. S2 §4.3 states the same Box 9 rule. The English guidelines state that the Arabic version prevails.

| Id | Source (official, all FETCHED) | Used for |
|---|---|---|
| S1 | [Guideline on Imports and Exports, 2nd ed., May 2026](https://zatca.gov.sa/en/HelpCenter/guidelines/Documents/Guideline-on-Imports-and-Exports-under-VAT-Provision.pdf) §5.3, §6.3 ex. 7, §10.3–10.4 | Field 8 holds VAT paid to ZATCA at customs. Field 9 holds reverse charge, and import VAT accounted through the return once approved. Ex. 7: the Field 9 VAT Amount is VAT payable after deduction (Amount 100,000, Adjustment 30,000, VAT 1,500). |
| S2 | [Guideline on Input Tax Deduction, 3rd version, May 2026](https://zatca.gov.sa/en/HelpCenter/guidelines/Documents/Guideline-on-Input-Tax-Deduction-under-VAT-Provisions.pdf) §4.2–4.4, §9.1–9.2, §10 | Box 7, Box 8. Box 9 "without adjustment results in VAT payable being fully offset". Deduction timing and later-period deduction (Art. 49(8)). Input adjustments for notes. |
| S3 | [Guideline for Tax Invoicing and Records, version 3, May 2026](https://zatca.gov.sa/en/HelpCenter/guidelines/Documents/Guideline-for-Tax-Invoicing-and-Records-under-VAT-Provisions.pdf) §4.2.4, §7.1.1, §7.2, §7.2.1, §10.4 | Rounded invoice figures are the return figures. Amount or Adjustments field for notes. Notes are due within 15 days of the following month (Art. 54(6)). One note may cover several invoices. Correction routes. Its change log cites Implementing Regulations amendments by Resolution (01-06-24) of 2024-11-19, which were not read (UNVERIFIED). Its §4.2.4 ex. 6 is arithmetically inconsistent (1,091.30 "rounded" to 1,195.24), so it is not relied on. |
| S4 | [VAT Implementing Regulations, English, amended to 2021-11-09](https://www.zatca.gov.sa/en/RulesRegulations/Taxes/Documents/Implmenting%20Regulations%20of%20the%20VAT%20Law_EN.pdf), the articles on tax period (Art. 58), payment (Art. 59), tax returns, correction (Art. 63), value adjustment (Art. 40), credit and debit notes (Art. 54), currency conversion | **Out of date**: it predates S6 and the 2024 amendments. It is used only where S6, S7 or the 2026 guidelines agree. Article numbers come from S2, S3 and S7 footnotes. |
| S5 | [E-Invoice XML Implementation Standard v1.2, 2023-05-19](https://zatca.gov.sa/ar/E-Invoicing/SystemsDevelopers/Documents/20230519_ZATCA_Electronic_Invoice_XML_Implementation_Standard_%20vF.pdf) §8.4, §8.5, §10, BR-CO-17, BR-S-09 | One VAT breakdown (BG-23) per VAT category and rate. Half-up rounding. BT-117 = BT-116 × rate / 100, rounded to 2 decimals at document level. |
| S6 | [Umm al-Qura Gazette: amendments to the VAT Implementing Regulations, 1444-12-05 (2023-06-23)](https://www.uqn.gov.sa/details?p=23146), Arabic | Art. 63(3) now covers an error "resulting in a tax difference whose net value is less than fifteen thousand (15,000) riyals", replacing 5,000. Also amends Art. 40(7)(d) and Art. 46. |
| S7 | [Guideline on Examination, Assessment, Correction and Objection, version 3, May 2026](https://zatca.gov.sa/en/HelpCenter/guidelines/Documents/Guideline-Examination-Assessment-Correction-Objection-on-VAT-Decision.pdf) §4.1, §4.2 (illustrative return form, p.15), §5.1–5.4 | Calendar month or **calendar quarter**. All 16 box labels. Box 14 limit ±15,000. Signed adjustments (ex. 6). Correction routes. |

## 3. Return boxes

Labels come from the **illustrative form in S7 p.15 (FETCHED, Arabic image)**, read by sight: S7 ex. 6 names "Box 1: Standard rated domestic sales" and "Box 4: Exports". Boxes 1–12 have Amount (SAR) and Adjustment (SAR) columns. Boxes 1–9 and 12 also have a VAT Amount column; Boxes 10–11 have none. Boxes 13–16 are single values. The form is illustrative: whether the live portal matches it stays open (Q-615), and so does whether its shaded VAT cells are computed by the portal (Q-616).

| Key | Box | Label (S7 p.15) | Draft may calculate |
|---|---|---|---|
| `sales_standard` | 1 | المبيعات الخاضعة للنسبة الأساسية | Yes |
| `sales_citizens` | 2 | المبيعات للمواطنين (الخدمات الصحية الخاصة/ التعليم الأهلي الخاص) | **No**: R-ZMAP |
| `sales_zero_domestic` | 3 | المبيعات المحلية الخاضعة للنسبة الصفرية | Yes, `VATEX-SA-35` only |
| `sales_export` | 4 | الصادرات | Yes, `VATEX-SA-32`, `-33` (S7 ex. 6 puts zero-rated services to a UK client in Box 4) |
| `sales_exempt` | 5 | المبيعات المعفاة | Yes, the three `E` codes |
| `sales_total` | 6 | إجمالي المبيعات | Yes, sum of 1–5 |
| `purch_standard` | 7 | المشتريات الخاضعة للنسبة الأساسية | Yes, full deduction, same-period supply |
| `purch_import_customs` | 8 | الاستيرادات … التي تدفع في الجمارك | Yes, full deduction, VAT paid at customs with evidence |
| `purch_reverse_charge` | 9 | الاستيرادات … التي تطبق عليها آلية الاحتساب العكسي | Yes, full deduction only. VAT column 0.00 (§5). |
| `purch_zero` | 10 | المشتريات الخاضعة للنسبة الصفرية | **Not computed**: no CMP-006 treatment |
| `purch_exempt` | 11 | المشتريات المعفاة | **Not computed**: no CMP-006 treatment |
| `purch_total` | 12 | إجمالي المشتريات | Yes, sum of 7–9, marked incomplete |
| `vat_due_current` | 13 | إجمالي ضريبة القيمة المضافة المستحقة عن الفترة الضريبية الحالية | Yes (§5) |
| `corrections_prior` | 14 | تصحيحات من الفترات السابقة بين (15,000) ± ريال | **No**: R-CORR |
| `credit_carried_forward` | 15 | ضريبة القيمة المضافة التي تم ترحيلها من الفترة/الفترات السابقة | **No**: R-CFWD |
| `net_vat_due` | 16 | صافي الضريبة المستحقة | **No**: needs 14 and 15 |

## 4. Exact mapping: CMP-006 treatment to box

`treatment` must be one of the seven keys in `apps/engine/compliance/ksa/vat_treatments.json`. The mapping is closed. Any other combination of `direction`, `treatment`, `invoice_category`, `reason_code`, `vat_rate_percent` or `source_doctype` is refused (R-TREAT).

**Canonical rate representation** (the XML form, not the CMP-006 `vat_rate_percent` field): `S` = `"15"`, `Z` = `"0"`, `E` = `"0"` (S5 uses 0 for exempt, as CMP-006 notes), `O` = `null`, input rows = `"15"`. The function checks it against this table and never copies CMP-006 `null` for exempt rows.

| `direction` / `treatment` | Category, reason | `source_doctype` | Box key |
|---|---|---|---|
| output `domestic_sale_standard` | `S`, `null` | `sales_invoice` | `sales_standard` |
| output `sale_zero_rated` | `Z`, `VATEX-SA-35` | `sales_invoice` | `sales_zero_domestic`, VAT `0.00` |
| output `sale_zero_rated` | `Z`, `VATEX-SA-32` or `-33` | `sales_invoice` | `sales_export`, VAT `0.00` |
| output `sale_zero_rated` | `Z`, `-EDU`, `-HEA`, `-34-1`…`-34-5`, `-36`, `-MLTRY` | – | refused R-ZMAP (Q-267) |
| output `sale_exempt` | `E`, `VATEX-SA-29`, `-29-7`, `-30` | `sales_invoice` | `sales_exempt`, VAT `0.00` |
| output `sale_out_of_scope` | `O`, `VATEX-SA-OOS` | `sales_invoice` | excluded, VAT must be `0.00` (R-OOSVAT) (Q-619) |
| input `domestic_purchase_standard` | `null` | `purchase_invoice` | `purch_standard` |
| input `goods_import_standard_at_customs` | `null` | `customs_declaration` | `purch_import_customs` |
| input `services_reverse_charge_standard` | `null` | `reverse_charge_record` | `purch_reverse_charge` |

**Mixed zero-rated documents (S5 §8.4).** One BG-23 breakdown covers every line with the same category and rate. A single invoice can therefore put medicines (Box 3) and exports (Box 4) into one `Z` subtotal. The input carries one row per (document, category, rate, reason, original document), and each row repeats its BG-23 subtotal. The rows of a subtotal must add up to it exactly (R-RECON). An extractor that cannot attribute every item of a subtotal to exactly one reason must not emit the document. How a mixed `Z` invoice states its reasons in XML is an open question (§12).

## 5. Calculation

All arithmetic runs on integer halalas after strict parsing, with no floats and no rounding (§7). Let *s* be the sign (§6) and *col* the column (§6).

- For each leaf box *k* (1–5, 7–9): `amount[k]` = Σ *s* × `taxable_amount` over rows with *col* = Amount, and `adjustment[k]` = the same over rows with *col* = Adjustment.
- `vat[k]` for Boxes 1–5, 7 and 8 = Σ *s* × `vat_amount` over all rows of *k*.
- `vat[purch_reverse_charge]` = **0.00**. With full deduction the self-assessed output and the deduction cancel (S2 §4.3; S1 ex. 7 shows this column as net VAT payable). The gross self-assessed VAT goes to `reconciliation.rcm_self_assessed_vat` = Σ *s* × `vat_amount` of Box 9 rows. It is shown, never added to a box.
- Box 6 and Box 12 are column sums of their leaf boxes.
- `vat_due_current` (Box 13) = `vat[6]` − `vat[12]`. A negative value is a refundable position (S7 p.15 callout 4). Refund versus carry-forward stays with Boxes 15–16, which are refused.
- `filing_due_date` = the last day of the month after `period.end` (S4 Art. 59(1); S7 §4.2 schedule).
- `diagnostics.vat_recomputed[k]` for Boxes 1 and 7 = half-up(|`amount` + `adjustment`| × rate / 100), with the sign restored, and its difference from `vat[k]`. This is **diagnostic only** and is never a box value (Q-616).

## 6. Signs, notes, periods, timing and corrections

**Signs.** Amounts in the input are non-negative magnitudes. The sign comes only from `document_kind`: `invoice` +1, `debit_note` +1, `credit_note` −1. A negative string is refused (R-NEG). S7 ex. 6 confirms that adjustments are signed: "a negative adjustment of SAR 120,000 to Box 1 … a positive adjustment … to Box 4". How the portal enters them stays Q-617.

**Output notes (S3 §7.1.1; S4 Art. 40(4)–(5)).** For a note, `supply_date` is its issue date. The row carries exactly one `original_document_id`, and a note covering several invoices (S3 §7.2.1) arrives as several rows reconciled to the note's subtotal (R-RECON). Filing status is fixed **at issue**, from the actual filing date of the original period's return: `original_return_filed_on` (a date, or `null` if not filed when the extract was taken). The status is never taken from extraction time.

| Condition | Column and period |
|---|---|
| `original_supply_date` in this period, or `original_return_filed_on` is `null` or after `supply_date` | Amount, in the period of `supply_date` |
| `original_return_filed_on` before `supply_date`, credit note | Adjustment, in the period of the later of `supply_date` and `adjustment_event_date` |
| `original_return_filed_on` before `supply_date`, debit note | Amount, in the period of `adjustment_event_date` |
| `original_return_filed_on` equal to `supply_date`, or not after the last day of `original_supply_date`'s month (no return is filed before its period ends), or `original_supply_date` after `supply_date` | refused, R-NOTECTX |

The selected date must fall inside the period, or the row is refused (R-PERIOD). The function never moves a row. S3 §7.2 requires a note within 15 days of the month after the triggering event (Art. 54(6); the 2024 amendment text was not read). A later note produces a warning, not a refusal, because it is a document-compliance issue, not a return amount.

**Input notes.** Same-period purchase notes are netted in the Amount column (S2 §10; Art. 40(6)). Cross-period purchase notes are refused (R-PNOTE, Q-622).

**Input timing (S2 §9.1–9.2, Art. 49(8)).** An input row has `supply_date` (when the tax became due) and `claim_date` (the return it is claimed in). Same-period claims are accepted. If `supply_date` is before `period.start` (a late claim, which Art. 49(8) allows up to five calendar years after the calendar year of supply), the row is refused (R-LATECLAIM). Neither the column nor the five-year boundary is set out in official text (§12). This refusal is explicit, not a silent R-PERIOD.

**Periods (S7 §4.1, FETCHED).** "In the KSA, the tax period is either a calendar month or a calendar quarter." Monthly is mandatory above SAR 40 million of annual taxable supplies (S4 Art. 58(1): "during the previous twelve months"). `period.frequency` is an input (ZATCA assigns it), and the function never derives it.
- `monthly`: one calendar month.
- `quarterly`: exactly Jan–Mar, Apr–Jun, Jul–Sep or Oct–Dec. Anything else is R-PERIOD. There is no verified exception route (for example, the first period after registration), so exceptions are refused.
- Supported range: `period.start` ≥ 2020-07-01 (earlier is R-RATE, because the 5% rate and transition rules are out of scope) and `period.end` ≤ 2099-12-31 (later is R-DATE).

**Corrections (S6; S7 §§5.1–5.4; S3 §10.4; all FETCHED).**
- An understatement of SAR 15,000 or more must be notified within 20 days of becoming aware of it, by correcting the original period's return on the portal (S7 §5.2.1, §5.4).
- An understatement under 15,000 may go in Box 14 of "the next Tax Return" (S6 Art. 63(3)) or "the tax return … for the tax period during which the error was discovered" (S3 §10.4).
- An overstatement under 15,000 may go in Box 14. Above that, it goes in the Adjustment column of the matching boxes in a later return (S7 §5.1.1, ex. 6), within five years of the end of the calendar year.
- The official texts disagree on the exact boundary ("less than", "15,000 or more", "exceeding") and on which return to use. S7 ex. 9 says a 6,000 understatement must be notified, contradicting §5.3. The draft therefore refuses every correction (R-CORR), and the refusal message carries the period in which the error was discovered and these routes (Q-620).

**Special cases are never silent.** Each row must state `special_case`. Any value other than `none` (bad-debt relief, capital-asset adjustment, nominal supply, internal supply, proportional deduction, state-borne citizen supply, other) is refused (R-SPECIAL). For customs rows, `vat_settlement` must be `paid_at_customs` with a non-empty `customs_payment_reference`. `through_return` is refused (R-IMPRET, S1 §5.3), and a missing reference is R-SCHEMA.

## 7. Rounding stages

| Stage | Where | Rule | Evidence |
|---|---|---|---|
| 0. Document VAT | Upstream: engine, CMP-003, CMP-004 | Half-up, BT-117 rounded to 2 decimals per category at document level, on final results only | S5 §10, BR-CO-17 (FETCHED). Whether it binds the ledger: Q-601. |
| 0a. Platform setting | Engine | Commercial Rounding, ties away from zero, including negatives | ADR-0033 (a founder decision). It matches S5 for positive values. Python `ROUND_HALF_UP` also rounds ties away from zero (checked: `-0.015` → `-0.02`). |
| 1. Input check | This function | No rounding. More than 2 decimals is R-PREC. Only for output `S` subtotals with `vat_source = "zatca_xml_bg23"`: `group_vat` must equal half-up(`group_taxable` × rate / 100), or R-BRCO17. `ledger_only` and input rows: a mismatch is a warning, left to the accountant (Q-601). | S5 BR-CO-17 |
| 2. Aggregation | This function | Exact integer sum, no rounding | S3 §4.2.4: "the rounded figures used must be the same figures used for … filing the VAT return" |
| 3. Presentation | Portal | Halalas or whole riyals: UNVERIFIED. No whole-riyal rounding is done. | Q-618 |

The 15% rate is read from the SA country pack version passed in `rate_source`. That version is echoed in the output, and a row whose rate differs from it is refused (R-RATE).

## 8. Closed input contract (`cmp-010.input.v1`)

Every object has a fixed key set: an unknown or missing key is R-SCHEMA. Amounts are JSON strings: a JSON number is R-TYPE, a leading minus is R-NEG, more than 2 decimals is R-PREC, more than 12 integer digits is R-BOUND, and any other mismatch is R-TYPE. Dates are Gregorian `YYYY-MM-DD`.

```text
ReturnInput {
  schema_version: "cmp-010.input.v1"
  taxpayer_vat_number: /^3\d{13}3$/                       # BR-KSA-40 format, as in phase1.py
  accounting_basis: "invoice"                             # else R-BASIS
  period: { frequency: "monthly" | "quarterly", start: date, end: date }
  rate_source: { pack_id: "sa", pack_version: string, standard_rate_percent: "15" }
  empty_period_confirmed: boolean                         # true if and only if rows is empty, else R-SCHEMA
  rows: TaxRow[0..1_000_000]
  prior_period_corrections: []                            # non-empty: R-CORR
  credit_carried_forward: "0.00"                          # anything else: R-CFWD
}
TaxRow {
  row_id: /^[A-Za-z0-9._:-]{1,64}$/                       # unique, else R-DUP
  taxpayer_vat_number: string                             # must equal the top level, else R-TAXPAYER
  source_doctype: "sales_invoice" | "purchase_invoice" | "customs_declaration" | "reverse_charge_record"
  source_document_id: /^[A-Za-z0-9._:\/-]{1,140}$/
  original_document_id: same pattern | null               # required for notes, else null
  direction, treatment, invoice_category, reason_code, vat_rate_percent   # §4
  special_case: "none" | "bad_debt" | "capital_asset" | "nominal_supply" | "internal_supply"
              | "proportional_deduction" | "state_borne" | "other"     # not "none": R-SPECIAL
  vat_settlement: "paid_at_customs" | "through_return" | null          # customs rows only
  customs_payment_reference: string{1,64} | null                       # required if paid_at_customs
  document_kind: "invoice" | "credit_note" | "debit_note"
  supply_date: date            # tax due date, or the note's issue date
  claim_date: date | null      # input invoice rows: the claimed return's date, else null
  original_supply_date: date | null            # notes only
  original_return_filed_on: date | null        # notes only: the actual filing date of the original's return
  adjustment_event_date: date | null           # notes only
  taxable_amount: amount, vat_amount: amount   # magnitudes, SAR
  group_taxable: amount, group_vat: amount     # the document's BG-23 subtotal for (category, rate)
  vat_source: "zatca_xml_bg23" | "ledger_only" | "supplier_document" | "customs_declaration"
  deductible_share: "full" | "partial" | "none" | null   # input rows; not "full": R-PARTIAL
  currency: "SAR"                                        # conversion happens upstream at the SAMA rate
}
```

**Allocation key and replay.** The key is (`source_doctype`, `source_document_id`, `invoice_category`, `vat_rate_percent`, `reason_code`, `original_document_id`). A repeated key is R-DUP, even with a new `row_id`, so a replayed SAR 1,500 subtotal cannot double. Rows sharing (`source_doctype`, `source_document_id`, `invoice_category`, `vat_rate_percent`) must carry identical `group_*` values and sum to them exactly (R-RECON). A row from another VAT registration is R-TAXPAYER.

**Bounds.** At most SAR 999,999,999,999.99 per amount and 1,000,000 rows. Every column sum and derived total, **positive or negative**, must satisfy |x| ≤ 10^15 halalas, else R-BOUND.

**`ReturnDraft`** (only when there are no refusals):
- `status: "draft-unreviewed"` and `rate_source` (echoed).
- `boxes: {key: {amount, adjustment, vat | null, row_ids}}` for 1–9 and 12, and single values for 13.
- `not_computed: [10, 11, 14, 15, 16]`, `purch_total_incomplete: true`, `filing_due_date`.
- `reconciliation: {rcm_self_assessed_vat, excluded_out_of_scope: {taxable, row_ids}}`.
- `diagnostics`, `warnings[]`.

**`RefusedResult`**: `{status: "refused", schema_version, refusals: [{code, row_id | null, message_key}], warnings: [{code, row_id | null}]}`, with no other keys and no amounts. Messages go through i18n.

## 9. What the draft may calculate, and what it refuses

**May calculate (draft, unreviewed):** Boxes 1, 3 (`-35`), 4 (`-32`, `-33`), 5 and 6; Boxes 7–9 with full deduction and same-period supply; Box 12 (marked incomplete); Box 13; the due date; reconciliation and diagnostics.

**Refuses:**

| Code | Trigger | Open with |
|---|---|---|
| R-ZMAP | `Z` reasons other than `-32`, `-33`, `-35` (includes Box 2) | Q-267 |
| R-PARTIAL, R-SPECIAL | Partial or no deduction; any special case | Q-267, Q-8 |
| R-IMPRET | Customs VAT settled through the return | Q-267 |
| R-LATECLAIM, R-PNOTE | Late input claim; cross-period purchase note | Q-622 |
| R-CORR, R-CFWD | Any correction; non-zero carried-forward credit | Q-620 |
| R-BASIS | Cash accounting basis | — |
| R-OOSVAT | Out-of-scope row with VAT ≠ 0.00 | Q-619 |
| R-BRCO17 | XML-sourced `S` subtotal fails BR-CO-17 | upstream defect |
| R-RECON, R-DUP, R-TAXPAYER, R-NOTECTX | Allocation, replay, taxpayer or note-context failures | — |
| R-SCHEMA, R-TYPE, R-NEG, R-PREC, R-BOUND, R-PERIOD, R-RATE, R-DATE, R-TREAT | Contract violations | — |

## 10. Worked synthetic example (monthly, 2026-10-01 to 2026-10-31)

Fixture **F**. All rows share these values: `taxpayer_vat_number` `300000000000003` (also top level); `currency` `SAR`; `special_case` `none`; `claim_date` `null` (the same-period default); `vat_settlement`, `customs_payment_reference`, `original_*` and `adjustment_event_date` `null` unless stated; and `group_*` equal to the row's own amounts. Top level: `accounting_basis` `invoice`; `rate_source` `{sa, 0.1.0, "15"}`; `empty_period_confirmed` `false`; corrections `[]`; carried-forward credit `"0.00"`.

| row | doctype / doc id | treatment, cat, reason, rate | kind, `supply_date`, note fields | taxable | VAT | `vat_source`, share | box, col |
|---|---|---|---|---|---|---|---|
| L1 | sales_invoice SI-1 | std sale, S, null, 15 | invoice 10-02 | 10,000.00 | 1,500.00 | xml | 1 A |
| L2 | sales_invoice SI-2 | std sale, S, null, 15 | invoice 10-03 | 333.33 | 50.00 | xml | 1 A |
| L3 | sales_invoice SI-3 | zero, Z, -32, 0 | invoice 10-04 | 5,000.00 | 0.00 | xml | 4 A |
| L4 | sales_invoice SI-4 | exempt, E, -30, 0 | invoice 10-04 | 2,000.00 | 0.00 | xml | 5 A |
| L5 | sales_invoice CN-1 | std sale, S, null, 15 | credit 10-20; orig SI-1 10-02; filed null; event 10-18 | 1,000.00 | 150.00 | xml | 1 A (−) |
| L6 | sales_invoice CN-2 | std sale, S, null, 15 | credit 10-15; orig SI-0 08-10; filed 09-25; event 10-12 | 400.00 | 60.00 | xml | 1 Adj (−) |
| L7 | purchase_invoice PI-1 | std purchase, null, null, 15 | invoice 10-06 | 6,000.00 | 900.00 | supplier, full | 7 A |
| L8 | customs_declaration CD-1 | import, null, null, 15; `paid_at_customs`, ref `PAY-1` | invoice 10-07 | 2,000.00 | 300.00 | customs, full | 8 A |
| L9 | reverse_charge_record RC-1 | RCM, null, null, 15 | invoice 10-08 | 2,000.00 | 300.00 | ledger, full | 9 A |
| L10 | sales_invoice SI-5 | OOS, O, -OOS, null | invoice 10-09 | 750.00 | 0.00 | xml | excluded |

Expected:
- Box 1: 9,333.33 / −400.00 / **1,340.00** (1,500 + 50 − 150 − 60). The diagnostic gives 8,933.33 × 15% = 1,339.9995 → 1,340.00, a difference of 0.00.
- Box 4: 5,000.00 / 0.00 / 0.00. Box 5: 2,000.00 / 0.00 / 0.00. Box 6: 16,333.33 / −400.00 / 1,340.00.
- Box 7: 6,000.00 / 0.00 / 900.00. Box 8: 2,000.00 / 0.00 / 300.00. Box 9: 2,000.00 / 0.00 / **0.00**. Box 12: 10,000.00 / 0.00 / 1,200.00 (incomplete).
- **Box 13 = 1,340.00 − 1,200.00 = 140.00.** `rcm_self_assessed_vat` = 300.00. `excluded_out_of_scope` = 750.00 (L10). Due date 2026-11-30.

## 11. Test vectors

Each refusal vector changes **one** thing in F and expects a `RefusedResult` with exactly that one code and no amount keys. T1 and the accepted vectors return a `ReturnDraft`.

| # | Change to F | Expect |
|---|---|---|
| T1 | none | §10 exactly |
| T2 | L1 `vat_amount` and `group_vat` `"1500.005"` | R-PREC |
| T3 | L1 `taxable_amount` as JSON number | R-TYPE |
| T4 | L5 `taxable_amount` `"-1000.00"` | R-NEG |
| T5 | L9 `deductible_share` `partial` | R-PARTIAL |
| T6 | L3 reason `-EDU` | R-ZMAP |
| T7 | L1 `supply_date` 2026-11-01 | R-PERIOD |
| T8 | one correction entry | R-CORR |
| T9 | L1 VAT and group VAT `"1500.01"` | R-BRCO17 |
| T10 | L1 extra key | R-SCHEMA |
| T11 | L6 `original_return_filed_on` = 10-15 (its issue date) | R-NOTECTX |
| T12 | L7 as a credit note: `original_document_id` PI-0, `original_supply_date` 09-03, filed 10-02, event 10-05 | R-PNOTE |
| T13 | L8 `vat_settlement` `through_return` | R-IMPRET |
| T14 | L2 copied with a new `row_id` (replay) | R-DUP |
| T15 | period 2020-06-01 to 2020-06-30, every date in F shifted back 76 months | R-RATE |
| T16 | `credit_carried_forward` `"10.00"` | R-CFWD |
| T17 | L8 `source_doctype` `purchase_invoice` | R-TREAT |
| T18 | L1 taxable and group `"1000000000000.00"` | R-BOUND |
| T19 | L7 `taxpayer_vat_number` `300000000000013` | R-TAXPAYER |
| T20 | L7 `supply_date` 09-20, `claim_date` 10-06 | R-LATECLAIM |
| T21 | L7 VAT and group VAT `"900.01"` | accepted, a warning, Box 13 = **139.99** |
| T22 | L3 split into two rows of SI-3 (`-32` 3,000.00 and `-35` 2,000.00, group 5,000.00) | accepted: Box 3 2,000.00, Box 4 3,000.00 |
| T23 | T22 with the `-35` row at 1,900.00 | R-RECON |
| T24 | quarterly 2026-08-01 to 2026-10-31 (all dates still inside) | R-PERIOD (not a calendar quarter) |
| T25 | quarterly 2026-07-01 to 2026-09-30, every date in F shifted back 3 months except L6 filed 07-10 | accepted, §10 boxes, due date 2026-10-31 |
| T26 | L10 VAT `"1.00"` | R-OOSVAT |
| T27 | `special_case` `bad_debt` on L7 | R-SPECIAL |
| T28 | `rows` `[]`, `empty_period_confirmed` `true` | accepted, all boxes 0.00, Box 13 0.00 |
| T29 | `rows` `[]`, `empty_period_confirmed` `false` | R-SCHEMA |
| T30 | `accounting_basis` `cash` | R-BASIS |
| T31 | T28 with period 2100-01-01 to 2100-01-31 | R-DATE |
| T32 | standalone: S 0.10/0.02 and 0.03/0.00, then plus a same-period credit 0.10/0.02 | Box 1 VAT 0.02, then 0.00 |

Properties:
- **Additivity**: for disjoint valid row sets A and B whose union is valid, every leaf-box column of A∪B equals A plus B.
- **Coverage**: every accepted `row_id` appears in exactly one leaf box (1–5, 7–9) or in `excluded_out_of_scope`.
- **Order independence**: shuffling the rows gives identical output.
- **No leakage**: every refusal vector's result has exactly the `RefusedResult` keys.

## 12. Accountant questions (open; nothing here closes them)

- **Q-267 (OPEN)**: customs evidence; restricted and partial recovery; reverse-charge settlement; import VAT through the return; Box 2 state-borne supplies; `VATEX-SA-34-*`, `-36`, `-MLTRY` mapping.
- **Q-8 (OPEN)**: splitting `2210` (the design splits by category and does not depend on it); settlement (`2230`) and refund receivable presentation.
- **Q-601 (OPEN)**: whether S5 half-up binds the ledger; negative rounding; BR-CO-17 on ledger-only rows (§7).
- **Q-615–Q-622 (OPEN)**: live-portal labels (Q-615); the VAT column (Q-616); Adjustment entry (Q-617); halala or riyal (Q-618); out-of-scope reporting (Q-619); Art. 63 correction routes at SAR 15,000 (Q-620); quarter exceptions (Q-621); cross-period purchase notes and late claims (Q-622).
- **Q-623–Q-626 (OPEN)**: how a mixed `Z` invoice (Box 3 and Box 4 items) states reasons in one BG-23 (S5 §8.4) (Q-623); the Art. 54(6) note deadline as amended by Resolution (01-06-24) (text not read) (Q-624); which consolidated Arabic Implementing Regulations text governs, given that S4 predates S6 (Q-625); the Art. 49(8) five-year boundary (Q-626).

## 13. Not claimed

This design is not verified against the ZATCA portal and not reviewed by an accountant. It is not production-ready. It does not close CMP-010.
