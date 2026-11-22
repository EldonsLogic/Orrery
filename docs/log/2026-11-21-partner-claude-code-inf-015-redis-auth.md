# Session log: inf-015-redis-auth

Date: 2026-11-21
Author: partner
Tool and model: claude-code (Claude Opus 5.5), implementation sub-agent
Plan IDs: INF-015

## Summary
The dev, headless and isolation Docker stacks now run `redis-cache` and `redis-queue` (which also backs `redis_socketio`) with a per-run `requirepass` password on an internal `redis_internal` network that only engine services join (R-033, T18).

## Files touched
- `infra/dev/docker/docker-compose.dev.yml`, `docker-compose.headless.yml`: Redis gets `REDIS_PASSWORD` by name, writes an owner-only `/tmp/redis.conf` (`requirepass`, `protected-mode yes`) and starts through the image entrypoint (drops to the `redis` user); fails closed on an empty or non-URL-safe password; authenticated healthcheck; only on internal `redis_internal`; the engine joins it and waits for healthy Redis.
- `infra/dev/docker/isolation/docker-compose.isolation.yml`: worker gets the password and joins `redis_internal`.
- `infra/dev/docker/entrypoint.sh`: refuses to start without a URL-safe `REDIS_PASSWORD`; writes `redis://:<pw>@host:6379` for `redis_cache`, `redis_queue`, `redis_socketio` into `common_site_config.json` (mode 600, atomic swap).
- `infra/dev/docker/run_real_bench_ci.py`, `isolation/run_isolation_suite.py`, `smoke_headless_engine.py`: mint `secrets.token_urlsafe(32)` per stack, passed only through the environment (runner diagnostics already redact `*PASSWORD*`). The readiness probe authenticates with the bench's own URLs.
- `infra/dev/docker/verify_dev_bench.py`: proves each Redis answers with the password and refuses an unauthenticated PING.
- `infra/dev/docker/run_50_tenant_load_spike.py`: Redis metrics authenticate inside the container.
- `infra/dev/docker/tests/test_inf_015_redis_auth.py` (new), `test_engine_entrypoint.py`, `test_erp_020_headless_compose.py`: offline compose/runner/verifier checks, plus Docker entrypoint checks (fail closed, URLs, mode 600).
- `infra/dev/docker/README.md`: how the password is generated and where it lives.
- `infra/dev/docker/HEADLESS.md`: manual start lists `REDIS_PASSWORD`; network list names `redis_internal` (Redis is no longer on `data`).
- `apps/engine/change_engine/change_engine/tests/live_sec_004_bench_attacks.py`: removed only the `expectedFailure` marker on `test_redis_requires_authentication`, after it passed live (unexpected success).
- `docs/risks.md` R-033: mitigating (dev/test by INF-015; production via INF-005). `docs/PLAN.md` INF-015: doing.

## Verification
This session was resumed after a rate limit. The work commit (87ffc2d) was re-checked, and this log was committed again with hooks on.
- Offline: `infra/dev/docker` unittest discovery (as tests.yml runs it, with Docker available, so the entrypoint fail-closed checks ran): 88 tests OK, 10 skipped (live-bench and networked-build tests). SEC-004 adapter tests (`test_sec_004_cross_tenant_isolation.py`, pytest, `PYTHONPATH=apps/engine/change_engine`): 5 passed. `scripts/tests`: 22 passed. check_docs, check_repo_hygiene, scan_secrets, check_plan_independence and check_lanes (partner) all OK.
- Live, own throwaway project `inf015-sec004-live` (dev and isolation overlay): `redis-cli ping` without auth gives `NOAUTH`, with the password `PONG`; `protected-mode yes`; `/tmp/redis.conf` is 600 and owned by redis; `redis-server *:6379` with no password on argv; no published port; only on `redis_internal` (internal=true). MariaDB, which is not on that network, gets no DNS name and times out connecting to the Redis IP; the engine connects. All three bench URLs (`redis_cache`, `redis_queue`, `redis_socketio`) authenticate from `common_site_config.json` (mode 600), and the worker ran RQ jobs through the authenticated queue.
- Live SEC-004 suite (`run_isolation_suite.py`, project `inf015-sec004-live`, port 18452): provisioning of the three tenants succeeded, but `setUpClass` fails with `login ... HTTP 404`. That 404 is the ERP-020 route-guard `before_request` hook blocking `/api/method/login`; it predates INF-015 and SEC-021 tracks it. To get a live result anyway, a scratch harness outside the repo ran the suite's two Redis methods against the kept stack. `test_redis_requires_authentication` gave an unexpected success (anonymous clients get `AuthenticationError`), so its marker is removed. `test_shared_cache_keys_hold_no_tenant_data` now fails with `AuthenticationError`: its inspector uses `redis.Redis(host=host)` without the password. Fixing it is outside this task's allowed paths (see Next step).
- Live verifier: on a hand-started throwaway project `inf015-verify` (dev compose, per-run passwords), `bench new-site` with erpnext, hrms and change_engine took 312 s. `verify_dev_bench.py` then printed "Verified ... authenticated Redis and HTTP" (rc 0).
- `run_real_bench_ci.py` (projects `inf015-realbench-live`, `inf015-realbench-live2`): the stack came up with healthy authenticated Redis and the authenticated readiness probe passed. Both runs then timed out in the runner's fixed 300 s `bench new-site` step on this loaded host (312 s measured above), so the CE-SEC-005 suite did not run here. Not verified locally; real-bench.yml CI is the check.
- All throwaway projects were torn down with `down -v` for that project only. No other container, volume or port was touched.

## Decisions
- One shared password for both Redis services per stack (not per-service ACL users): the engine needs both anyway, so separate passwords add no isolation between them; ACL users per bench belong with production (INF-005).
- Compose interpolates `${REDIS_PASSWORD:-}` (lenient) instead of `:?`, so the many read-only `docker compose exec` callers (the SEC-004 live suite, ERP-014 tests, `scripts/provision_tenant_site.py`) keep working; fail-closed is enforced at runtime by Redis and the engine entrypoint instead.

## Tokens or cost
Unknown.

## Next step
- SEC-021 (or a scoped follow-up): `live_sec_004_bench_attacks.py::test_shared_cache_keys_hold_no_tenant_data` must authenticate. Its inspector should use `redis.Redis.from_url(json.load(open('sites/common_site_config.json'))[key])`, not `redis.Redis(host=host)`. The `test_redis_requires_authentication` docstring still says "CONFIRMED LEAK" and should become a regression note. The suite's login is blocked by the ERP-020 guard, so the whole live suite stays red until SEC-021 lands.
- The `run_real_bench_ci.py` 300 s provisioning timeout is tight for erpnext, hrms and change_engine on a loaded machine (312 s measured). Raise it in a separate row if CI also hits it.
- Production Redis auth and ACLs: INF-005.
- Cross-model review of this PR (Tier 2, security infra).
