# Session log: inf-003-main-merge

Date: 2026-11-19
Author: partner
Tool and model: codex / gpt-6.1-sol
Plan IDs: INF-003

## Summary
Merged origin/main f444b67 into PR #163, preserved every main validation command, integrated CE-SEC-002 and QA-007 into filtered CI, and renumbered the staging prerequisites question from Q-222 to Q-291. INF-003 remains doing pending staging.

## Files touched
- `.github/workflows/tests.yml`: retain main CE-SEC mock tests under the engine filter; run QA-007 brand tests with tools/token triggers and mapped-test recognition; preserve SEC-010 under the Blueprint suite and all prior fail-closed diff fixes.
- `scripts/tests/test_services_ci_filter.py`: regression coverage for newly merged suite paths and brand inputs.
- `docs/open-questions.md` and two PR-only logs: Q-291 references; main logs unchanged.
- `docs/PLAN.md`: preserve main statuses and INF-003 doing.

## Verification
- New regressions failed before integration (CE-SEC tests rejected as unmapped; brand inputs skipped), then all 10 filter tests passed.
- YAML and shell syntax validated; every origin/main validation command accounted for in the filtered workflow.
- Gateway dependency step installs Blueprint requirements, which pin jsonschema 4.26.0; all 10 gateway tests passed in an isolated environment using that exact install command.
- Main logs and question rows are byte-identical; deployment remains disabled.
- Initial full replay found an integration defect: brand pytest generated a docs-tools bytecode cache before Blueprint tests (1331 passed, one no-bytecode assertion failed). Set PYTHONDONTWRITEBYTECODE=1 on the brand step and removed only generated cache before replaying the affected steps.
- Full local workflow replay and required repository checks recorded below.

## Decisions
- No architecture change. Q-291 remains the staging blocker; no deployment enabled.

## Tokens or cost
Unknown.

## Next step
Cross-model review of the merge; complete founder staging prerequisites before closing INF-003. No CI polling or PR merge in this session.

## Local workflow results

All compileall steps passed. The corrected affected steps passed on replay: brand 20 tests; Blueprint 1332 tests. The optional crawler step initially saw an empty untracked directory left by switching from QA-016; removed only empty directories and reran the exact guarded command successfully (suite absent on this branch). Live staging and bench-dependent checks remain unverified.

| Suite | Result |
|---|---|
| Tenant theme and contrast tests (QA-007) | 20 passed; no docs bytecode |
| Blueprint validator, compiler and adapter tests | 1332 passed after bytecode fix |
| Contract example validates | 0 errors; 6 existing warnings |
| Contract schemas and examples | 16 schemas OK |
| Control-plane identity and support tests | 114 passed in 0.46s |
| Datasets generator and loader tests (DAT-002) | 105 passed in 0.65s |
| Discovery and connector tests | 409 passed, 5 xfailed in 7.80s |
| Gateway token and cost metering tests (PLT-025) | Ran 10 tests in 0.012s |
| Tool API and AG-UI tests (OPR-003, OPR-020) | 181 passed, 1 skipped in 5.69s |
| Studio API and static tests | 70 passed in 26.42s |
| Change engine security mock tests, fast (CE-SEC-001..004; real-bench run is real-bench.yml) | 54 passed, 22 subtests passed in 0.32s |
| Engine unit, adapter and conformance tests | Ran 14 tests in 0.261s; Ran 15 tests in 0.443s; OK (skipped=1); 5 passed in 0.18s; 6 passed in 1.78s; 15 passed in 1.59s; Ran 7 tests in 0.031s |
| Engine adapter conformance suite (BPL-025 via change_engine.adapter) | 208 passed in 38.80s |
| Frappe runtime engine adapter conformance suite (ERP-012 via make_frappe_harness) | 208 passed in 40.65s |
| Eval harness tests and sets | 303 passed, 22 xfailed in 3.55s |
| Script tests (phase exit check) | 22 passed, 29 subtests passed in 2.20s |
| Dev bench contract, pin and entrypoint tests (live tests skip without a bench) | Ran 17 tests in 6.819s; OK (skipped=3) |
| Engine invisibility crawler tests (QA-016) | Absent on this branch; guarded command passed after empty-directory cleanup |
| Trading Arabic, ZATCA and country pack component tests | Ran 6 tests in 0.231s; Ran 4 tests in 0.095s; Ran 32 tests in 0.019s; Ran 3 tests in 0.086s |

Required docs, hygiene, secrets and plan-independence checks passed. Lane guard and finish-session gate verified after committing and pushing.
