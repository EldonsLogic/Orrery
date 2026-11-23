# Session log: erp-031-real-bench-valuation

Date: 2026-11-23
Author: partner
Tool and model: claude-code (Sonnet 5.5)
Plan IDs: ERP-031

## Summary
Real-bench CI now runs the ERP-014 and ERP-015 live valuation layers on their own fresh sites (each with `tenant_id`) with the REQUIRE flags set, fails a run whose live layer skips, and ERP-015 gains a live back-dated issue and back-dated transfer and fails on any repost that is not `Completed` (`Skipped` included). Test and CI code only: no ledger, valuation or posting logic changed. The real bench was NOT run here.

## Files touched
- infra/dev/docker/run_real_bench_ci.py: after the CE-SEC-005 suite, provisions `erp014-<id>.localhost` and `erp015-<id>.localhost` (same `_provision_site`, so `tenant_id` is set), runs each suite on the host with `ERPxxx_COMPOSE_PROJECT`, the site variable and `REQUIRE_ERPxxx_LIVE=1`, and fails when unittest output reports any skip; both layers always run; drops every provisioned site on a reused project; `TOTAL_PHASE_LIMIT_SECONDS` (60 min).
- .github/workflows/real-bench.yml: job `timeout-minutes` 25 to 60 to cover the runner's phase limits; step name and comment.
- apps/engine/change_engine/change_engine/tests/test_erp_014_accounting_properties.py: `live_skip_reason` and `live_config_problem` (a REQUIRE flag of 1 never skips; the live class then fails in `setUpClass` without a bench); the all-or-nothing test uses them.
- apps/engine/change_engine/change_engine/tests/test_erp_015_inventory_valuation.py: same gate; new items E15-BKIS and E15-BKTX with back-dated issue `i3` and back-dated transfer `t3`, hand-computed exact figures (`BACKDATED_EXACT`, keys `id@warehouse` for a transfer's rows); `repost_problems` (anything but `Completed` fails) used by `test_9`; three new checker mutations; test_9 also checks the transfer nets to zero on Stock In Hand.
- apps/engine/change_engine/change_engine/tests/erp_015_bench_probe.py: the two new item codes only.
- infra/dev/docker/tests/test_erp_031_real_bench_valuation.py (new): offline tests for the runner (sites, tenant_id, flags, skip detection, drop), the REQUIRE flag (real subprocess runs of both live classes: skip without the flag, fail without skipping with it) and the workflow timeout.
- infra/dev/docker/tests/test_inf_015_redis_auth.py: the fake `subprocess.run` now records only the verifier's env (the runner now also starts two unittest subprocesses).
- tests.yml not changed: the new offline file sits in `infra/dev/docker/tests`, which the infra step already discovers (`unittest discover -s tests`); ERP-014/015 suites are already in their steps.

## What ran
- `cd infra/dev/docker && python3 -m unittest discover -s tests`: 114 tests OK (10 skipped, the unrelated live ones).
- `PYTHONPATH=apps/engine/change_engine python3 -m unittest` on the ERP-014 and ERP-015 suites: 35 tests OK (17 skipped = live classes, no bench).
- The oracle (`simulate`) independently reproduces my hand-computed figures for i1..i4 and t1..t5 (pure layer).
- `python3 scripts/check_repo_hygiene.py`: OK.

## Not verified (needs the real bench in CI)
- That the live layers pass on the real pinned bench: the new back-dated issue and transfer figures, and that every repost ends `Completed`. If the engine marks a legitimate repost `Skipped` (for example by de-duplication), CI now fails on purpose: report it, do not relax the check.
- That `setup_complete` (the probes create their company with it) works on a fresh site that has hrms installed, and that the live layers fit their 900 s limit each (job limit 60 min).
- The workflow's wall time: unmeasured.

## Decisions
- None. REQUIRE flags keep the existing names `REQUIRE_ERP014_LIVE` and `REQUIRE_ERP015_LIVE`.

## Tokens or cost
Unknown.

## Next step
Open the PR, read the first real-bench run (ERP-031): confirm the live layers ran (no `skipped`), tune timeouts from the measured time.
