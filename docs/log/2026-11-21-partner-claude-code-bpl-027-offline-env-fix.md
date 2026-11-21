# Session log: bpl-027-offline-env-fix

Date: 2026-11-21
Author: partner
Tool and model: claude-code
Plan IDs: BPL-027

## Summary
Fixed the CI python-tests failure on PR #150: after merging main (ERP-027), three offline tests hit `offline_ddl_simulator_forbidden` because `CHANGE_ENGINE_ENV` was unset. The test module now sets `CHANGE_ENGINE_ENV=test` via a module-level `mock.patch.dict` (same pattern as the ERP-012 and BPL-008 suites); the production guard is unchanged. With the variable unset: BPL-027 tests 5 passed, 9 skipped (was 3 failed); ERP-012, BPL-008 and ERP-027 suites 22 passed; docs, hygiene and secret checks clean.

## Files touched
- apps/engine/change_engine/change_engine/tests/test_bpl_027_fixture_real_adapter.py: module-level env patch (setUpModule/tearDownModule)
- merge of main (bca4a2a) into the branch

## Decisions
- None, or link to ADR / strategy decision.

## Tokens or cost
Unknown or approximate, if known.

## Next step
What the next session should pick up, with plan IDs.
