# Session log: bpl-027-review-fixes

Date: 2026-11-20
Author: partner
Tool and model: antigravity
Plan IDs: BPL-027

## Summary
Addressed PR #150 review findings on `BPL-027`: made mid-step backend failures fail closed to `recovery_required` unless proven side-effect-free (with DB rollback and execute-before-mutate), made warehouse company resolution fail closed when multiple companies exist and documented `location.disable` as a no-op with zero companies, and wired the offline `BPL-027` tests into CI.

## Files touched
- `apps/engine/change_engine/change_engine/adapter/frappe_backend.py`: Added `side_effect_free: bool = False` to `FrappeBackendError` (marked true only for pre-write validation/acquire/session/lookup failures); wrapped `execute_step` with `f.db.rollback()` on exception; updated `_find_warehouse` to fail closed (`site_not_ready`) when >1 Company exists without an explicit company name and return `(None, None)` on `location.disable` when 0 companies exist.
- `apps/engine/change_engine/change_engine/adapter/engine.py`: Executed `frappe_backend.execute_step` before mutating `site.config`/`site.retained` in `_exec` (removing `copy.deepcopy` snapshot restoration and reference aliasing), and escalated backend exceptions in `_execute_all` to `recovery_required` (`comp_fault = True`) whenever `side_effect_free` is not explicitly true.
- `apps/engine/change_engine/change_engine/tests/test_bpl_027_fixture_real_adapter.py`: Added offline regression tests for proven side-effect-free failure compensation, partial-write failure triggering `f.db.rollback()` and `recovery_required`, multi-company fail-closed warehouse lookup, explicit company lookup, and zero-company `location.disable` no-op.
- `.github/workflows/tests.yml`: Added the offline `BPL-027` pytest step after merging `origin/main` while preserving all existing CI steps.
- `docs/log/2026-11-20-partner-antigravity-bpl-027-review-fixes.md`: This append-only session log.

## Decisions
- Kept `BPL-027` as `doing` in `docs/PLAN.md` pending follow-up resolution of the 3 engine-conformance gaps identified on the live bench.
- Did not add cross-lane `docs/PLAN.md` rows for the 3 discovered gaps; tracked them here for follow-up scoping once owner confirms lane split:
  1. Built-in role/workflow-state case-insensitive name collisions (`test_04b`, e.g. `sales_manager` vs `Sales Manager`, `draft` vs `Draft`).
  2. `entity.add` on existing core DocTypes ignoring `definition.fields` and Blueprint->engine field mapping (`test_05`).
  3. `role.upsert` not syncing `definition.permissions` to `Custom DocPerm` (`test_06`).
- Provenance of prior live-bench evidence: the live-bench run recorded in `docs/log/2026-11-18-partner-claude-code-bpl-027-fixture-real-adapter.md` corresponds to commit `2e4a3d36efd8dc0089140c30b67473a9722b6216` (note: `~`-relative default paths in `test_bpl_027_fixture_real_adapter.py` and `README.md` were adjusted right before committing `2e4a3d3` and have not been re-run on a live bench after this review-fix commit; offline tests and both BPL-025 conformance harnesses were re-run here).

## Tokens or cost
Unknown.

## Next step
Wait for owner review of PR #150 (`BPL-027`) and follow up on the 3 engine-conformance gaps once scoped, then re-run `TestBpl027FixtureRealAdapter` on a live bench before closing `BPL-027`.
