# Session log: bpl-041-check-ready-refusals

Date: 2026-11-25
Author: partner
Tool and model: claude-code (Claude Sonnet 5.5 child wrote the code test-first; Claude Opus 5.5 coordinator reviewed, applied and ran the tests)
Plan IDs: BPL-041

## Summary
First slice of BPL-041. `FrappeRuntimeBackend.check_ready` now finds the BPL-031 refusals of `entity.add`, `field.add` and `relation.add` (`protected_subject`, `subject_missing`, `unique_or_index`, plus `unsupported_value_type` so the reason matches the execute path) before the first step runs. A plan whose first step is valid and whose second is refused now writes nothing; before, step 1 ran and was then compensated. The execute-time checks stay as a second line. The bench class in `test_bpl_027_fixture_real_adapter.py` reads `REQUIRE_BPL027_LIVE=1`: no skip, and `setUpClass` fails when no bench is usable (same rule as ERP-031). Nothing sets the flag yet: the real-bench runner (`infra/dev/docker/run_real_bench_ci.py`) does not run BPL-027 at all, so wiring it is slice 2 and BPL-041 stays `doing`.

## Files touched
- `apps/engine/change_engine/change_engine/adapter/frappe_backend.py`: `_check_entity_refusals` and `_check_entity_add`, called at the end of `check_ready` (read-only).
- `apps/engine/change_engine/change_engine/tests/test_bpl_041_check_ready_refusals.py`: new, 8 tests (7 failed before the change; disabling only the new call fails the check_ready and engine-level tests again).
- `apps/engine/change_engine/change_engine/tests/test_bpl_027_fixture_real_adapter.py`: `REQUIRE_BPL027_LIVE` handling only; `test_05` unchanged.
- `.github/workflows/tests.yml`: new test file in the BPL-027/031 step.
- `docs/PLAN.md`: BPL-041 `doing`.

## Tests
- New file, both `test_bpl_031_*`, `test_bpl_033_location_hardening`, `test_bpl_027`, `test_bpl_012`: 90 passed, 10 skipped (bench class), 27 subtests passed.
- All 59 engine test files listed in `tests.yml`: 1,501 passed, 86 skipped, 27 failed. The failures are only the known Hijri-date ones (`test_cmp_005_calendar`, `test_cmp_005_hijri_dates`, `test_erp_007`, `test_erp_016`), which fail on main too.

