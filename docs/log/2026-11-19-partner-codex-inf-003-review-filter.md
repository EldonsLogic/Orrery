# Session log: inf-003-review-filter

Date: 2026-11-19
Author: partner
Tool and model: codex / gpt-6.1-sol
Plan IDs: INF-003

## Summary
Closed remaining INF-003 filter defects after verifying the existing fixes at 97cefb3. INF-003 remains doing pending real staging deployment.

## Files touched
- `.github/workflows/tests.yml`: replace echo pipelines with here-strings so grep cannot SIGPIPE the producer under pipefail; shared scripts trigger all suites; unmapped changed Python tests fail explicitly until their suite is configured.
- `scripts/tests/test_services_ci_filter.py`: execute the actual workflow shell with synthetic Git failures, empty diffs, main/manual events, large diffs, shared scripts, unknown services and unmapped tests.

## Verification
- Regression tests observed failing before implementation: large diff deselected seven required suites, shared script selected only scripts, and an unmapped test silently passed.
- `python3 -m unittest discover -s scripts/tests -p test_services_ci_filter.py -v`: 8 tests passed.
- Required docs, hygiene, lane and secret checks passed.
- Executed the configured workflow commands in a clean virtual environment with all suites selected; results below. YAML parsed successfully; all compileall steps passed.
- Existing changes at the old head already handle merge-base/diff failures, main trigger, cross-service dependencies, gateway jsonschema dependency, disabled deploy guard and Q-273 renumbering.

## Decisions
- No architecture change; hosting and secret schema remain deferred to INF-001. No staging deployment enabled.

## Tokens or cost
Unknown.

## Next step
Cross-model re-review of INF-003. Complete founder staging prerequisites before enabling deployment; no CI polling or merge in this session.

## Local workflow results

Commands and environment settings are the matching named steps in `.github/workflows/tests.yml`.

| Step | Result |
|---|---|
| Blueprint validator, compiler and adapter tests | 1199 passed in 177.70s (0:02:57) |
| Contract example validates | 0 error(s), 6 warning(s) |
| Contract schemas and examples | Contracts OK (16 schemas) |
| Control-plane identity and support tests | 114 passed in 0.47s |
| Datasets generator and loader tests (DAT-002) | 105 passed in 0.68s |
| Discovery and connector tests | 409 passed, 5 xfailed in 8.25s |
| Gateway token and cost metering tests (PLT-025) | Ran 10 tests in 0.011s; OK |
| Tool API and AG-UI tests (OPR-003, OPR-020) | 181 passed, 1 skipped in 5.78s |
| Studio API and static tests | 70 passed in 26.55s |
| Engine unit, adapter and conformance tests | Ran 14 tests in 0.264s; OK; Ran 15 tests in 0.445s; OK (skipped=1); 5 passed in 0.18s; 6 passed in 1.79s; 15 passed in 1.50s; Ran 7 tests in 0.029s; OK |
| Engine adapter conformance suite (BPL-025 via change_engine.adapter) | 208 passed in 40.00s |
| Frappe runtime engine adapter conformance suite (ERP-012 via make_frappe_harness) | 208 passed in 40.55s |
| Eval harness tests and sets | 303 passed, 22 xfailed in 3.52s |
| Script tests (phase exit check) | 20 passed, 20 subtests passed in 1.48s |
| Dev bench contract, pin and entrypoint tests (live tests skip without a bench) | Ran 17 tests in 6.565s; OK (skipped=3) |
| Engine invisibility crawler tests (QA-016) | Skipped: suite absent on this branch; see note below |
| Trading Arabic, ZATCA and country pack component tests | Ran 6 tests in 0.232s; OK; Ran 4 tests in 0.097s; OK; Ran 32 tests in 0.027s; OK; Ran 3 tests in 0.093s; OK |

The first local optional crawler command returned exit 5 (zero tests) because
ignored bytecode from the previous branch left an empty test directory. Removed
only those caches; reran the exact conditional command, exit 0 with the absent
suite skipped, matching a clean checkout. The crawler was verified separately
on PR #160 (14 passing tests). Optional country-pack/event/accounts tests absent
on this branch were also skipped by their existing file guards. Live engine
and bench checks remain unverified where the output records skips.

Contract example warnings (6) are existing fixture/brand warnings, with zero errors.
`python3 scripts/finish_session.py` completed with FINISHED after push.
