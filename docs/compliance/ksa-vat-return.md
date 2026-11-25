# KSA VAT return report: design

Status: Design draft (revision 8) for Tier 3 line-by-line founder review and Saudi accountant review. No code in this file. Not tax advice.

Plan ID: CMP-010 (G2, rigid zone, Tier 3). Depends on CMP-006 ([KSA chart and VAT codes](ksa-coa-and-tax-codes.md)).

Method: the CMP-003 and ERP-015 method applies, as the partner confirmed for this task. An agent drafts deterministic code against this design. A founder reviews it line by line (Tier 3, [ADR-0031](../decisions/ADR-0031-rigid-zone-code-authorship.md), [ADR-0035](../decisions/ADR-0035-risk-tiered-review.md)), and a Saudi accountant reviews it before any production use. Until that review, the output is a **draft worksheet**, never a fileable return.

## 1. Scope and shape

- **What it is.** A pure function `build_vat_return_draft(input) -> ReturnDraft | RefusedResult` turns a closed list of deterministic tax rows into return boxes. It makes no engine calls, does no I/O, uses no model and reads no clock (the period comes in with the input).
- **What feeds it.** A separate extractor, outside this design and needing its own plan row, reads the engine's posted documents and produces the input. The engine stays the calculation authority for each document's VAT (ADR-0031). This function only **sums** amounts that are already rounded. It never recomputes the VAT it reports.
- **All or nothing.** If any refusal fires, the result is a `RefusedResult` (§8). It holds **no amounts of any kind**: no boxes, totals, diagnostics or exclusions. A partial return is worse than no return.
- **Scope.** Invoice accounting basis only (S4 Art. 45; S2 §9.1). Cash basis (Art. 46, amended in S6) is refused (R-BASIS).
- **Traceability (principle 8).** Every box value lists the `row_id`s it sums.
- **Location (partner's decision, 2026-11-25):** `components/compliance/zatca_sa/vat_return.py`, with tests in `components/compliance/zatca_sa/tests/test_vat_return.py`, inside the existing rigid `compliance.zatca_sa` component boundary.

## 2. Evidence labels and sources

All sources below were accessed **2026-11-25**. Labels:
- **FETCHED**: the official file or page was downloaded and its text, or for S7 p.15 its rendered image, was read this session.
- **UNVERIFIED**: no official text was read.

Vendor guides (Zoho, Tally, ClearTax, Odoo apps) are SECONDARY and are not cited. The ZATCA RCM circular (`.../MediaCenter/Publications/Documents/VAT%20Circular%20-%20RCM-EN.pdf`) returned an HTML page instead of the PDF to our fetcher, so it is **UNVERIFIED** and not relied on. S2 §4.3 states the same Box 9 rule. The English guidelines state that the Arabic version prevails.

| Id | Source (official, all FETCHED) | Used for |
|---|---|---|
| S1 | [Guideline on Imports and Exports, 2nd ed., May 2026](https://zatca.gov.sa/en/HelpCenter/guidelines/Documents/Guideline-on-Imports-and-Exports-under-VAT-Provision.pdf) §5.3, §6.3 ex. 7, §10.3–10.4 | Field 8 holds VAT paid to ZATCA at customs. Field 9 holds reverse charge, and import VAT accounted through the return once approved. Ex. 7: the Field 9 VAT Amount is VAT payable after deduction (Amount 100,000, Adjustment 30,000, VAT 1,500). |
| S2 | [Guideline on Input Tax Deduction, 3rd version, May 2026](https://zatca.gov.sa/en/HelpCenter/guidelines/Documents/Guideline-on-Input-Tax-Deduction-under-VAT-Provisions.pdf) §4.2–4.4, §9.1–9.2, §10 | Box 7, Box 8. Box 9 "without adjustment results in VAT payable being fully offset". Deduction timing and later-period deduction (Art. 49(8)). Input adjustments for notes. |
| S3 | [Guideline for Tax Invoicing and Records, version 3, May 2026](https://zatca.gov.sa/en/HelpCenter/guidelines/Documents/Guideline-for-Tax-Invoicing-and-Records-under-VAT-Provisions.pdf) §4.2.4, §7.1.1, §7.2, §7.2.1, §10.4 | Rounded invoice figures are the return figures. Amount or Adjustments field for notes. Notes are due within 15 days of the following month (Art. 54(6)). One note may cover several invoices. Correction routes. Its change log cites the Resolution (01-06-24) amendments (see S8). Its §4.2.4 ex. 6 is arithmetically inconsistent (1,091.30 "rounded" to 1,195.24), so it is not relied on. |
| S4 | [VAT Implementing Regulations, English, amended to 2021-11-09](https://www.zatca.gov.sa/en/RulesRegulations/Taxes/Documents/Implmenting%20Regulations%20of%20the%20VAT%20Law_EN.pdf), the articles on tax period (Art. 58), payment (Art. 59), tax returns, correction (Art. 63), value adjustment (Art. 40), credit and debit notes (Art. 54), currency conversion | **Out of date**: it predates S6 and the 2024 amendments (S8). It is used only where S6, S7 or the 2026 guidelines agree. Article numbers come from S2, S3 and S7 footnotes. |
| S5 | [E-Invoice XML Implementation Standard v1.2, 2023-05-19](https://zatca.gov.sa/ar/E-Invoicing/SystemsDevelopers/Documents/20230519_ZATCA_Electronic_Invoice_XML_Implementation_Standard_%20vF.pdf) §8.4, §8.5, §10, BR-CO-17, BR-S-09 | One VAT breakdown (BG-23) per VAT category and rate. Half-up rounding. BT-117 = BT-116 × rate / 100, rounded to 2 decimals at document level. |
| S6 | [Umm al-Qura Gazette: amendments to the VAT Implementing Regulations, 1444-12-05 (2023-06-23)](https://www.uqn.gov.sa/details?p=23146), Arabic | Art. 63(3) (2023 text) covers an error "resulting in a tax difference whose net value is less than fifteen thousand (15,000) riyals", replacing 5,000. Also amends Art. 40(7)(d) and Art. 46. |
| S8 | [Guideline for Amendments to the VAT Implementing Regulation, Resolution (01-06-24) of 2024-11-19, issue 1, April 2025](https://zatca.gov.sa/en/HelpCenter/guidelines/Documents/Amendments-to-the-Implementing-Regulation-of-(VAT).PDF) §2.9, the note-timeframe section, §2.12 | Art. 54 notes are due "within 15 days following the end of the month" of the triggering event. Art. 40(10) excepts financing contracts from the 12-month unpaid-input adjustment. Art. 63(1)–(4) were amended: the guideline describes them but does **not quote the new text** or any threshold. Ex. 25: a 10,000 understatement is corrected in the "Corrections" section of the return for the period of discovery. |
| S7 | [Guideline on Examination, Assessment, Correction and Objection, version 3, May 2026](https://zatca.gov.sa/en/HelpCenter/guidelines/Documents/Guideline-Examination-Assessment-Correction-Objection-on-VAT-Decision.pdf) §4.1, §4.2 (illustrative return form, p.15), §5.1–5.4 | Calendar month or **calendar quarter**. All 16 box labels. Box 14 limit ±15,000. Signed adjustments (ex. 6). Correction routes. |

## 3. Return boxes

Labels come from the **illustrative form in S7 p.15 (FETCHED, Arabic image)**, read by sight: S7 ex. 6 names "Box 1: Standard rated domestic sales" and "Box 4: Exports". Boxes 1–12 have Amount (SAR) and Adjustment (SAR) columns. Only Boxes 1, 6, 7, 8, 9 and 12 have a VAT Amount cell; Boxes 2–5 and 10–11 have none (re-checked on a zoomed render of p.15). Boxes 13–16 are single values. The form is illustrative: whether the live portal matches it stays open (Q-615), and so does whether its shaded VAT cells are computed by the portal (Q-616).

| Key | Box | Label (S7 p.15) | Draft may calculate |
|---|---|---|---|
| `sales_standard` | 1 | المبيعات الخاضعة للنسبة الأساسية | Yes |
| `sales_citizens` | 2 | المبيعات للمواطنين (الخدمات الصحية الخاصة/ التعليم الأهلي الخاص) | **No**: R-ZMAP |
| `sales_zero_domestic` | 3 | المبيعات المحلية الخاضعة للنسبة الصفرية | Yes, `VATEX-SA-35` only |
| `sales_export` | 4 | الصادرات | Yes, `VATEX-SA-32`, `-33` (S7 ex. 6 puts zero-rated services to a UK client in Box 4) |
| `sales_exempt` | 5 | المبيعات المعفاة | Yes, the three `E` codes |
| `sales_total` | 6 | إجمالي المبيعات | Yes, sum of 1–5; its VAT equals Box 1 VAT |
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
| output `sale_zero_rated` | `Z`, `-EDU`, `-HEA`, `-34-1`…`-34-5`, `-36`, `-MLTRY` | `sales_invoice` | refused R-ZMAP (Q-267); passes R-TREAT so that R-ZMAP is the code |
| output `sale_exempt` | `E`, `VATEX-SA-29`, `-29-7`, `-30` | `sales_invoice` | `sales_exempt`, VAT `0.00` |
| output `sale_out_of_scope` | `O`, `VATEX-SA-OOS` | `sales_invoice` | excluded, VAT `0.00` (Q-619) |
| input `domestic_purchase_standard` | `null` | `purchase_invoice` | `purch_standard` |
| input `goods_import_standard_at_customs` | `null` | `customs_declaration` | `purch_import_customs` |
| input `services_reverse_charge_standard` | `null` | `reverse_charge_record` | `purch_reverse_charge` |

**Zero VAT.** On `Z`, `E` and `O` rows, both `vat_amount` and `group_vat` must be `0.00`, or the row is refused (R-ZEROVAT). Boxes 2–5 carry no VAT, so nothing can leak into Box 13.

**Allowed `vat_source` (R-SOURCE otherwise).** Every output row, including notes and `O` rows, must be `zatca_xml_bg23` and carry `xml_uuid` (the document's `cbc:UUID`, BR-KSA-03) and `xml_sha256` (hex SHA-256 of the issued XML as stored). Input rows must use `supplier_document` for `domestic_purchase_standard`, `customs_declaration` for `goods_import_standard_at_customs`, and `ledger_only` for `services_reverse_charge_standard` (a self-assessed value with no ZATCA XML). On input rows both `xml_*` fields are `null`. **The extractor's binding duty**: take output row amounts only from the issued XML's BG-23 breakdown and never present ledger postings as XML. For every `S`, `Z` or `E` sale with no issued XML, it **must** emit one `ledger_only` row with the ledger figures and `null` `xml_*` fields, and that row is refused as R-SOURCE. Only `O` supplies without XML may be omitted. Until CMP-004 issues XML, every output row is therefore refused, and the draft computes nothing for sales. That is deliberate (Q-601).

**Sales without a tax invoice (option a, fail-closed).** S8 p.38 shows supplies outside the scope of VAT for which no tax invoice is required. That example concerns non-registered suppliers selling through a marketplace; we read it as showing that `O` and possibly `E` supplies can lack XML. `O` and `E` rows keep the XML requirement.
- An `S`, `Z` or `E` sale without XML arrives as the mandatory `ledger_only` row above and is R-SOURCE. Boxes 1–5 therefore cannot be quietly understated unless the extractor breaks its duty.
- An out-of-scope supply without XML is not an input row, so the extractor omits it. Because it affects no box, the output marks `excluded_out_of_scope.coverage: "xml_only"` to flag that the total may be incomplete. In this version `coverage` is that constant on every draft.

**Mixed zero-rated documents (S5 §8.4).** One BG-23 breakdown covers every line with the same category and rate. A single invoice can therefore put medicines (Box 3) and exports (Box 4) into one `Z` subtotal. The input carries one row per (document, category, rate, reason, original document), and each row repeats its BG-23 subtotal. The rows of a subtotal must add up to it exactly (R-RECON). An extractor that cannot attribute every item of a subtotal to exactly one reason must not emit the document. How a mixed `Z` invoice states its reasons in XML is an open question (§12).

## 5. Calculation

All arithmetic runs on integer halalas after strict parsing, with no floats. The return does no rounding of its own: it sums amounts already rounded on the issued documents (§7). Let *s* be the sign (§6) and *col* the column (§6).

- For each leaf box *k* (1–5, 7–9): `amount[k]` = Σ *s* × `taxable_amount` over rows with *col* = Amount, and `adjustment[k]` = the same over rows with *col* = Adjustment.
- `vat[k]` for Boxes 1, 7 and 8 = Σ *s* × `vat_amount` over all rows of *k*. Boxes 2–5 have no VAT value (`null`), since R-ZEROVAT guarantees their rows carry none.
- `vat[purch_reverse_charge]` = **0.00** (**UNVERIFIED** presentation, Q-616). S2 §4.3 says only that a Box 9 entry without adjustment "results in VAT payable being fully offset". S1 ex. 7 shows 1,500 in the VAT column for a 30,000 non-deductible adjustment. That the column reads 0.00 under full deduction is our inference from these, not stated text. The gross self-assessed VAT goes to `reconciliation.rcm_self_assessed_vat` = Σ *s* × `vat_amount` of Box 9 rows. It is shown, never added to a box.
- Box 6 and Box 12 are column sums of their leaf boxes (Box 6 VAT = Box 1 VAT).
- `vat_due_current` (Box 13) = `vat[6]` − `vat[12]`. A negative value is a refundable position (S7 p.15 callout 4). Refund versus carry-forward stays with Boxes 15–16, which are refused.
- `filing_due_date` = the last day of the month after `period.end` (S4 Art. 59(1); S7 §4.2 schedule).
- `diagnostics.vat_recomputed[k]` for Boxes 1 and 7 = half-up(|`amount` + `adjustment`| × rate / 100), with the sign restored, and its difference from `vat[k]`. This is **diagnostic only** and is never a box value (Q-616).

## 6. Signs, notes, periods, timing and corrections

**Signs.** Amounts in the input are non-negative magnitudes. The sign comes only from `document_kind`: `invoice` +1, `debit_note` +1, `credit_note` −1. A negative string is refused (R-NEG). S7 ex. 6 confirms that adjustments are signed: "a negative adjustment of SAR 120,000 to Box 1 … a positive adjustment … to Box 4". How the portal enters them stays Q-617.

**Output notes (S3 §7.1.1, the source of the column table below).** For a note, `supply_date` is its issue date. The row carries exactly one `original_document_id`, and a note covering several invoices (S3 §7.2.1) arrives as several rows reconciled to the note's subtotal (R-RECON). Filing status is fixed **at issue**, from evidence about the original period's return. Every note must carry `original_return` = `{period_start, period_end, filed_on, not_filed_as_of}` with exactly one of the last two set. There is no `null` fallback: a missing object, or neither or both of the dates set, is R-SCHEMA. The rest is R-NOTECTX:
- The period must be a valid calendar month or quarter (rules below) that contains `original_supply_date`.
- `filed_on` must be after `period_end`.
- `not_filed_as_of` must be on or after the note's `supply_date`, so the evidence covers the issue date.
- If `original_supply_date` is in the draft period, the period must equal the draft period and `filed_on` must be `null`.
- The extractor resolves the evidence **once per original period**: `filed_on` is the actual filing date if the return was filed by extraction time, else `not_filed_as_of` is the extraction date. All note rows naming the same (`period_start`, `period_end`) must carry identical `filed_on` and `not_filed_as_of`. Periods named by different rows, and the draft period itself, must be pairwise identical or non-overlapping. Rows sharing (`direction`, `original_document_id`) must carry an identical `original_supply_date`; a sales and a purchase document may share an ID string. Any conflict makes every row involved R-NOTECTX.

| Condition (S3 §7.1.1) | Column and period |
|---|---|
| `original_supply_date` in this period, or `not_filed_as_of` set, or `filed_on` after `supply_date` | Amount, in the period of `supply_date` |
| `filed_on` before `supply_date`, credit note | Adjustment, in the period of the later of `supply_date` and `adjustment_event_date` |
| `filed_on` before `supply_date`, debit note | Amount, in the period of `adjustment_event_date` |
| `filed_on` equal to `supply_date`, any evidence failure above, or `original_supply_date` after `supply_date` | refused, R-NOTECTX |

The selected date must fall inside the period, or the row is refused (R-PERIOD). The function never moves a row. Art. 54 requires a note "within 15 days following the end of the month" of the triggering event (S8 and S3 §7.2, FETCHED guidance; the Arabic regulation text was not read). A later note produces a warning, not a refusal, because it is a document-compliance issue, not a return amount.

**Input notes.** Same-period purchase notes are netted in the Amount column (S2 §10; Art. 40(6)). The last paragraph of S3 §7.1.1 sets the period for a cross-period purchase note: the customer corrects input tax "in the tax period in which the credit or debit note was issued". It does not set the column, so such notes are refused (R-PNOTE, Q-622).

**Input timing (S2 §9.1–9.2, Art. 49(8)).** An input invoice row has `supply_date` (when the tax became due) and a required `claim_date` (the return it is claimed in), with `supply_date` ≤ `claim_date` (else R-PERIOD). `claim_date` must fall inside the draft period, or the row is refused (R-PERIOD), so an October draft can never take a November claim. Input notes use `supply_date` only, and their `claim_date` is `null`. If `supply_date` is before `period.start` (a late claim, which Art. 49(8) allows up to five calendar years after the calendar year of supply), the row is refused (R-LATECLAIM). Neither the column nor the five-year boundary is set out in official text (§12). This refusal is explicit, not a silent R-PERIOD.

**Periods (S7 §4.1, FETCHED).** "In the KSA, the tax period is either a calendar month or a calendar quarter." Monthly is mandatory above SAR 40 million of annual taxable supplies (S4 Art. 58(1): "during the previous twelve months"). `period.frequency` is an input (ZATCA assigns it), and the function never derives it.
- `monthly`: one calendar month.
- `quarterly`: exactly Jan–Mar, Apr–Jun, Jul–Sep or Oct–Dec. Anything else is R-PERIOD. There is no verified exception route (for example, the first period after registration), so exceptions are refused.
- Supported range: `period.start` ≥ 2020-07-01 (earlier is R-RATE, because the 5% rate and transition rules are out of scope) and `period.end` ≤ 2099-12-31 (later is R-DATE).

**Corrections: routes UNVERIFIED pending the amended Art. 63 text.** S8 says Resolution (01-06-24) amended Art. 63(1)–(4), the paragraphs that hold the threshold, after the 2023 gazette (S6) set SAR 15,000. S8 does not quote the new text, so every route below, including the 15,000 figure, is **UNVERIFIED** until the Arabic text is read. The guidance as published (FETCHED):
- An understatement of SAR 15,000 or more must be notified within 20 days of becoming aware of it, by correcting the original period's return on the portal (S7 §5.2.1, §5.4).
- An understatement under 15,000 may go in Box 14 of "the next Tax Return" (S6 Art. 63(3)) or "the tax return … for the tax period during which the error was discovered" (S3 §10.4).
- An overstatement under 15,000 may go in Box 14. Above that, it goes in the Adjustment column of the matching boxes in a later return (S7 §5.1.1, ex. 6), within five years of the end of the calendar year.
- The official texts disagree on the exact boundary ("less than", "15,000 or more", "exceeding") and on which return to use. S7 ex. 9 says a 6,000 understatement must be notified, contradicting §5.3. The draft refuses every correction (R-CORR). The refusal message says only that corrections need the accountant (Q-620). It quotes no route or threshold.

**Special cases are never silent.** Each row must state `special_case`. Any value other than `none` (bad-debt relief, capital-asset adjustment, nominal supply, internal supply, proportional deduction, state-borne citizen supply, other) is refused (R-SPECIAL). For customs rows, `vat_settlement` must be `paid_at_customs` with a non-empty `customs_payment_reference`. `through_return` is refused (R-IMPRET, S1 §5.3), and a missing reference is R-SCHEMA.

## 7. Rounding stages

| Stage | Where | Rule | Evidence |
|---|---|---|---|
| 0. Document VAT | Upstream: engine, CMP-003, CMP-004 | Half-up, BT-117 rounded to 2 decimals per category at document level, on final results only | S5 §10, BR-CO-17 (FETCHED). Q-601 answered 2026-11-25: ZATCA mandates half-up, so the Saudi rounding rule is statutory; rounding of negative amounts stays open. |
| 0a. Platform setting | Engine | Commercial Rounding, ties away from zero, including negatives | ADR-0033 (a founder decision). It matches S5 for positive values. Python `ROUND_HALF_UP` also rounds ties away from zero (checked: `-0.015` → `-0.02`). |
| 1. Input check | This function | No rounding. More than 2 decimals is R-PREC. If an output `S` subtotal's `group_vat` ≠ half-up(`group_taxable` × rate / 100), or an input row mismatches, the result is warning **W-BRCO17** listing the `row_id`s and `xml_uuid`, and the draft is still built from the issued figures. No box value is recomputed or substituted (CMP-003: no second calculator); the §5 diagnostic is not a box value. | S5 BR-CO-17; founder decision "A, warn only" (PR #319 comment, Eldon for both founders, 2026-11-25) |
| 2. Aggregation | This function | Exact integer sum, no rounding | S3 §4.2.4: "the rounded figures used must be the same figures used for … filing the VAT return" |
| 3. Presentation | Portal | Halalas or whole riyals: UNVERIFIED. No whole-riyal rounding is done. | Q-618 |

The 15% rate is read from the SA country pack version passed in `rate_source`. That version is echoed in the output. `rate_source.standard_rate_percent` other than `"15"` is R-RATE (stage 2). A row's rate is part of the closed §4 combination, so a wrong row rate is R-TREAT. There is no row-level R-RATE: the old path was dead because R-TREAT always ran first.

## 8. Closed input contract (`cmp-010.input.v1`)

Every object has a fixed key set: an unknown or missing key is R-SCHEMA. So is a non-`null` value where a field's rule below says "else null", "null on invoices", "notes only", "customs rows only" or "input rows". These conditions are keyed on stage-1 enums only: notes are rows whose `document_kind` is `credit_note` or `debit_note`; customs rows are rows whose `source_doctype` is `customs_declaration`; input rows are rows whose `source_doctype` is `purchase_invoice`, `customs_declaration` or `reverse_charge_record`. Every JSON string anywhere in the input, keys and values, including inside `prior_period_corrections`, must be printable ASCII (U+0020 to U+007E), else R-SCHEMA. No input field needs Arabic text, so this costs nothing, and it means no string that reaches a later stage or the digest can fail to encode. Amounts are JSON strings: a JSON number is R-TYPE, a leading minus is R-NEG, more than 2 decimals is R-PREC, more than 12 integer digits is R-BOUND, and any other mismatch is R-TYPE. Dates are Gregorian `YYYY-MM-DD`. Every pattern below is applied with `re.fullmatch` and uses ASCII `[0-9]`, never `\d` (which matches non-ASCII digits) or `^…$` anchoring (`$` accepts a trailing newline).

```text
ReturnInput {
  schema_version: "cmp-010.input.v1"
  taxpayer_vat_number: 3[0-9]{13}3                         # BR-KSA-40 format, as in phase1.py
  accounting_basis: "invoice"                             # else R-BASIS
  period: { frequency: "monthly" | "quarterly", start: date, end: date }
  rate_source: { pack_id: "sa", pack_version: [0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}, standard_rate_percent: "15" }
  empty_period_confirmed: boolean                         # true if and only if rows is empty, else R-SCHEMA
  rows: TaxRow[0..1_000_000]                            # more rows: R-BOUND (stage 1)
  prior_period_corrections: []                            # non-empty: R-CORR
  credit_carried_forward: "0.00"                          # anything else: R-CFWD
}
TaxRow {
  row_id: [A-Za-z0-9._:-]{1,64}                          # unique, else R-DUP
  taxpayer_vat_number: string                             # must equal the top level, else R-TAXPAYER
  source_doctype: "sales_invoice" | "purchase_invoice" | "customs_declaration" | "reverse_charge_record"
  source_document_id: [A-Za-z0-9._:/-]{1,140}
  original_document_id: same pattern | null               # required for notes, else null
  direction, treatment, invoice_category, reason_code, vat_rate_percent   # §4
  special_case: "none" | "bad_debt" | "capital_asset" | "nominal_supply" | "internal_supply"
              | "proportional_deduction" | "state_borne" | "other"     # not "none": R-SPECIAL
  vat_settlement: "paid_at_customs" | "through_return" | null          # customs rows only
  customs_payment_reference: [A-Za-z0-9._:/-]{1,64} | null           # customs rows only; required if paid_at_customs
  document_kind: "invoice" | "credit_note" | "debit_note"
  supply_date: date            # tax due date, or the note's issue date
  claim_date: date | null      # required on input invoice rows, inside the period; else null
  original_supply_date: date | null            # notes only
  original_return: { period_start: date, period_end: date, filed_on: date | null,
                     not_filed_as_of: date | null } | null   # required on notes (exactly one date set); null on invoices
  adjustment_event_date: date | null           # notes only
  taxable_amount: amount, vat_amount: amount   # magnitudes, SAR
  group_taxable: amount, group_vat: amount     # the document's BG-23 subtotal for (category, rate)
  vat_source: "zatca_xml_bg23" | "ledger_only" | "supplier_document" | "customs_declaration"   # §4 matrix
  xml_uuid: [0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12} | null   # lower case only
  xml_sha256: [0-9a-f]{64} | null                                               # both required on output rows
  deductible_share: "full" | "partial" | "none" | null   # input rows only; not "full": R-PARTIAL
  currency: "SAR"                                        # conversion happens upstream at the SAMA rate
}
```

**Allocation key and replay.** The key is (`source_doctype`, `source_document_id`, `invoice_category`, `vat_rate_percent`, `reason_code`, `original_document_id`). A repeated key is R-DUP, even with a new `row_id`, so a replayed SAR 1,500 subtotal cannot double. The binding is one-to-one in both directions. Every output source document (`source_doctype`, `source_document_id`) carries exactly one `xml_uuid` and one `xml_sha256` on all its rows, and each `xml_uuid` and each `xml_sha256` belongs to exactly one source document. Any other pairing is R-DUP. The stage-3 binding check skips `null` UUIDs and hashes; an output row with a `null` is refused as R-SOURCE in stage 4. A UUID that is not lower-case 8-4-4-4-12 hex is R-SCHEMA, so a case-changed copy cannot pass as a new UUID. This function sees one period only. Preventing a replay across periods, and preventing one supplier invoice entered under two `source_document_id`s (which would double Box 7), is the **extractor's duty**. This means SI-1's XML replayed under another document ID cannot add SAR 1,500, and one document cannot carry two XMLs whose subtotals would add up separately. Rows sharing a reconciliation group must carry identical `group_*` values and sum to them exactly (R-RECON). For output rows the group is (`source_document_id`, `xml_uuid`, `invoice_category`, `vat_rate_percent`). The binding makes this one subtotal per document, category and rate, so a document's rows can never sum past its own subtotals; for input rows it is (`source_doctype`, `source_document_id`, `invoice_category`, `vat_rate_percent`). A row from another VAT registration is R-TAXPAYER. All rows of one source document (`source_doctype`, `source_document_id`) must share one `document_kind`, checked before the sums, or R-RECON. This stops an invoice row of 600/90 and a credit row of 400/60 from reconciling to a 1,000/150 subtotal while posting 30.

**Refusal precedence.** Checks run in stages. The first stage that finds a refusal stops evaluation and reports every refusal from that stage. Within stage 4 and stage 5, checks on one row run in the listed order, and only the row's first failure is reported. R-TAXPAYER sits in stage 2, so a foreign-registration row that passed stage 1 is always reported, even alongside header refusals. `primary_code` is defined by the refusal ordering below. Each single-change vector in §11 yields one distinct code.
1. Shape: R-SCHEMA (unknown or missing key, malformed date, a value outside its enum such as `document_kind`, `frequency` or `currency`, any pattern mismatch including `xml_uuid`, a string that is not printable ASCII, a non-`null` value in a field that must be `null` for that row), R-TYPE, R-NEG, R-PREC, R-BOUND (single amounts or row count).
2. Header and registration: R-TAXPAYER (every row), R-BASIS, R-DATE, R-RATE (period start or `rate_source`), R-PERIOD (period shape), R-CORR, R-CFWD.
3. Identity: R-DUP (allocation key and XML binding).
4. Classification, per row: R-TREAT (including the row rate), R-SOURCE, R-ZMAP, R-SPECIAL, R-IMPRET, R-PARTIAL, R-ZEROVAT.
5. Dates, per row: R-NOTECTX, R-PNOTE, R-PERIOD (`supply_date` after `claim_date`), R-LATECLAIM, R-PERIOD (dates outside the period).
6. Documents: R-RECON. (BR-CO-17 is a warning, never a refusal.)
7. Totals: R-BOUND (sums).

**Bounds.** At most SAR 999,999,999,999.99 per amount and 1,000,000 rows. Every column sum and derived total, **positive or negative**, must satisfy |x| ≤ 10^15 halalas, else R-BOUND.

**`ReturnDraft`** (only when there are no refusals):
- `status: "draft-unreviewed"` and `rate_source` (echoed).
- `boxes: {key: {amount, adjustment, vat | null, row_ids}}` for 1–9 and 12 (`vat` is `null` for 2–5), and a single value for 13.
- `not_computed: [10, 11, 14, 15, 16]`, `purch_total_incomplete: true`, `filing_due_date`.
- `reconciliation: {rcm_self_assessed_vat, excluded_out_of_scope: {taxable, row_ids, coverage: "xml_only"}}`.
- `input_sha256`: hex SHA-256 of the canonical input. It is computed only after stage 1 passes, so every string in the input has already been checked as printable ASCII (§8) and encoding cannot fail. It is `null` whenever `prior_period_corrections` is non-empty, because its entries are opaque and refused (R-CORR). Canonical form: the input with `rows` sorted by `row_id`, ties (duplicate `row_id`s) broken by each row's own canonical bytes; every object's keys sorted by Unicode code point; separators `,` and `:` with no whitespace; JSON literals for `true`, `false` and `null`; amounts and dates kept as their input strings; UTF-8 without BOM and with non-ASCII characters unescaped. In Python: `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")`. Golden value: T28.
- `diagnostics` and `warnings[]`. Each warning is `{code, source_doctype, source_document_id, row_ids, xml_uuid | null}`, so input-side warnings carry their document. W-BRCO17 is emitted once per reconciliation group (document subtotal), not once per row. W-NOTELATE is emitted once per note document and lists every row of that note. A warning never changes a box value.
- **Ordering** (deterministic): every `row_ids` list is sorted ascending by code point. `warnings[]` is sorted by (`code`, `source_doctype`, `source_document_id`, first `row_id`). `refusals[]` is sorted by (stage, the check's position in its stage list, `row_id` with `null` first, `message_key`). The check's position matters because R-PERIOD appears twice in stage 5. `primary_code` is the code of the first refusal in this order.
- `draft_complete: false` with `incomplete_boxes: [10, 11, 14, 15, 16]`. It stays false while any box is not computed, which is always the case in this version.

**`RefusedResult`**: `{status: "refused", schema_version, primary_code, input_sha256 | null, refusals: [{code, row_id | null, message_key}], warnings: []}`, with no other keys and no amounts. `warnings` is always empty on a refusal. `input_sha256` is `null` when stage 1 fails or corrections are present. Messages go through i18n.

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
| R-ZEROVAT | `Z`, `E` or `O` row with VAT ≠ 0.00 | Q-619 |
| R-SOURCE | `vat_source` or XML provenance not allowed for the row (§4) | Q-601 |
| R-RECON, R-DUP, R-TAXPAYER, R-NOTECTX | Allocation, replay, taxpayer or note-context failures | — |
| R-SCHEMA, R-TYPE, R-NEG, R-PREC, R-BOUND, R-PERIOD, R-RATE, R-DATE, R-TREAT | Contract violations | — |

## 10. Worked synthetic example (monthly, 2026-10-01 to 2026-10-31)

Fixture **F**. All rows share these values: `taxpayer_vat_number` `300000000000003` (also top level); `currency` `SAR`; `special_case` `none`; `claim_date` equal to `supply_date` on L7–L9 and `null` elsewhere; on output rows, `xml_uuid` and `xml_sha256` are distinct synthetic values; `vat_settlement`, `customs_payment_reference`, `original_*` and `adjustment_event_date` `null` unless stated; `deductible_share` `null` on output rows; and `group_*` equal to the row's own amounts. Top level: `accounting_basis` `invoice`; `rate_source` `{sa, 0.1.0, "15"}`; `empty_period_confirmed` `false`; corrections `[]`; carried-forward credit `"0.00"`.

| row | doctype / doc id | treatment, cat, reason, rate | kind, `supply_date`, note fields | taxable | VAT | `vat_source`, share | box, col |
|---|---|---|---|---|---|---|---|
| L1 | sales_invoice SI-1 | std sale, S, null, 15 | invoice 10-02 | 10,000.00 | 1,500.00 | xml | 1 A |
| L2 | sales_invoice SI-2 | std sale, S, null, 15 | invoice 10-03 | 333.33 | 50.00 | xml | 1 A |
| L3 | sales_invoice SI-3 | zero, Z, -32, 0 | invoice 10-04 | 5,000.00 | 0.00 | xml | 4 A |
| L4 | sales_invoice SI-4 | exempt, E, -30, 0 | invoice 10-04 | 2,000.00 | 0.00 | xml | 5 A |
| L5 | sales_invoice CN-1 | std sale, S, null, 15 | credit 10-20; orig SI-1 10-02; return {10-01, 10-31, not filed as of 10-20}; event 10-18 | 1,000.00 | 150.00 | xml | 1 A (−) |
| L6 | sales_invoice CN-2 | std sale, S, null, 15 | credit 10-15; orig SI-0 08-10; return {08-01, 08-31, filed 09-25}; event 10-12 | 400.00 | 60.00 | xml | 1 Adj (−) |
| L7 | purchase_invoice PI-1 | std purchase, null, null, 15 | invoice 10-06 | 6,000.00 | 900.00 | supplier, full | 7 A |
| L8 | customs_declaration CD-1 | import, null, null, 15; `paid_at_customs`, ref `PAY-1` | invoice 10-07 | 2,000.00 | 300.00 | customs, full | 8 A |
| L9 | reverse_charge_record RC-1 | RCM, null, null, 15 | invoice 10-08 | 2,000.00 | 300.00 | ledger, full | 9 A |
| L10 | sales_invoice SI-5 | OOS, O, -OOS, null | invoice 10-09 | 750.00 | 0.00 | xml | excluded |

Expected:
- Box 1: 9,333.33 / −400.00 / **1,340.00** (1,500 + 50 − 150 − 60). The diagnostic gives 8,933.33 × 15% = 1,339.9995 → 1,340.00, a difference of 0.00.
- Box 4: 5,000.00 / 0.00 / VAT `null`. Box 5: 2,000.00 / 0.00 / VAT `null`. Box 6: 16,333.33 / −400.00 / 1,340.00.
- Box 7: 6,000.00 / 0.00 / 900.00. Box 8: 2,000.00 / 0.00 / 300.00. Box 9: 2,000.00 / 0.00 / **0.00**. Box 12: 10,000.00 / 0.00 / 1,200.00 (incomplete).
- **Box 13 = 1,340.00 − 1,200.00 = 140.00.** `rcm_self_assessed_vat` = 300.00. `excluded_out_of_scope` = 750.00 (L10). Due date 2026-11-30.

## 11. Test vectors

Each refusal vector except T41 changes **one** thing in F and expects a `RefusedResult` with exactly one distinct code (precedence in §8) and no amount keys. T1 and the accepted vectors return a `ReturnDraft`.

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
| T9 | L1 VAT and group VAT `"1500.01"` | accepted, W-BRCO17 on L1; Box 1 VAT 1,340.01; Box 13 140.01 |
| T10 | L1 extra key | R-SCHEMA |
| T11 | L6 `filed_on` = 10-15 (its issue date) | R-NOTECTX |
| T12 | L7 as a credit note: `original_document_id` PI-0, `original_supply_date` 09-03, `original_return` {09-01, 09-30, filed 10-02}, event 10-05, `claim_date` null | R-PNOTE |
| T13 | L8 `vat_settlement` `through_return` | R-IMPRET |
| T14 | L2 copied with a new `row_id` (replay) | R-DUP |
| T15 | period 2020-06-01 to 2020-06-30, every date in F shifted back 76 months | R-RATE |
| T16 | `credit_carried_forward` `"10.00"` | R-CFWD |
| T17 | L8 `source_doctype` `purchase_invoice` | R-TREAT |
| T18 | L1 taxable and group `"1000000000000.00"` | R-BOUND |
| T19 | L7 `taxpayer_vat_number` `300000000000013` | R-TAXPAYER |
| T20 | L7 `supply_date` 09-20 (`claim_date` stays 10-06) | R-LATECLAIM |
| T21 | L7 VAT and group VAT `"900.01"` | accepted, one W-BRCO17 on PI-1, Box 13 = **139.99** |
| T22 | L3 split into two rows of SI-3 (`-32` 3,000.00 and `-35` 2,000.00, group 5,000.00) | accepted: Box 3 2,000.00 and Box 4 3,000.00, both VAT `null` |
| T23 | T22 with the `-35` row at 1,900.00 (rows sum 4,900.00, SAR 100.00 short of the 5,000.00 group) | R-RECON |
| T24 | quarterly 2026-08-01 to 2026-10-31 (all dates still inside) | R-PERIOD (not a calendar quarter) |
| T25 | quarterly 2026-07-01 to 2026-09-30, every date in F shifted back 3 months, except that L5 `original_return` is {07-01, 09-30, not filed as of 07-20} and L6 `original_return` is {04-01, 06-30, filed 07-10} | accepted, §10 boxes, due date 2026-10-31 |
| T26 | L10 VAT `"1.00"` | R-ZEROVAT |
| T27 | `special_case` `bad_debt` on L7 | R-SPECIAL |
| T28 | `rows` `[]`, `empty_period_confirmed` `true` | accepted: Boxes 1–9 and 12 at 0.00 (VAT `null` for 2–5), Box 13 0.00; `not_computed` is still [10, 11, 14, 15, 16]; `input_sha256` `2b407d5fb6fff29627e4eaafd546e2d970748baf3b9620ef51bfd8e64d58d690` |
| T29 | `rows` `[]`, `empty_period_confirmed` `false` | R-SCHEMA |
| T30 | `accounting_basis` `cash` | R-BASIS |
| T31 | T28 with period 2100-01-01 to 2100-01-31 | R-DATE |
| T32 | standalone month: invoices SI-A S 0.10/0.02 (0.015 → 0.02) and SI-B 0.03/0.00 (0.0045 → 0.00); then also CN-A credit 0.10/0.02 issued 10-05, original SI-A 10-02, return {10-01, 10-31, not filed as of 10-05} | Box 1 0.13 / 0.02 VAT; then 0.03 / 0.00 VAT (checked) |
| T33 | SI-1 as two rows: invoice 600.00/90.00 and credit 400.00/60.00 (credit issued 10-02, orig SI-1 10-02, `original_return` {10-01, 10-31, not filed as of 10-20}, event 10-02), both with group 1,000.00/150.00 | R-RECON (mixed `document_kind`) |
| T34 | L7 `claim_date` 11-03 | R-PERIOD |
| T35 | L1 `vat_source` `supplier_document` | R-SOURCE |
| T36 | L6 `original_return` {08-01, 08-31, filed 08-25} | R-NOTECTX (filed before the period ended) |
| T37 | L3 VAT and group VAT `"1.00"` | R-ZEROVAT |
| T38 | L1 copied with a new `row_id` and `source_document_id` SI-1B, same `xml_uuid` and `xml_sha256` | R-DUP |
| T39 | add CN-3: credit 10-16 on SI-0, 100.00/15.00, its own XML, `original_return` {08-01, 08-31, not filed as of 10-16} (conflicts with L6) | R-NOTECTX |
| T40 | L6 `original_return` `null` | R-SCHEMA (no fallback to Amount) |
| T42 | L2 as a VAT-inclusive sale: total 100.01 issued as taxable 86.97 and VAT 13.04 (group the same; 86.97 × 15% = 13.0455 → 13.05) | accepted, W-BRCO17 on L2; issued figures kept: Box 1 9,086.97 / −400.00 / 1,303.04; Box 13 103.04 |
| T43 | L3 plus a second SI-3 row: `-35`, 5,000.00/0.00, group 5,000.00/0.00, but a different `xml_uuid` and `xml_sha256` | R-DUP (one document, two XMLs; without the check Box 6 would gain 5,000.00) |
| T44 | add CN-4: credit 10-16 on SI-9 (orig 08-20), 100.00/15.00, its own XML, `original_return` {08-01, 08-31, not filed as of 10-16} (same period as L6, different evidence) | R-NOTECTX |
| T45 | L1 copied as SI-1B with a new `row_id`, `xml_uuid` upper-cased and a different `xml_sha256` | R-SCHEMA |
| T46 | L1 `supply_date` `"2026-10-32"` | R-SCHEMA |
| T47 | L1 `document_kind` `"Invoice"` | R-SCHEMA |
| T48 | `period.frequency` `"annual"` | R-SCHEMA |
| T49 | L7 `currency` `"USD"` | R-SCHEMA |
| T50 | L7 `claim_date` 10-05 (`supply_date` 10-06) | R-PERIOD |
| T51 | L6 `adjustment_event_date` 08-20 (note due by 09-15, issued 10-15) | accepted, one W-NOTELATE on CN-2, §10 boxes |
| T52 | L5 `original_return` {10-01, 10-31, filed 11-02} (original inside the draft period) | R-NOTECTX |
| T53 | add SI-10…SI-20: eleven S invoices, each 999,999,999,999.99 / 150,000,000,000.00, valid XML | R-BOUND (Box 1 amount exceeds 10^15 halalas; stage 7) |
| T41 | T16 and T19 together | refusals R-TAXPAYER and R-CFWD; `primary_code` R-TAXPAYER |

Properties:
- **Box 13**: equals Σ *s* × `vat_amount` over output rows minus Σ *s* × `vat_amount` over Box 7 and 8 rows. Reverse-charge rows are excluded because they net to zero. F gives 1,340.00 − 1,200.00 = 140.00.
- **Additivity**: for disjoint valid row sets A and B whose union is valid, every leaf-box column of A∪B equals A plus B.
- **Coverage**: every accepted `row_id` appears in exactly one leaf box (1–5, 7–9; never in totals 6, 12 or 13) or in `excluded_out_of_scope`.
- **Order independence**: shuffling the rows gives identical output.
- **No leakage**: every refusal vector's result has exactly the `RefusedResult` keys and `warnings: []`.
- **Digest**: `input_sha256` is unchanged when rows or object keys are reordered, and changes when any value changes.

## 12. Accountant questions (open; nothing here closes them)

- **Q-267 (OPEN)**: customs evidence; restricted and partial recovery; reverse-charge settlement; import VAT through the return; Box 2 state-borne supplies; `VATEX-SA-34-*`, `-36`, `-MLTRY` mapping.
- **Q-8 (OPEN)**: splitting `2210` (the design splits by category and does not depend on it); settlement (`2230`) and refund receivable presentation.
- **Q-601 (ANSWERED in part, 2026-11-25)**: ZATCA mandates half-up (S5 §10), so the Saudi rounding rule is statutory. Still open for the accountant: rounding of negative amounts (`half_away_from_zero` versus half-up). The return itself still does no rounding, and W-BRCO17 stays a warning (founder decision, §7).
- **Q-615–Q-622 (OPEN)**: live-portal labels (Q-615); the VAT column (Q-616); Adjustment entry (Q-617); halala or riyal (Q-618); out-of-scope reporting (Q-619); Art. 63 correction routes at SAR 15,000 (Q-620); quarter exceptions (Q-621); cross-period purchase notes and late claims (Q-622).
- **Q-623–Q-626 (OPEN)**: how a mixed `Z` invoice (Box 3 and Box 4 items) states reasons in one BG-23 (S5 §8.4) (Q-623); the Art. 54 note deadline after Resolution (01-06-24) (S8 guidance read; Arabic text not read) (Q-624); which consolidated Arabic Implementing Regulations text governs, given that S4 predates S6 (Q-625); the Art. 49(8) five-year boundary (Q-626).
- **Q-628 (OPEN)**: whether out-of-scope and exempt sales issued without a ZATCA tax invoice must be reported, and from what evidence (§4: exempt rows without XML are refused; out-of-scope rows without XML are omitted and flagged `xml_only`).

## 13. Not claimed

This design is not verified against the ZATCA portal and not reviewed by an accountant. It is not production-ready. It does not close CMP-010.