## Not verified or not covered
- Real bench: not run here.
- Role-grant refusals and `field.set_property` on `/unique` or `/indexed` still refuse only at execute time (outside the row's named refusals; `set_property` would need plan-level knowledge of fields added earlier in the same plan).
- `check_ready` judges against the current engine state. A plan that adds a unique field with `field.add` and then re-adds it with `entity.add` could be refused falsely; that is unlikely while unique DDL is refused anyway.
- If a field's metadata exists without its column, `check_ready` says `unique_or_index` where execute says `recovery_required`. Both are clean refusals.

## Decisions
- None.

## Tokens or cost
Unknown.

## Next step
BPL-041 slice 2: add a BPL-027 phase to `infra/dev/docker/run_real_bench_ci.py` (fresh `BPL027_BENCH_SITE`, engine container with `jsonschema`, the `docker-compose.bpl027-test.yml` mounts, minimum 10 tests, `REQUIRE_BPL027_LIVE=1`) and update `infra/dev/docker/tests/test_erp_031_real_bench_valuation.py`.

## Review round 1 (cross-model review, gpt-6.1-sol)
- R1 (earlier steps ignored): `check_ready` now walks the steps in order with an in-memory projection (`made_types`, `made`) of the types and fields earlier steps create, and judges each step against the engine plus that projection. A field an earlier step adds never carries unique or index (Q-603); a type `entity.add` creates carries its fields' flags.
- R2 (false `subject_missing`): the projection includes types created by `entity.add` of an unmapped entity and by `field.add` or `relation.add` (`_ensure_doctype_exists`); a mapped `entity.add` still raises `subject_missing` for a type nothing earlier creates. Tests: the passing plan runs to the end, and plans execute would refuse are still refused.
- R3 (`need()` skipped under the flag): new `missing_prerequisite(env, state, key)`; with `REQUIRE_BPL027_LIVE=1` a missing prerequisite fails, otherwise it skips as before. `need()` calls it.
- R4 (survivors): added the `unsupported_value_type` refusal test; the zero-write spy now fails on any document or DocType insert, `set_value`, commit, DDL helper or non-read `db.sql`, and on any difference in the whole simulated site state. Both survivors (no unsupported-type check; DocType insert during readiness) now fail the new file.
- R5 (`get_meta` cache fill): accepted; one comment in `_held_fields`.
- R6 (malformed steps): `_check_step_shapes` runs first and raises the backend's existing side-effect-free `invalid_request` with `details.fields` (as `_location_kind` does). Covers step, subject, params, definition, fields (list of dicts), parents (list of dicts with `id`).
- Counts: new file 8 -> 21 tests (13 added; all pass). Both `test_bpl_031_*`, `test_bpl_033`, `test_bpl_027`, `test_bpl_012` and the new file: 103 passed, 10 skipped. All 59 engine files in `tests.yml`: 1,514 passed, 86 skipped, 27 failed (only the known Hijri-date ones).

## Review round 2 (gpt-6.1-sol re-review `d0c93e2..c1666d1`: REQUEST_CHANGES; fixed by the coordinator)
- R2 to R6 closed; R1 partly: N1 Medium, the projection was updated during one `entity.add`'s field scan, so `note` plus `custom_note` skipped projecting `custom_custom_note` (execute judges every field against the metadata before the step). Fixed: additions are collected per step and merged after the scan. New regression `test_fields_of_one_entity_add_are_judged_against_the_state_before_that_step` fails without the fix, passes with it.
- N2 Low, not fixed here (existing execute gap, follow-up): fields of an adapter-made type live in DocField, while execute's snapshots read only Custom Field metadata, so a second step on such a field returns `recovery_required`. The readiness-only test stays, documented.
- All 59 engine files: 1,515 passed, 86 skipped, 27 Hijri-only failures.

## Review round 3 fixes (Eldon's review at `2cae2164`)
- M1 Medium: `field.add` or `relation.add` with a truthy `unique` or `indexed` on a field no existing engine field holds passed `check_ready` (recorded as `_NO_CONSTRAINT`) and then always failed at the DDL gate as `engine_unavailable` after earlier steps had written. Now refused as `plan_rejected` / `unique_or_index` (side-effect-free) in `_check_entity_refusals` and in the execute path, before `_ensure_doctype_exists` writes. Truthiness matches the rest of the file (`defn.get("unique") or defn.get("indexed")`), so the string "1" counts. A held field that already carries the constraint behaves as before. Tests (class `TestConstraintOnAFieldNoEngineFieldHolds`, 7): the two-step probe, unique on a missing table, indexed relation, unique on an existing table, truthy "1", falsy flags still pass, held constrained field unchanged. Red before the fix: 5 failed, 2 passed (the two guards); green after: 7 passed.
- L1 Low: the two fail-closed tests now catch `unittest.SkipTest` and call `self.fail`, so a removed branch fails instead of skipping. Proved with an in-memory-only monkeypatch of `missing_prerequisite` (no fail-closed branch): both tests FAIL (2 failures, 0 skipped); nothing left mutated.
- L2 Low: docstrings now say the flag is "to be set by real-bench CI (slice 2)".
- Overlap note: BPL-043 (#312) adds `_refuse_constrained_fields`; both guard the same Q-603 gap on different paths, so expect a small merge in `frappe_backend.py` near `_check_entity_refusals` and the `field.add` execute branch.
