# Session log: bpl-046-real-bench-class

Date: 2026-11-26
Author: partner
Tool and model: claude-code / claude-sonnet-5-5 (worker), claude-opus-5-5 (coordinator)
Plan IDs: BPL-046

## Summary
BPL-046 (BPL-041 slice 2): real-bench CI gets a BPL-027 phase that runs the trading-fixture bench class on a fresh site with `REQUIRE_BPL027_LIVE=1`, so any skip or a vacuous run fails. Coordinated from docs/log/2026-11-26-partner-claude-code-partner-g1-sprint.md.

## Task trail
- Worker A: Claude Sonnet 5.5 high (T3 `delegate_task`, own worktree from main, no git). Allowed paths: `infra/dev/docker/run_real_bench_ci.py`, `infra/dev/docker/docker-compose.bpl027-test.yml`, `infra/dev/docker/tests/`, `infra/dev/docker/README.md`, `.github/workflows/real-bench.yml`.
- `run_real_bench_ci.py`: layers the BPL-027 compose file. It adds a last phase: pinned requirements install, a fresh `bpl027-*` site, an in-container class run, `REQUIRE_BPL027_LIVE=1`, at least 10 live tests, any skip fails. It shares the pass/fail check with ERP-014 and ERP-015.
- `docker-compose.bpl027-test.yml`: read-only `docs/brand/tools` and `docs/brand/tokens` mounts. Without them the fixture compile fails (`BP-BRAND-001`).
- `real-bench.yml`: timeout 75 to 90 minutes. The phases total 4770 s, leaving 630 s of headroom.
- Runner tests: 135 run, OK, 10 skipped (baseline 125). Change-engine suite: 1853 passed, 86 skipped.
- Local bench run of the new phase alone (scratch driver, longer limits): 10 ran, 7 failed. `test_01`, `test_01b` and `test_02` passed. `test_03` ended `recovery_required` at step 42 (`entity.add /entities/customer`): "DDL rejected before execution: executed ADD COLUMN clauses differ from the approved plan" (`custom_customer_code varchar(140)`). Tests 04 to 08 failed on that missing prerequisite.
- Likely cause (UNVERIFIED): the plan uses `length` = `maxLength` 20, while `apply_native_custom_field` omits `length`. Engine fix dispatched to Claude Opus 5.5 in this worktree (hard debugging, DDL path).

## Files touched
- infra/dev/docker/run_real_bench_ci.py, infra/dev/docker/docker-compose.bpl027-test.yml, infra/dev/docker/README.md, infra/dev/docker/tests/test_erp_031_real_bench_valuation.py, infra/dev/docker/tests/test_ce_sec_005_real_bench_ci.py, infra/dev/docker/tests/test_inf_015_redis_auth.py, .github/workflows/real-bench.yml.

## Decisions
- Coordinator: the PR opens only once the class passes, or with the next defect named. Merging the phase while the class fails would turn real-bench CI red on every engine PR.

## Tokens or cost
Unknown.

## Next step
- Engine fix for `test_03`, then a full local run of the phase, then the PR.
- UNVERIFIED: site provisioning took 297 to 306 s locally against a 300 s limit; the 600 s class limit is unmeasured for a passing run.
- Noted, not changed: the `real-bench.yml` path filters miss `services/blueprint/**`, `contracts/**` and `docs/brand/**`; the change-engine README's BPL-027 section is stale.
