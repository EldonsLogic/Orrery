# Session log: inf-015-review-fixes

Date: 2026-11-21
Author: partner
Tool and model: antigravity (Gemini 4 Argon; continued after a claude-code Claude Opus 5.5 rate limit)
Plan IDs: INF-015

## Summary
Resolved the Eldon (1-6) and Gemini (L1-L4) review findings on PR #242 (INF-015): merged `origin/main`, authenticated the live SEC-004 shared-cache inspector with the bench URLs, required specific `NOAUTH`/`AuthenticationError` refusals with positive controls, redacted Redis credentials in captured runner output, added a live cross-network unreachability probe in `smoke_headless_engine.py`, enforced a 32-character minimum password length with `rm -f /tmp/redis.conf` before writing, and preserved `REDIS_PASSWORD` under `--reuse-project`.

## Files touched
- `apps/engine/change_engine/change_engine/tests/live_sec_004_bench_attacks.py`: `test_shared_cache_keys_hold_no_tenant_data` connects via `redis.Redis.from_url(json.load(open('sites/common_site_config.json'))[key])` and pings before scanning; `test_redis_requires_authentication` asserts an authenticated PING positive control (`True`) and specific `AuthenticationError` on anonymous PING, with its stale `CONFIRMED LEAK` docstring updated.
- `infra/dev/docker/verify_dev_bench.py`: `redis_requires_auth` requires `anonymous.stdout.strip().startswith("NOAUTH")` alongside the authenticated `PONG` positive control so exec failures, DNS misses, or empty replies fail closed.
- `infra/dev/docker/run_real_bench_ci.py`: added `redact(text, env)` (env secrets plus `rediss?://...:<pw>@` credentials), captured and redacted `verify_dev_bench.py` output, and kept `REDIS_PASSWORD` from the environment when `--reuse-project` is set (failing closed if missing).
- `infra/dev/docker/smoke_headless_engine.py`: redacted captured `compose up`, `bench new-site`, and sidecar error output; added `REACH_PROBE` (`redis-cache:6379` and `redis-queue:6379` unreachable with `"dns"` or `"refused"` from `engine_internal`, positive control `"connected"` to `engine:8000`) and `ENGINE_REDIS_PING` positive control from the engine container.
- `infra/dev/docker/isolation/run_isolation_suite.py`: redacted `provision_tenant.sh` stderr on provisioning failure using `run_real_bench_ci.redact`.
- `infra/dev/docker/docker-compose.dev.yml`, `infra/dev/docker/docker-compose.headless.yml`: enforced `test "$${#REDIS_PASSWORD}" -ge 32` and `rm -f /tmp/redis.conf` before writing `/tmp/redis.conf`.
- `infra/dev/docker/entrypoint.sh`: enforced `[ "${#REDIS_PASSWORD}" -lt 32 ]` fail-closed guard before bench setup.
- `infra/dev/docker/README.md`: documented exact redaction scope, the unverified Frappe v15 `get_redis_conn` error-log risk, the 32-character minimum and `/tmp/redis.conf` removal, the cross-network smoke check, and INF-005 residuals (environment-variable exposure and shared `default` Redis user).
- `infra/dev/docker/tests/test_inf_015_redis_hardening.py`: 16 new offline unit tests covering items 2-8.
- `docs/PLAN.md`: resolved merge with `origin/main`, keeping all main rows and `INF-015` status `doing`.

## Verification
This session was started by `claude-code` (Claude Opus 5.5, saved as WIP commit `1ff09a1` when cut off by a rate limit), merged with `origin/main` (`6ce4262`), and verified and completed by `antigravity` (Gemini 4 Argon).
- Tests-first check: checking out pre-fix implementation files from `9102e6c` against `test_inf_015_redis_hardening.py` fails with 21 failures and 4 errors across the 16 test methods (every new test fails without the fix); restoring the fix passes all 16 tests.
- Offline suites: `python3 -m unittest discover -s infra/dev/docker/tests -v` ran 104 tests (OK, skipped=10); SEC-004 offline (`test_sec_004_cross_tenant_isolation.py` and `live_sec_004_bench_attacks.py` without context) ran 30 tests (5 passed, 25 skipped); `scripts/tests` pytest ran 22 passed (29 subtests).
- Governance and hygiene gates: `check_docs.py`, `check_repo_hygiene.py`, `scan_secrets.py`, `check_plan_independence.py`, and `check_lanes.py --base $(git merge-base origin/main HEAD) --actor partner` all passed.
- Live Docker checks on throwaway projects (torn down with `down -v`):
  - `python3 infra/dev/docker/smoke_headless_engine.py`: all checks passed (`ALL PASSED`), including `redis-cache unreachable from engine_internal (got dns)`, `redis-queue unreachable from engine_internal (got dns)`, `sidecar probe reaches the engine (got connected)`, and `engine answers an authenticated Redis PING on both services`.
  - `python3 infra/dev/docker/run_real_bench_ci.py` (throwaway project `ce-sec-005-5f152e89`): provisioned synthetic site `ce005-7bc04740.localhost`, passed `verify_dev_bench.py` (`Verified synthetic site ... authenticated Redis and HTTP`), and passed all 16 live tests in `test_ce_sec_005_real_bench` and `test_ce_sec_005_live_http`.

## Decisions
- Kept the single shared per-run `REDIS_PASSWORD` (minimum 32 URL-safe characters) for dev/test Compose stacks and documented container-env and shared `default` user residuals under INF-005.

## Tokens or cost
Unknown.

## Next step
- Re-review PR #242 and merge once CI is green on `inf-015-redis-auth`, then pick up SEC-021.
