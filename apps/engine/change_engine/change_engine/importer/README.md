# Opening balances and master data importer

Status: implemented for offline verification; Tier 3 review pending.
Owner: partner. Plan: ERP-013.

`OpeningImporter(backend)` exposes `validate(batch)`, `preview(batch)` and
`apply(batch, confirmed_by=..., plan_hash=...)`. It has no public endpoint or
implicit backend. The supplied `SQLiteImportBackend` is a transactional reference
store for synthetic runs, including file-backed restart tests. Its records are
**import records, not native ledger postings**. This PR does not establish live
posting, financial conformance, or permission behavior on a deployed engine.

## Input and stages

A batch contains `tenant_id`, `company`, `batch_id`, ISO `posting_date`, one
supported ISO-4217 `currency` (`SAR`, `AED`, `EGP`, `QAR`, `USD`, `EUR`, `GBP`), `datasets`, and a mandatory `prevalidation` report.
The server derives the precision from `currency`. If provided, `currency_precision`
must be an integer equal to the derived precision or the batch returns `IMP-SCHEMA`.
`datasets` maps an entity below to row dicts or a DSC-019
`{"rows": [...], "sheet": ...}` wrapper. No unknown batch,
entity, row or mapping field is accepted.

1. **Validate:** authenticate the backend human session and tenant/company scope
   before processing data; no writes. Check schema, sizes, exact numbers, dates,
   the explicit currency allowlist, stable keys, Unicode formula/control content,
   the complete upstream report, server-side DSC-019 checks and reconciliation.
   A failure returns `ok: false` with an `IMP-*` bilingual catalog error, without
   copying raw cells. Validation stops at the first error (maximum one error);
   `errors_truncated: true` means additional errors may remain unchecked. Report
   blockers include safe counts. Arabic messages carry
   `ar_review: unreviewed_arabic` pending ADR-0033 native-speaker review.
2. **Preview:** no writes. Return entity counts, exact totals as decimal strings,
   reconciliation results (`true` for a checked control, `null` only when that
   control and its details are absent), and `master_updates` (existing masters
   whose values change). SHA-256 covers version, tenant, company, batch identity,
   date, currency, server-derived precision, canonical rows, report, referenced
   master state and before/after master snapshots. Object keys are sorted;
   row order is retained and approval changes if rows are reordered. No source
   spelling or financial number is corrected.
3. **Apply:** authenticate early using the server-owned backend session's
   `opening_import` capability, tenant/company membership and human identity.
   Require `confirmed_by` equal to that identity and the exact preview hash.
   Request-supplied roles/capabilities are forbidden. Within one transaction,
   recompute validation and master snapshots, claim the company opening, write
   masters before details, and journal the hash, source digest, approver and
   before/after snapshots. A changed master requires a new preview approval.
   An identical committed batch returns `already_applied` using its original hash
   and source digest; an altered batch returns `IMP-CONFLICT`. A different batch
   with any opening rows for the same `(tenant, company)` returns
   `IMP-OPENING-CONFLICT`, including legacy reference records without a claim.
   There is no supersede/reversal path; master-only batches remain possible.
   Write/journal failure rolls back inserts **and prior-record updates** and
   records a sanitized failed attempt with the authenticated user ID. The
   offline failure log is append-only per tenant and has no retention cap.
   Older records without an actor keep a null user ID. Rollback or failure-log
   errors require recovery (`IMP-RECOVERY`). Auth and initial validation
   refusals do not write a failure record.

## Entities and invariants

| Entity | Allowed fields | Stable business key |
|---|---|---|
| Customer | customer_code, customer_name, customer_type, customer_group, territory, tax_id | customer_code, else customer_name |
| Supplier | supplier_code, supplier_name, supplier_type, supplier_group, tax_id | supplier_code, else supplier_name |
| Item | item_code, item_name, item_group, stock_uom | item_code |
| Warehouse | warehouse_name, parent_warehouse | warehouse_name |
| Account | account_number, account_name, parent_account, account_type | account_number, else account_name |
| TrialBalance | account, account_type, debit, credit | batch and row index |
| AR | customer, amount | batch and row index |
| AP | supplier, amount | batch and row index |
| Stock | item_code, warehouse, qty, valuation_rate | batch and row index |

Master keys include tenant and company in storage. Keep the same key field on
subsequent uploads: switching a name-only record to a new code is a different
business key and requires prior owner resolution, never an automatic merge.
Duplicate master keys and opening details that resolve to the same master key tuple return `IMP-DUPLICATE`.
An opening batch may contain one trial-balance row per account, one AR row per
customer, one AP row per supplier and one stock row per item and warehouse pair.
Opening rows may state `posting_date` and `currency`; both must equal the batch context.

Every detail reference must resolve by a stable master key in the batch or the
existing backend records for the exact tenant/company: trial balance to Account,
AR to Customer, AP to Supplier, stock to Item and Warehouse. Unknown or ambiguous
references return `IMP-REFERENCE`. Every trial-balance row requires `account_type`:
`Receivable`, `Payable`, `Stock` or `Other`, matching its resolved Account master.
An existing Account cannot be reclassified by this importer. Mapping and new
master classifications still need accountant review; the offline store does not
look up a live chart of accounts. Debit and credit are nonnegative and cannot both be positive
on one line. Total debit must equal total credit **exactly**, without tolerance.
Every nonzero control line requires matching details, even when control lines
net to zero. Details require their corresponding control in the trial balance,
even if their amount is zero. Compare AR to receivable debit minus credit, AP to
payable credit minus debit, and stock to stock debit minus credit; mismatches or
missing reconciliation return `IMP-RECONCILE`.

