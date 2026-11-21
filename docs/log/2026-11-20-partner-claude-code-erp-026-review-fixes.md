# Session log: erp-026-review-fixes

Date: 2026-11-20
Author: partner
Tool and model: claude-code (Claude Sonnet 5.5)
Plan IDs: ERP-026

## Summary
Fixed every finding of Eldon's 2026-11-19 cross-model review on Tier 3 PR 126 (ERP-026 durable adapter state) and added a regression test for each, run on SQLite offline and on a real MariaDB 11.4. Tier 3 human review and ADR-0041 acceptance by Eldon are still pending; the PR is not merged.

## Files touched
- apps/engine/change_engine/change_engine/adapter/engine.py: the site reset to `ready` is decided by the acquire (finding 1); `provision_site` and `sync_members` roll back when the key was lost, and `sync_members` holds the site row lock (2); ownership checked before every journal entry, engine step and DDL, unexpected errors close the run `failed_clean` or `recovery_required`, a lost lease returns the stored outcome as `ok: true` (3); events carry the tenant, a misrouted call on a bound store gets `tenant_not_found` (5); module docstring (6).
- apps/engine/change_engine/change_engine/adapter/storage.py, mariadb_store.py, store_api.py: `acquire_operation` reports `ready_before`, new `operation_owned`, `idem_status`, `lock_site_row`; tenant binding (`tenant_id=` at construction, `TenantMismatch`) and `tenant_id` on `adapter_events`.
- apps/engine/change_engine/change_engine/tests/test_erp_026_pr126_review_fixes.py: new, 29 tests (11 scenarios on SQLite and MariaDB, tenant binding on both).
- apps/engine/change_engine/change_engine/tests/test_erp_026_durable_adapter_state.py, test_erp_026_review_fixes.py: `REQUIRE_ERP026_MARIADB=1` fail-closed guard, placeholder password in the docstring, the lost-lease test now expects `ok: true`.
- .github/workflows/tests.yml: new job `erp-026-mariadb` (MariaDB 11.4 service, digest pinned, `REQUIRE_ERP026_MARIADB=1`); no existing step changed.
- docs/runbooks/adapter-recovery-required.md, docs/runbooks/README.md: runbook for clearing `recovery_required`.
- docs/decisions/ADR-0041-durable-adapter-state-on-tenant-database.md: still Proposed; decision text, follow-ups and tests updated.

## Decisions
- Contract 5.6.1 says an operation record that exists returns `ok: true` with an outcome, so a worker that lost its lease now returns the stored `recovery_required` outcome (replayed) instead of raising. No contract change.
- Lost key in `provision_site` and `sync_members` gives `concurrent_change` (retryable); the retry is a correct first run. No operation record exists for those two operations.
- Tenant binding is optional at construction (unbound stays the default for dev, tests and the conformance harness); the platform id is always allowed. A migration of pre-existing adapter state is not written because none is deployed (stated in ADR-0041).
- Clearing `recovery_required` stays manual SQL in a runbook (hooks are refused in production); an audited admin operation would need a contract change (Eldon's lane) and is not planned.

## Verification
- Each new test fails on the pre-fix code (23 of 23 scenario tests, run against the PR head) and passes on the fix.
- ERP-026 suites on MariaDB 11.4 with `REQUIRE_ERP026_MARIADB=1`: 63 tests, none skipped; without the variable and without a server they skip, and with the variable and no server they fail.
- Engine adapter unit tests (15) and the adapter conformance suite for both harnesses (208 each) pass.
- Not run: the new CI job itself (it runs on GitHub); its command was run locally against the same image. The restore test needs `docker exec` into the service container, found in CI with `docker ps --filter publish=3306` (UNVERIFIED on a hosted runner until the first run).

## Tokens or cost
Unknown.

## Next step
Eldon: Tier 3 line-by-line review of `engine.py`, `storage.py` and `mariadb_store.py`, and accept or change ADR-0041. Then ERP-003 (wire the engine effects onto the tenant connection), the 30-day key purge job and the restore drill on the real bench (CE-SEC-005).
