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
