# Session log: bpl-007-apply-preview-ddl-gate

Date: 2026-11-17
Author: partner
Tool and model: antigravity / gemini-4-hydrogen
Plan IDs: BPL-007

## Summary
Hardened the change engine's preview-to-apply binding and DDL plan gate (`BPL-007`), resolved both `E0-7` findings from the Phase 0 engine proof report (`decimal(21,9)` approval regex + phantom zero-decimal default normalization on core ERPNext tables, and Stage 6 `RECOVERY_REQUIRED` persistence/blocking), verified against the live `erp001.localhost` bench, added BPL-007 unit tests in CI, and marked `BPL-007` `done`.

## Files touched
- `apps/engine/change_engine/change_engine/guarded_apply/ddl_plan_gate.py`: updated `APPROVED_DDL_REGEX` to permit `decimal(w,p)` type precision while blocking multi-clause `, DROP`/`MODIFY` injection, and added `_normalize_zero_decimal_defaults` inside `_inspect_with_frappe_mariadb_table` to suppress phantom MariaDB `INFORMATION_SCHEMA` `'0.000000000'` `MODIFY` diffs on untouched core decimal columns (`E0-7` #1).
- `apps/engine/change_engine/change_engine/guarded_apply/schema_reconciler.py`: invoked best-effort `db.mark_recovery_required(...)` when Stage 6 outcome persistence raises after Stage 4 DDL (`E0-7` #2).
- `apps/engine/change_engine/change_engine/api/endpoints.py`: emitted deterministic `preview_digest`, `base_revision_hash`, and structured `preview` from `propose_configuration_change` (failing closed on `ZoneSafetyViolation` and `DDL_PLAN_REJECTED`); added `FrappeDeploymentAdapter.mark_recovery_required` and blocked unresolved `PREPARED` + `RECOVERY_REQUIRED` rows in `is_target_in_recovery_required`; enforced preview-digest, statement-plan, and `proposal` binding in `apply_configuration_change` before Stage 3.
- `apps/engine/change_engine/change_engine/tests/test_bpl_007_apply_preview_gate.py`: added 5 unit tests covering `decimal(21,9)` gate approval and multi-clause rejection, zero-decimal normalization vs genuine drift, fail-closed proposal previews, preview-to-apply drift rejection (`PREVIEW_MISMATCH` / `DDL_PLAN_REJECTED`), and Stage 6 recovery persistence + stale `PREPARED` blocking.
- `.github/workflows/ci.yml`: installed `pydantic>=2` and added `test_bpl_007_apply_preview_gate.py` to `engine-adapter-conformance`.
- `docs/PLAN.md`: updated `BPL-007` status from `todo` to `done`.

## Verification
- Live Frappe bench (`platform-erp001-20261111b-engine-1`, site `erp001.localhost`): verified `inspect_frappe_ddl_plan` across `Customer`, `Sales Order`, `Sales Invoice`, `Delivery Note`, and `Item` for both `Data` (`varchar(140)`) and `Currency` (`decimal(21,9) not null default 0`) fields; all 10 checks returned `inspectable=True`, `is_approved_additive_only=True`, single `ADD COLUMN` statement with zero phantom `MODIFY COLUMN` noise.
- `PYTHONPATH=apps/engine/change_engine uv run --with pytest --with pydantic --with jsonschema python3 -m pytest apps/engine/change_engine/change_engine/tests --ignore=apps/engine/change_engine/change_engine/tests/test_live_mariadb_suite_b.py -q`: `148 passed, 50 subtests passed`.
- `PYTHONPATH=services/blueprint:apps/engine/change_engine ADAPTER_HARNESS=change_engine.adapter.harness:make_harness uv run --with pytest --with pydantic --with jsonschema python3 -m pytest services/blueprint/tests/adapter -q`: `208 passed`.
- `python3 scripts/check_docs.py`, `python3 scripts/check_repo_hygiene.py`, `python3 scripts/scan_secrets.py`, `python3 scripts/check_plan_independence.py`.

## Decisions
- Kept `APPROVED_DDL_REGEX` strictly anchored per ADR-001 Rev 2.3 while explicitly allowing `(?:decimal\(\d+,\d+\)|...)` only inside the column type declaration so commas cannot be used to smuggle additional `ALTER TABLE` clauses.
- Treated both `RECOVERY_REQUIRED` and unresolved `PREPARED` rows as recovery-blocking in `is_target_in_recovery_required`, backed by an explicit best-effort `mark_recovery_required` commit if Stage 6 persistence fails after Stage 4 DDL.

## Tokens or cost
Unknown.

## Next step
Review and merge PR for `BPL-007`. Next partner G1 items unlocked and ready: `BPL-008` (Rollback to a previous Blueprint version) and `ERP-012` (Frappe implementation of the engine adapter).
