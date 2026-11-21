# Session log: erp-027-review-fixes

Date: 2026-11-18
Author: partner
Tool and model: claude-code / sonnet-5.5
Plan IDs: ERP-027

## Summary
Fixed the cross-model review findings on PR #125: the DDL plan gate now fails closed (coded rejection) whenever Frappe's own inspection cannot run, no longer hides Rating, Duration or nullable-column drift, and the after-snapshot compares what Frappe really executed with the approved plan. `ERP-027` is set back to `doing` (live apply path unproven, see below).

## What changed (by finding)
- H1: `_DECIMAL_FIELDTYPES` is now Currency, Float, Percent only. Source: Frappe v15.126.0 `frappe/database/schema.py:201` (`elif self.fieldtype in ("Currency", "Float", "Percent")` is the only decimal branch that adds `not null default 0`; Rating and Duration get no default clause). Live bench confirms real Rating columns are `decimal(3,2)` default `NULL`, nullable. The old test that approved a Rating `0.00` default now asserts rejection.
- H1 (after-snapshot): `FrappeDeploymentAdapter.take_snapshot` no longer hard-codes `unapproved_side_effects=False`/`indexes_unchanged=True` on a live bench. The adapter records every statement Frappe runs through `frappe.db.sql_ddl` during `apply_native_custom_field` (still executed unchanged), keeps the approved plan from `persist_prepare_and_audit_intent`, and reads a whole-table fingerprint (columns with type, nullability, default, key; indexes) before and after. New pure `assess_applied_ddl` decides.
- H2: `inspect_frappe_ddl_plan(..., offline_simulator=False)`. Default uses ONLY Frappe's `MariaDBTable`; any failure returns `inspectable=False` with `reason_code` (`DDL_GATE_FRAPPE_UNAVAILABLE`, `_FRAPPE_IMPORT_FAILED`, `_INSPECTION_FAILED`, `_EXISTING_COLUMNS_MISSING`) and logs the exception. `offline_simulator=True` uses ONLY the simulator. No fallback chain. Offline is chosen explicitly by: the in-memory adapter, the ERP-012 backend when a test `frappe_factory` is injected (`offline_ddl_simulator`), `adapter/mapping.py` (planning-time classification on synthetic standard columns), the pymysql test harness, and tests.
- M1: nullability. `ColumnDesc` gains `nullable` (None = unknown). The zero-default normalisation requires `nullable is False`; the live adapter reads `IS_NULLABLE` from information_schema. Unknown or nullable stays a MODIFY and is rejected.
- M1 (statements that run): see the decision below.
- M2: CI step "DDL plan gate decimal drift and fail-closed tests (ERP-027)" added next to the BPL-007 step in `.github/workflows/tests.yml` (shared path: Eldon must review).
- M3: new negatives: Rating/Duration zero default, nullable and unknown nullability, raising inspection, DbColumn signature change, DbColumn import failure, frappe not importable, db not connected, no existing definitions with `decimal(18,2)` drift, upper-case `DECIMAL(18,6)` on the Frappe path, executed-vs-approved cases. Mutation checks: re-adding Rating/Duration fails 2 tests, removing the nullability check fails 2, forcing the simulator fails 19. Stand-in limits are now in the test docstring.
- L1: `_canonical_column_type` is now case and whitespace outside quotes only; the bare-synonym branch is gone; a test asserts the generated type for every `MARIADB_TYPE_MAP` entry is already canonical.
- L2: `_col_with` copies the live column dict and overrides only `type` or `default`, keeping extra keys.

## Files touched
- `apps/engine/change_engine/change_engine/guarded_apply/ddl_plan_gate.py`: all of the above (gate, coded reasons, `assess_applied_ddl`).
- `apps/engine/change_engine/change_engine/api/endpoints.py`: nullability read, whole-table fingerprint, DDL recording, after-snapshot comparison, explicit offline flag, caller updates.
- `apps/engine/change_engine/change_engine/guarded_apply/schema_reconciler.py`, `adapter/mapping.py`, `adapter/frappe_backend.py`: pass the explicit offline flag.
- Tests: `test_erp_027_decimal_drift.py` (48 tests), plus explicit `offline_simulator=True` or `nullable=False` in `test_ai_control_plane.py`, `test_bpl_007_apply_preview_gate.py`, `test_live_mariadb_suite_b.py`; `test_api_deployment.py` live-SQL test now has a `sql_ddl` double and an injected approved plan.
- `.github/workflows/tests.yml`: ERP-027 step. `docs/PLAN.md`: ERP-027 set to `doing`.

## Verified
- pytest (own venv, pydantic>=2, jsonschema): ERP-027 48 passed; BPL-007, BPL-012, ERP-012, ERP-021, BPL-008, test_api_deployment, test_ai_control_plane: 104 passed together with ERP-027; `services/blueprint/tests/adapter` 208 passed with the default harness and with `make_frappe_harness`. CI-style invocation (`PYTHONPATH=apps/engine/change_engine python -m pytest`) also passes.
- Live bench (`erp001.localhost`, Frappe 15.126.0, read-only probe copied to a temp dir in the container and removed afterwards, no restart, nothing written): the patched gate, fed the adapter-style column read (with IS_NULLABLE), approved 48 of 48 (Customer, Sales Order, Sales Invoice, Item x 12 fieldtypes). Negative controls on `grand_total` (`decimal(18,6)`, `decimal(21,2)`, default 5, nullable, unknown nullability) were all rejected; a call without existing definitions was rejected with `DDL_GATE_EXISTING_COLUMNS_MISSING`.

## Decision: statements that run vs the approved plan
Frappe's own apply (Custom Field insert) re-emits the phantom `MODIFY` clauses the gate normalises away (651 raw clauses on the bench). A strict string compare would therefore fail every apply on the core DocTypes. `assess_applied_ddl` rejects (unapproved side effect, apply ends in RECOVERY_REQUIRED) unless: every executed statement is an `ALTER TABLE` on the target table, the executed `ADD COLUMN` clauses equal the approved ones, and any extra clause is a `MODIFY` whose before/after table fingerprint proves all existing columns (type, nullability, default, key) and indexes unchanged and only the new column added. Unknown input fails closed. No ADR: this tightens the gate. Flag for review.

## NOT done or NOT verified
- The live APPLY path was not run (no writes on a shared bench): recording of `frappe.db.sql_ddl` during a real Custom Field insert and the real information_schema before/after comparison are covered by test doubles only. The statement recording assumes Frappe v15 emits DDL through `frappe.db.sql_ddl` (true for `MariaDBTable.alter`); another DDL route would show as a schema change with no recorded statement and be rejected, not missed. This is why `ERP-027` stays `doing`; it can become `done` after one apply on a disposable bench plus a green CI run of the new step.
- Frappe v16, MariaDB 11.x column-type output; whether MariaDB runs identical-definition MODIFYs instantly (review "not covered").
- The in-memory adapter and an injected-factory (simulated) backend still report no side effects: no real DDL runs there.

## Tokens or cost
Unknown.

## Next step
Run one apply on a disposable bench (ERP-027), get Eldon's review of the CI step, then set `done`.
