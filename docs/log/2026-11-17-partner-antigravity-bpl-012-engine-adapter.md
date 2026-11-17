# Session log: bpl-012-engine-adapter

Date: 2026-11-17
Author: partner
Tool and model: antigravity
Plan IDs: BPL-012

## Summary
Implemented the `change_engine.adapter` package in `apps/engine/change_engine/` implementing `contracts/engine-adapter.md` v0.1.2 with SQLite durable state, `guarded_apply` DDL/safety/lock integration, unit tests, and CI conformance wiring, passing all 208 `BPL-025` conformance tests and 8 unit tests.

## Files touched
- `apps/engine/change_engine/change_engine/guarded_apply/__init__.py`: Guard optional Pydantic v2 workflow/report re-exports so pure-stdlib DDL gate, safety guardrails, and schema reconciler load in minimal contract test environments.
- `apps/engine/change_engine/change_engine/adapter/__init__.py`: Package exports (`ChangeEngineAdapter`, `ChangeEngineHarness`, `AdapterError`, `HooksDisabled`, `make_harness`).
- `apps/engine/change_engine/change_engine/adapter/contracts_support.py`: Canonical JSON hashing (`canon`, `sha`, `artifact_hashes`) and Draft 2020-12 contract validation with pure-Python context fallback.
- `apps/engine/change_engine/change_engine/adapter/mapping.py`: Blueprint-to-engine mapping integrating `ddl_plan_gate.inspect_frappe_ddl_plan` (including `decimal(21,9)` for `money`/`decimal`/`percent`), `safety_guardrails` (`ZONE_2_LOCKED_DOCTYPES`, `PROHIBITED_CODE_PROPERTIES`, `PROHIBITED_EXPRESSION_PATTERNS`), and `schema_reconciler.make_bounded_lock_key`.
- `apps/engine/change_engine/change_engine/adapter/storage.py`: `SQLiteAdapterStore` persisting sites, idempotency outcomes, plan tokens, plan evidence, prepare intents, execution journal, audit log, events, shadow members, and additive zero-drop tenant entity tables (`tstore_*`).
- `apps/engine/change_engine/change_engine/adapter/engine.py`: `ChangeEngineAdapter` implementing all 10 contract operations, 6+1 stage journaled apply/rollback with stored-inverse and initial-build compensation, and production `test_hooks=False` gating.
- `apps/engine/change_engine/change_engine/adapter/harness.py`: `ChangeEngineHarness` and `make_harness()` factory for `ADAPTER_HARNESS=change_engine.adapter.harness:make_harness`.
- `apps/engine/change_engine/change_engine/tests/test_bpl_012_engine_adapter.py`: Unit tests covering DDL gate decimal/index handling, Zone 2 and `eval:` guardrails, bounded lock keys, non-destructive SQLite persistence across restarts, and production hook gating.
- `.github/workflows/ci.yml`: Added `engine-adapter-conformance` CI job running `BPL-012` unit tests and `services/blueprint/tests/adapter` conformance suite.
- `docs/PLAN.md`: Updated `BPL-012` status from `todo` to `done`.

## Decisions
- Kept `change_engine.adapter` dependency-light (`jsonschema` + Python stdlib with pure-Python context fallback) so it runs in `services/blueprint/requirements.txt` CI environments while delegating DDL inspection, guardrails, and bounded advisory lock keys directly to `change_engine.guarded_apply`.
- Persisted tenant entity data tables (`tstore_*`) in SQLite using additive `ALTER TABLE ... ADD COLUMN` and quarantine state flags so field/entity removal never executes `DROP` or deletes stored tenant data (`ADP-C-050`).

## Tokens or cost
Unmeasured.

## Next step
Execute `ERP-021` (Phase 0 engine proof suite on a pinned bench), followed by `ERP-024` (maintained MariaDB LTS upgrade) and `PLT-025` (gateway token metering).
