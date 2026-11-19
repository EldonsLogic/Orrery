# Session log: erp-027-rereview-fixes

Date: 2026-11-18
Author: partner
Tool and model: antigravity / gemini-4-hydrogen
Plan IDs: ERP-027

## Summary
Completed and verified the fixes and regression tests for the four cross-model re-review findings on PR #125 (`ERP-027`): allow-listed no-op `MODIFY` validation, quote/backtick-aware DDL splitting, expanded MariaDB `information_schema` whole-table fingerprinting, `db.sql` DDL recording, fail-closed live callers when `frappe.db` is missing or column/revision reads fail, and per-deployment applied-state tracking; rebased cleanly onto `origin/main`.

## Files touched
- `apps/engine/change_engine/change_engine/guarded_apply/ddl_plan_gate.py`: added `_scan_top_level` quote/backtick/comment/semicolon-aware clause splitter, `_normalize_sql`, `noop_modify_allowlist`, `new_column_matches_plan`, `SCHEMA_COLUMN_ATTRS`/`SCHEMA_KEYS`, and exact allow-list + whole-table fingerprint enforcement in `assess_applied_ddl` (from `3f4f554`).
- `apps/engine/change_engine/change_engine/api/endpoints.py`: expanded `_read_table_schema` (`CHARACTER_SET_NAME`, `COLLATION_NAME`, `EXTRA`, `COLUMN_COMMENT`, `GENERATION_EXPRESSION`, `ORDINAL_POSITION`, `TABLE_CONSTRAINTS`, `CHECK_CONSTRAINTS`, `TRIGGERS`, `TABLES`), recorded DDL through `db.sql` alongside `db.sql_ddl`, removed silent `in_memory`/`offline_simulator` and synthetic-column/revision-hash fallbacks when `frappe` is present, and tracked applied deployments per `deployment_id` (from `3f4f554`).
- `apps/engine/change_engine/change_engine/tests/test_api_deployment.py`: updated live-mode `information_schema` stub rows for expanded schema queries (from `3f4f554`).
- `apps/engine/change_engine/change_engine/tests/test_erp_027_decimal_drift.py`: added tests for quote-aware splitting, `noop_modify_allowlist`, `new_column_matches_plan`, charset/collation/EXTRA/constraint/trigger/order bypasses, lossy `MODIFY`-then-restore, `db.sql` recording, adapter reuse, and fail-closed live callers (91 passed, 91 subtests passed).
- `docs/PLAN.md`: merged `origin/main` cleanly (`ERP-027` remains `doing` pending one live disposable-bench apply + Eldon review of `.github/workflows/tests.yml`).

## Decisions
- None.

## Tokens or cost
Unknown.

## Next step
Get Eldon's review on PR #125 (including `.github/workflows/tests.yml` shared path) and run one apply on a disposable bench before marking `ERP-027` `done`.
