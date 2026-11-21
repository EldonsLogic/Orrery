# Session log: ce-sec-007-live-suite-opt-in

Date: 2026-11-21
Author: partner
Tool and model: Codex / GPT-6.2 Sol
Plan IDs: CE-SEC-007

## Summary
Live MariaDB Suite B skips by default and validates explicit credentials before connecting to the throwaway dev stack.

## Files touched
- `apps/engine/change_engine/change_engine/tests/test_live_mariadb_suite_b.py` adds the opt-in gate and removes credential defaults.
- `apps/engine/change_engine/change_engine/tests/test_ce_sec_007_live_suite_opt_in.py` checks offline skipping and both missing-credential cases.
- `apps/engine/change_engine/README.md` documents the opt-in command and the schema writes.
- `.github/workflows/tests.yml` runs the offline regression and installs the existing Suite B driver for it.
- `docs/PLAN.md` records CE-SEC-007 as done.

## Evidence
- On main at `fe95ac7`, all three regression assertions failed because the connection mock was called.
- After the fix, pytest reported two regression tests passed and five live tests skipped. Unittest also reported five skipped. The connection mock saw zero calls.
- The engine CI test selection passed 56 tests. The script test suite passed 22 tests.
- No live database was used.

## Decisions
Tier 2 under ADR-0035 because this changes test code and CI.

## Tokens or cost
Unknown.

## Next step
Cross-model review of CE-SEC-007.
