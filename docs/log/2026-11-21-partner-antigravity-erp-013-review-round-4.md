# Session log: erp-013-review-round-4

Date: 2026-11-21
Author: partner
Tool and model: antigravity / gemini-4-hydrogen
Plan IDs: ERP-013

## Summary
Addressed PR #202 round 4 review findings from Eldon (Claude Fable 5.2) and Opus 5.5 on `ERP-013`, merged `origin/main`, and split tests and validation modules to stay under 500 lines per file.

## Brief (ADR-0031 condition 4)
Implement PR #202 round 4 fixes for `ERP-013`:
1. Allow safe format marks (`\u200c`, `\u200d`, `\u200e`, `\u200f`, `\u061c`) only in name/free-text fields; refuse them in codes, account numbers, link fields, and `batch_id`; strip them from name-based master business keys.
2. Drop control account from Stock/AR/AP duplicate keys (`one AR per customer, one AP per supplier, one Stock per item+warehouse`).
3. Make `OpeningImporter.confirm` require and verify the pending `plan_hash`.
4. Make `import_distinct_confirmations` insert-only (append with `seq`) and record `distinct_confirmed_by` in `import_batches` at commit.
5. Default `SQLiteImportBackend` `company_currency` to `None` (fail closed with `IMP-CURRENCY`) and update fixtures.
6. Add `\u061c` (ALM) to safe format marks for name fields; map embedded tab/newline/CR to `IMP-SCHEMA` instead of `IMP-FORMULA` (leading tab/CR remain `IMP-FORMULA`).
7. Log `apply(..., confirmed_by=<other>)` failures in `import_failures` with the authenticated `user_id`.
8. Renumber `Q-521`/`Q-522` to `Q-550`/`Q-551` in `docs/open-questions.md` without editing old logs.
9. Keep files under 500 lines (`upstream.py` split from `validation.py`; `test_erp_013_review_round4.py` split from `test_erp_013_review_fixes.py` and wired into `.github/workflows/tests.yml`).
10. Merge `origin/main`.

## Files touched
- `apps/engine/change_engine/change_engine/importer/validation.py`: restricted `SAFE_FORMAT_MARKS` (with `\u061c`) to `NAME_TEXT_FIELDS`, mapped embedded tabs/newlines/CR to `IMP-SCHEMA`, stripped marks in `business_key` for name keys, dropped control account from AR/AP/Stock duplicate keys, verified `pending_plan_hash` in `prepare`, and delegated upstream checks to `upstream.py` (427 lines).
- `apps/engine/change_engine/change_engine/importer/upstream.py`: extracted bounded DSC-019 report and upstream prevalidation helpers (134 lines).
- `apps/engine/change_engine/change_engine/importer/engine.py`: required and verified pending `plan_hash` in `confirm(...)`; moved `apply(...)` confirmation validation inside `try` with sanitized hash logging in `record_failure` (156 lines).
- `apps/engine/change_engine/change_engine/importer/backend.py`: defaulted `default_currency` to `None`, migrated `import_distinct_confirmations` to append-only (`seq INTEGER PRIMARY KEY`), and added `distinct_confirmed_by` to `import_batches` (287 lines).
- `apps/engine/change_engine/change_engine/importer/README.md`: documented `confirm(..., plan_hash=...)`, append-only confirmations, `IMP-CONFIRM` failure logging, `\u061c`/format-mark field rules, and embedded whitespace codes.
- `apps/engine/change_engine/change_engine/tests/test_erp_013_opening_importer.py`: configured `company_currencies` in fixtures (452 lines).
- `apps/engine/change_engine/change_engine/tests/test_erp_013_review_fixes.py`: updated fixtures and `IMP-CONFIRM` failure-log test; split Round 3/4 tests into `test_erp_013_review_round4.py` (487 lines).
- `apps/engine/change_engine/change_engine/tests/test_erp_013_review_round4.py`: added 7 Round 4 regression tests (tests-first: 7 failed before fixes) plus moved Round 3 tests (360 lines).
- `.github/workflows/tests.yml`: wired `test_erp_013_review_round4.py` into the `ERP-013` step.
- `docs/open-questions.md`: renumbered `Q-521`/`Q-522` to `Q-550`/`Q-551`.

## Decisions
- Conservative AR/AP duplicate rule: one AR row per resolved customer and one AP row per resolved supplier (matching Stock one row per item+warehouse and `README.md`), rather than splitting one party across multiple control accounts.
- `confirm(...)` requires and verifies the pending `plan_hash` returned by `preview(...)`.

## Verification
- Tests-first on `test_erp_013_review_round4.py`: 7 failed before implementation fixes.
- After final edits:
  - `uv run --no-project --with pytest --with "pydantic>=2" env PYTHONPATH=apps/engine/change_engine:. python -m pytest apps/engine/change_engine/change_engine/tests/test_erp_013_*.py -q`: 162 passed.
  - `uv run --no-project --with pytest python -m pytest scripts/tests -q`: 22 passed, 29 subtests passed.
  - `check_docs.py`: 0 errors, 0 warnings.
  - `check_repo_hygiene.py`: OK.
  - `scan_secrets.py`: 0 hits.
  - `check_plan_independence.py`: OK.
  - `check_lanes.py --base $(git merge-base origin/main HEAD) --actor partner`: OK.

## Tokens or cost
Unknown.

## Next step
Tier 3 human line-by-line review and security review on PR #202 (`ERP-013`), plus founder decisions on `Q-303`, `Q-478`, `Q-550`, and `Q-551`.