Amounts accept plain ASCII decimal strings, integers or finite `Decimal`.
Binary floats, booleans, exponent strings, separators, negative amounts, NaN and
Infinity are refused. Debit, credit, AR/AP amounts and stock valuation rates
with more decimal places than the server-derived precision return `IMP-PRECISION`,
including excess trailing zeroes. Stock quantity must exceed zero and supports
up to 18 decimal places. Stock valuation rate may be zero. The comparison and
preview sum each derived `qty * valuation_rate` using explicit `ROUND_HALF_UP`
at currency precision. Source quantities and rates are preserved. Arithmetic
uses up to 38 significant input digits and an independent 128-digit Decimal
context. Q-478 tracks how to import negative opening balances. No tax,
exchange conversion or ledger-entry generation is implemented here.

Caps: 10,000 rows (server may lower), 1,024 characters per text cell, two million
input string bytes including report, 200,000 nodes and 12 nesting levels. Because
DSC-019 accumulates findings and compares names pairwise, each entity dataset is
also capped at 250 rows and a conservative two-million-cell pairwise name
comparison budget before its invocation (`IMP-LIMIT`); this conservative
offline budget must be reassessed before live bulk import. Text starting with
`=`, `+`, `-`, `@`, tab or carriage return is rejected after NFKC detection-only
normalization and leading Unicode whitespace/format/control removal. Any `Cf`
or `Cc` character anywhere in text is also rejected. Accepted source spelling is
unchanged. Numeric fields follow their stricter decimal grammar.

## DSC-011 and DSC-019 integration

Use `from_tabular(sheet, mapping)` on a `TabularConnector.extract()` sheet.
Headers map explicitly, one-to-one, to the fields above; unmapped headers and
cells, duplicate headers, hidden content, comments, external links, preambles and
formula cells (including cached numeric values) fail closed. The adapter retains
all source cell text. The flattened model-facing `normalise()` output lacks
formula provenance and is deliberately not used as financial source data.

Run DSC-019 `prevalidate` on all mapped rows before normalization, configuring
its required fields and logical field mapping for the source. Supply its entire
v1 `to_dict()` result or JSON. Accepted-row multisets must match all batch rows
exactly. Quarantine, findings, owner-review pointers or name groups block the
entire batch; none are dropped or adopted. Current v1 has no confirmed-duplicate
contract and no informational finding codes. A caller cannot downgrade a finding
or add `confirmed: true` to unlock apply: resolve upstream and regenerate a clean
report. A supplied report alone grants no trust. Every stage directly reruns
DSC-019 `prevalidate()` on each submitted dataset with server-owned mappings for
party/item names and posting dates. Missing row date/currency inherits batch
context. Import-required fields and exact control reconciliation are checked by
the importer; transaction-document defaults (`type`/`date`) are inapplicable to
these master/opening schemas. Any server-generated finding/quarantine/name group
blocks the batch, even if the supplied report is forged and internally consistent.
Tests consume real CSV/XLSX outputs and the unmodified DSC-019 producer.

## Runtime backend and Tier 3 review

`ImportBackend` isolates storage and session authority, as the existing engine
adapter does. A native writer must enforce its own document/link permissions,
resolve account classifications and existing master identities, preserve exact
numeric inputs, and commit its unique journal **in the same transaction** as all
business writes. Never combine independently committing adapter helpers, DDL,
external effects, or a separate journal database with this atomic promise.
Native stock/subledger posting must avoid duplicating control-account effects;
the SQLite reference store makes no native GL changes. Live integration must
prove that behavior before it is exposed to customer traffic. [Q-303](../../../../../docs/open-questions.md)
tracks the UNVERIFIED Opening Invoice Creation Tool / Journal Entry / Stock
Reconciliation wiring and role mapping. The SQLite backend maps trusted
`Accounts Manager` / `System Manager` sessions to `opening_import` only when
`CHANGE_ENGINE_ENV` is `dev` or `test`. A live backend must supply a verified
mapping. ADR-0039 is the requested role-mapping reference,
but that record is absent from the checked `origin/main`; its existence and
applicability must be resolved under Q-303 before production wiring.
Production audit durability and integrity are tracked in ERP-026 and SEC-008.

Before merge: a different model reviews the patch; Eldon records line-by-line
human review (ADR-0031/0035); security reviews the session, tenant, hash and
transaction boundaries; a native speaker reviews Arabic. Synthetic arithmetic
regressions are not official vectors or certification evidence. Production
posting and any applicable accountant/phase-exit acceptance remain separate
review evidence. ERP-013 remains `doing` pending review and live posting (Q-303).

Run from the repository root:

```bash
PYTHONPATH=apps/engine/change_engine:. python3 -m pytest apps/engine/change_engine/change_engine/tests/test_erp_013_opening_importer.py apps/engine/change_engine/change_engine/tests/test_erp_013_review_fixes.py -q
```
