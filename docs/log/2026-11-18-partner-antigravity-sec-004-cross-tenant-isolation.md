# Session log: sec-004-cross-tenant-isolation

Date: 2026-11-18
Author: partner
Tool and model: antigravity
Plan IDs: SEC-004

## Summary
Built and verified the cross-tenant isolation test suite (`SEC-004`) across the change-engine adapter and Frappe runtime backend, the CE-SEC-003 runtime policy store, the AI metering/budget gateway, and a live two-site Compose runtime verifier (`verify_tenant_isolation.py`).

## Files touched
- `apps/engine/change_engine/change_engine/tests/test_sec_004_cross_tenant_isolation.py`: tests cross-tenant adapter isolation (config exports, plan tokens, idempotency keys, custom field schema/data probes, member sync, fail-closed `platform` and unknown tenants, audit separation) on both SQLite and `SimulatedFrappeRuntime`, plus `FrappeSiteResolver` traversal rejection and `PolicyStore` per-site isolation.
- `services/gateway/tests/test_sec_004_gateway_isolation.py`: tests fail-closed tenant context validation, spoofed metadata-key rejection, independent per-tenant budget exhaustion, session ledger isolation, and `meter.ai_usage` event attribution.
- `infra/dev/docker/verify_tenant_isolation.py`: live two-site Compose isolation verifier checking distinct site DB credentials and `common_site_config.json` encryption-key non-sharing, symmetric MariaDB `errno 1142` denial across `SELECT`/`COUNT`/`INSERT`/`UPDATE`/`DELETE`, Frappe ORM canary isolation, Redis cache isolation, and HTTP `Host`/token swap rejection (`401`/`404`).
- `infra/dev/docker/tests/test_sec_004_live_isolation.py`: offline unit and fail-closed contract tests for `verify_tenant_isolation.py`.
- `.github/workflows/tests.yml`: runs `test_sec_004_cross_tenant_isolation.py` alongside gateway and Docker bench unit discovery suites.
- `docs/PLAN.md`: marks `SEC-004` as `done`.
- `docs/log/2026-11-18-partner-antigravity-sec-004-cross-tenant-isolation.md`: session log.

## Decisions
- Live verification against disposable two-site stack `sec004-verify` (`alpha.localhost` and `beta.localhost`, torn down cleanly with `down -v`) passed all checks: symmetric MariaDB `errno 1142`, ORM/Redis isolation, `own_a`/`own_b` HTTP `200`, cross-host tokens HTTP `401`, and cross-host doc fetch HTTP `404`.
- All three CI suites pass (`4 passed, 6 subtests passed` in `test_sec_004_cross_tenant_isolation.py`, `12 OK` in `services/gateway/tests`, `20 OK (skipped=3)` in `infra/dev/docker/tests`).

## Tokens or cost
Unknown (T3 Code session).

## Next step
Pick up `CE-SEC-005`: CI against a real Frappe bench instead of mocks.
