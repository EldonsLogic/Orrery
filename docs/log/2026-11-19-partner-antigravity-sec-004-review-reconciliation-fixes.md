# Session log: sec-004-review-reconciliation-fixes

Date: 2026-11-19
Author: partner
Tool and model: antigravity
Plan IDs: SEC-004,SEC-021,INF-015

## Summary
Reconciled PR #131 (`sec-004-isolation-suite`) and PR #159 (`sec-004-review-reconciliation`), resolved all HIGH and MEDIUM review findings from both independent reviews on PR #131, kept `SEC-004` in `doing` until upstream Frappe RQ Job prefix isolation (`SEC-021`) and bench Redis authentication (`INF-015`) are remediated and re-verified on a live multi-site stack, and added fail-closed scheduled CI execution for the live isolation suite.

## Files touched
- `.github/workflows/sec-004-live-isolation.yml`: added weekly scheduled and `workflow_dispatch` workflow running `infra/dev/docker/isolation/run_isolation_suite.py` with `CI_REQUIRE_LIVE_SEC004=1`.
- `.github/workflows/tests.yml`: renamed the offline isolation step to explicitly state adapter-level (mocked/simulated) coverage.
- `apps/engine/change_engine/change_engine/adapter/frappe_backend.py`: restricted `FrappeSiteResolver` tenant IDs to `^t_[a-z0-9][a-z0-9_]{1,59}[a-z0-9]$` (matching the canonical contract while eliminating `_`/`-`/`.`/case collisions) and rejected colliding `site_map` targets.
- `apps/engine/change_engine/change_engine/tests/live_sec_004_bench_attacks.py`: renamed from `test_sec_004_live_bench_attacks.py` so default `unittest` discovery cannot silently skip it; added `CI_REQUIRE_LIVE_SEC004=1` fail-closed gate; fixed CSRF-vacuous `POST` probes and added positive controls across header-swap, API-token, public-file, File-traversal, and RQ Job tests; replaced fixed sleep with polling helper; added low-role principal, change-engine policy endpoint, distinct non-empty `encryption_key`, symmetric MariaDB write-isolation (`errno 1142` both directions), strict `SHOW GRANTS` + `LOAD_FILE`/`mysql.user`/`performance_schema`, deserialized Redis cache/queue key scan, and `--with-files` backup checks; reclassified `test_redis_requires_authentication` to HIGH (defence in depth) and linked both `@unittest.expectedFailure` probes to `SEC-021`/`R-032` and `INF-015`/`R-033`.
- `apps/engine/change_engine/change_engine/tests/sec004_isolation_probe.py`: added `site_config_summary()`, `create_low_role_user()`, and `register_canary_policy()` helpers for the live harness.
- `apps/engine/change_engine/change_engine/tests/test_sec_004_cross_tenant_isolation.py`: reframed docstrings explicitly as adapter-level (mocked/simulated) tests, expanded `FrappeSiteResolver` collision/invalid-tenant tests, and added SQL-path `PolicyStore` (`WHERE site_id = %s`) isolation test with `_SqlDbShim`.
- `docs/PLAN.md`: changed `SEC-004` from `done` to `doing` (aligned with PR #159) and added partner-owned `G1` rows `INF-015` (Redis auth) and `SEC-021` (RQ Job site isolation).
- `docs/risks.md`: updated `R-017` and added `R-032` (RQ Job prefix leak, HIGH) and `R-033` (unauthenticated shared Redis, HIGH defence in depth).
- `infra/dev/docker/isolation/README.md` and `infra/dev/docker/isolation/run_isolation_suite.py`: pointed runner to `live_sec_004_bench_attacks.py` with `CI_REQUIRE_LIVE_SEC004=1` and documented the scheduled CI workflow and tracked defects.
- `infra/dev/docker/verify_tenant_isolation.py`: fixed vacuous `no_shared_encryption_key` check (`bool(enc_a) and bool(enc_b) and enc_a != enc_b`), added synthetic low-role user probe with cleanup, and clarified positioning as lightweight standalone smoke verifier.
- `infra/dev/docker/tests/test_sec_004_live_isolation.py`: documented verifier/gate scope and added tests for missing encryption keys, low-role checks, and `CI_REQUIRE_LIVE_SEC004=1` fail-closed behavior.
- `docs/log/2026-11-19-partner-antigravity-sec-004-review-reconciliation-fixes.md`: this session log.

## Decisions
- PR #131 (`sec-004-isolation-suite`) remains the authoritative implementation PR for `SEC-004`; PR #159 (`sec-004-review-reconciliation`) is a docs-only multi-PR recovery/open-questions PR covering 13 plan IDs and `Q-210`..`Q-212`, so PR #159 is left open with a cross-PR reconciliation comment rather than closed.
- Per honest-evidence policy, `SEC-004` remains `doing` until `SEC-021` and `INF-015` are fixed and proven on a live multi-site bench.

## Verification
- Passed: adapter/engine tests (`test_sec_004_cross_tenant_isolation.py`, `test_erp_012_frappe_adapter.py`, `test_bpl_008_blueprint_rollback.py` — 18 passed, 16 subtests passed).
- Passed: BPL-025 adapter conformance suite against `make_frappe_harness` (208 passed).
- Passed: gateway unit & isolation suite (`services/gateway/tests`, `REQUIRE_EVSTREAM_TESTS=1` — 12 passed, including 2 `SEC-004` gateway isolation tests).
- Passed: docker verifier/contract tests (`infra/dev/docker/tests` — 22 discovered, 19 passed, 3 skipped because live bench / networked build integration flags were unset).
- Passed: `py_compile` on live attack suite, probe helper, verifier, and runner; `scripts/check_docs.py`, `scripts/check_repo_hygiene.py`, `scripts/scan_secrets.py`, `scripts/check_plan_independence.py`, `scripts/check_lanes.py`, and `git diff --check`.
- Not run in this session: the full throwaway 3-site Docker Compose run (`infra/dev/docker/isolation/run_isolation_suite.py`) was not executed locally in this environment; live execution is wired into `.github/workflows/sec-004-live-isolation.yml` (`workflow_dispatch` + weekly schedule).

## Tokens or cost
Unknown.

## Next step
Execute `.github/workflows/sec-004-live-isolation.yml` (or `run_isolation_suite.py` on a clean Docker host) to record live evidence for the hardened suite, then remediate `SEC-021` (RQ Job exact site matching) and `INF-015` (authenticated Redis) before marking `SEC-004` `done`.
