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
three-letter `currency`, `datasets`, and a mandatory `prevalidation` report.
`currency_precision` defaults to 2 and accepts 0–6; production configuration must
supply the approved currency precision. `datasets` maps an entity below to row
dicts, or a DSC-019 `{"rows": [...], "sheet": ...}` wrapper. No unknown batch,
entity, row or mapping field is accepted.

1. **Validate:** no writes. Check schema, sizes, exact numbers, dates, currency,
   stable keys, formulas, the complete upstream report and reconciliation.
   A failure returns `ok: false` with an `IMP-*` bilingual catalog error, without
   copying raw cells. Report blockers include safe counts. Arabic messages carry
   `ar_review: unreviewed_arabic` pending ADR-0033 native-speaker review.
2. **Preview:** no writes. Return entity counts, exact totals as decimal strings,
   and reconciliation results (`true` when checked, `null` when either side is
   absent). SHA-256 covers version, tenant, company, batch identity, date,
   currency, precision, canonical rows **and report**. Object keys are sorted;
   row order is retained and approval changes if rows are reordered. No source
   spelling or financial number is corrected.
3. **Apply:** validate again. Resolve the current human identity and roles from
   the server-owned backend session. Require company and tenant membership,
   `Accounts Manager` or `System Manager`, `confirmed_by` equal to that identity,
   and the exact preview hash. Never accept request-supplied roles. Within one
   transaction, check the tenant/batch journal, write masters before opening
   details and journal the
   hash and approver. Same hash returns `already_applied`; another hash, including
   a different company under the same tenant/batch, returns `IMP-CONFLICT`.
   Write/journal failure rolls back inserts **and prior-record updates** and
   records a sanitized failed attempt. Rollback or failure-log errors require
   recovery (`IMP-RECOVERY`), never a blind successful retry.

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
Duplicate master keys within a batch are refused. Opening rows may additionally
state `posting_date` and `currency`; both must equal the batch context.

Every trial-balance row requires `account_type`: `Receivable`, `Payable`, `Stock`
or `Other`. A single account cannot have inconsistent types. Mapping and control
classification need accountant review; the offline store does not look up a live
chart of accounts. Debit and credit are nonnegative and cannot both be positive
on one line. Total debit must equal total credit **exactly**, without tolerance.
When both datasets are supplied, compare AR to receivable debit minus credit,
AP to payable credit minus debit, and stock to stock debit minus credit.

All amounts accept plain ASCII decimal strings, integers or finite `Decimal`;
binary floats, booleans, exponent strings, separators, negative amounts, NaN and
Infinity are refused. Stock qty must exceed zero; rate may be zero. Sum each
`qty * valuation_rate` rounded with explicit `ROUND_HALF_UP` to currency precision
for comparison/preview only; source qty/rate are preserved. Arithmetic uses an
independent bounded Decimal context (38 significant input digits, up to 18 places,
128-digit computation), regardless of the caller's context or traps. No tax,
exchange conversion or ledger-entry generation is implemented here.

Caps: 10,000 rows (server may lower), 1,024 characters per text cell, two million
input string bytes including report, 200,000 nodes and 12 nesting levels. Text
starting with `=`, `+`, `-`, `@`, tab or carriage return, including prefixes after
whitespace, is rejected. Numeric fields follow their stricter decimal grammar.

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
report. A supplied report is evidence, not signed authentication; the trusted
intake must generate it from the source rather than accept an assertion from an
untrusted client. Tests consume real CSV/XLSX outputs and real report producers.

## Runtime backend and Tier 3 review

`ImportBackend` isolates storage and session authority, as the existing engine
adapter does. A native writer must enforce its own document/link permissions,
resolve account classifications and existing master identities, preserve exact
numeric inputs, and commit its unique journal **in the same transaction** as all
business writes. Never combine independently committing adapter helpers, DDL,
external effects, or a separate journal database with this atomic promise.
Native stock/subledger posting must avoid duplicating control-account effects;
the SQLite reference store makes no native GL changes. Live integration must
prove that behavior before it is exposed to customer traffic.

Before merge: a different model reviews the patch; Eldon records line-by-line
human review (ADR-0031/0035); security reviews the session, tenant, hash and
transaction boundaries; a native speaker reviews Arabic. Synthetic arithmetic
regressions are not official vectors or certification evidence. Production
posting and any applicable accountant/phase-exit acceptance remain separate
review evidence, not implied by a done implementation row.

Run from the repository root:

```bash
PYTHONPATH=apps/engine/change_engine:. python3 -m pytest apps/engine/change_engine/change_engine/tests/test_erp_013_opening_importer.py -q
```
