# Session log: erp-013-review-round-3

Date: 2026-11-21
Author: partner
Tool and model: antigravity / Gemini 4 Hydrogen
Plan IDs: ERP-013

## Summary

Addressed PR #202 cross-model review round 3 findings (1 High, 2 Medium, 3 Low) and logged founder-decision open questions Q-521 and Q-522.

## Prompt / Brief

Fix PR #202 review findings for ERP-013 (`erp-013-opening-balances-importer`):
1. High: per-account control reconciliation for AR/AP/Stock (optional `account` link defaulted when one control account exists, required when multiple; nonzero control lines require matching nonzero detail total for that account; update default fixture).
2. Medium 2: verify batch currency equals backend company functional currency (`ImportBackend.company_currency`, `IMP-CURRENCY`), and echo `company`, `posting_date`, `currency` in preview.
3. Medium 4: near-duplicate checks on master name fields only (never codes/SKUs), plus server-recorded `owner_confirmed_distinct` confirmation via `confirm(...)` bound into `plan_hash` (never from source payload).
4. Low 6: merge master updates preserving omitted fields, allow explicit `""`/`None` clears, and report `changed_fields` / `cleared_fields` in `preview["master_update_fields"]`.
5. Low 7: allow standard Arabic directional/joining marks (`\u200c`, `\u200d`, `\u200e`, `\u200f`) while stripping format marks before formula prefix detection.
6. Low 8: update stale ADR-0039 text in `importer/README.md` and `Q-303`, and log `IMP-CONFIRM` mismatches at apply with the authenticated `user_id`.
7. Record open questions Q-521 (Medium 3: single opening claim vs DSC-019 budgets) and Q-522 (Medium 5: stock unit cost rounding at 2 decimals) in `docs/open-questions.md`.

## Files touched

- `apps/engine/change_engine/change_engine/importer/errors.py`: added `IMP-CURRENCY` and optional `name_groups`/`plan_hash` metadata on `ImportFailure`.
- `apps/engine/change_engine/change_engine/importer/backend.py`: added `company_currency`, `distinct_confirmations`, `record_distinct_confirmation` to `ImportBackend` and `SQLiteImportBackend` (`import_companies`, `import_distinct_confirmations`, `set_company_currency`, `opening_import_confirm` dev/test capability).
- `apps/engine/change_engine/change_engine/importer/validation.py`: implemented per-account control reconciliation (`_reconcile_controls`), functional currency verification, master name-only upstream checks, distinct-group confirmation checking, merge-with-explicit-clears master updates (`master_update_fields`), and `SAFE_FORMAT_MARKS` handling in `text()`.
- `apps/engine/change_engine/change_engine/importer/engine.py`: added `OpeningImporter.confirm()`, returned pending `name_groups`/`plan_hash` on unresolved name-group preview, wrote merged master rows at apply, and logged transactional `IMP-CONFIRM` failures with `user_id`.
- `apps/engine/change_engine/change_engine/importer/README.md`: documented new behavior and updated stale ADR-0039/Q-303 text.
- `apps/engine/change_engine/change_engine/tests/test_erp_013_opening_importer.py`: updated default `batch()` fixture to reconcile per account and updated `currency` plan-hash test for functional currency check.
- `apps/engine/change_engine/change_engine/tests/test_erp_013_review_fixes.py`: added regressions for per-account control reconciliation, dummy zero detail refusal, functional currency mismatch/preview echo, bound owner distinct confirmation, code-only non-duplicates, master merge/explicit clears, Arabic directional/joining marks, and `IMP-CONFIRM` failure logging.
- `docs/open-questions.md`: updated `Q-303` ADR-0039 status wording and added `Q-521` and `Q-522`.

## Decisions

- `confirm()` requires a separate `opening_import_confirm` capability (granted alongside `opening_import` in `dev`/`test` SQLite role mapping) and binds `owner_confirmed_distinct` to `(tenant_id, company, batch_id, source_digest)` on the backend and into `plan_hash`.
- Medium 3 and Medium 5 deferred as founder decisions in `Q-521` and `Q-522`.

## Verification

- Tests first: 61 failed, 93 passed before implementation fixes.
- After fixes: `test_erp_013_opening_importer.py` + `test_erp_013_review_fixes.py`: 154 passed.
- `scripts/tests`: 22 passed, 29 subtests passed.
- `check_docs.py`: 0 errors, 0 warnings; `check_repo_hygiene.py`: OK (1672 files); `scan_secrets.py`: 0 hits; `check_plan_independence.py`: OK; `check_lanes.py` (against merge-base with `origin/main`, actor `partner`): OK.

## Tokens or cost

Unknown.

## Next step

Tier 3 re-review on PR #202 and founder decisions on Q-303, Q-478, Q-521, and Q-522 (ERP-013).
