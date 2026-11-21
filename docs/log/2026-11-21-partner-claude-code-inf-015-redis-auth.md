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
- `docs/risks.md` R-033: mitigating (dev/test by INF-015; production via INF-005). `docs/PLAN.md` INF-015: doing.

## Verification
RESULTS_PLACEHOLDER

## Decisions
- One shared password for both Redis services per stack (not per-service ACL users): the engine needs both anyway, so separate passwords add no isolation between them; ACL users per bench belong with production (INF-005).
- Compose interpolates `${REDIS_PASSWORD:-}` (lenient) instead of `:?`, so the many read-only `docker compose exec` callers (the SEC-004 live suite, ERP-014 tests, `scripts/provision_tenant_site.py`) keep working; fail-closed is enforced at runtime by Redis and the engine entrypoint instead.

## Tokens or cost
Unknown.

## Next step
NEXT_PLACEHOLDER
