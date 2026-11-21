# Session log: erp-020-live-http-token

Date: 2026-11-21
Author: partner
Tool and model: codex
Plan IDs: ERP-020

## Summary
Fixed credential delivery for the real-bench HTTP suite on PR #148. The runner generates a fresh internal token for each new stack. Compose passes it to the engine and the test process by environment, and the HTTP helper presents it as `X-Internal-Token`.

## Files touched

- `infra/dev/docker/run_real_bench_ci.py` and `infra/dev/docker/docker-compose.dev.yml` wire the credential and validate the engine environment during readiness. A reused stack requires its existing credential in `ENGINE_INTERNAL_TOKEN`.
- `test_ce_sec_005_live_http.py` asserts an adapter request with user credentials alone receives `404`. The cross-worker policy check uses the allowed policy evaluation RPC and still checks revision and site scoping. The real-bench suite separately checks enforcement on document writes.
- Docker tests verify matching per-run credentials in the resolved engine and test environments, credential redaction, and parity between Compose configurations.

## Decisions

- Implemented option (a) from the decision on PR #148. The real bench uses the registered route hook in the loopback development stack. The WSGI guard has its own unit and Compose checks.

## Verification

- Route and WSGI guards passed 64 tests with Werkzeug 3.1.3. Docker test discovery passed 42 tests and skipped 10 opt-in tests. The scripts suite passed 22 tests and 29 subtests.
- The full real-bench runner passed all 16 tests, including all 10 live HTTP cases, on a disposable Compose project with no published database port.
- Docs, repository hygiene, secret scan, plan independence and the PR merge-base lane check passed.
- The branch also has an existing `python-tests` CI failure on the missing suite mapping for `test_erp_020_route_guard.py` in `.github/workflows/tests.yml`. That workflow is outside this patch's scope.

## Tokens or cost

Unknown.

## Next step

Review the new real-bench result on PR #148 and address the separate Python suite mapping failure. ERP-020 remains doing.
