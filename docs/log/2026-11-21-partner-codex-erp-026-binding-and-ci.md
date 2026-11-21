# Session log: erp-026-binding-and-ci

Date: 2026-11-21
Author: partner
Tool and model: codex / gpt-6.2-sol
Plan IDs: ERP-026

## Summary
Updated PR 126 to require a tenant-bound production store, fix the real-bench adapter fixture, and run ERP-026 under the path-filtered CI workflow.

## Files touched
- [Test workflow](../../.github/workflows/tests.yml) preserves main's suites, maps the three ERP-026 modules under the engine filter, and retains the separate digest-pinned MariaDB 11.4 job with required mode.
- [Decision index](../decisions/INDEX.md) retains main's entries and includes proposed ADR-0041 in order.
- [Store guard](../../apps/engine/change_engine/change_engine/adapter/store_api.py) raises `StoreRefused` for an unbound production-grade store in production, including the default and empty environment.
- The ERP-026 guard tests cover production and test environments. The CE-SEC-005 bench test uses explicit test environments for both adapter instances with test hooks off, so the fresh adapter still reloads state from the live backend.
- [ADR-0041](../decisions/ADR-0041-durable-adapter-state-on-tenant-database.md) records the binding requirement and the same-key retry after engine-user changes. The [runbook](../runbooks/adapter-recovery-required.md) covers interrupted finalization and lease recovery. [ERP-026](../PLAN.md) is `doing` pending the hosted MariaDB job.

## Verified
- The new production refusal test reproduced the gap in four environment cases before the guard change. After the fix, the offline ERP-026 step passed 30 tests and 39 subtests, with 36 live tests skipped.
- Without a server configured, `REQUIRE_ERP026_MARIADB=1` exited 1 with 37 failures and zero skips. On the CI-pinned MariaDB 11.4.13 image, it passed all 66 tests, including dump and restore, with zero skips. The throwaway container used a separate loopback port and was removed afterward.
- BPL-012 and ERP-012 passed 15 tests. Both adapter conformance harnesses passed 208 tests each. CE-SEC mocks passed 54 tests and 22 subtests. The real-bench runner passed 9 tests and 6 subtests, and the six live Frappe cases skipped offline.
- Docs, repo hygiene, secret scan, plan independence and partner lanes passed. Script tests passed 22 tests and 29 subtests. The workflow filter mapped every changed test path and selected the engine suite.

## Decisions
- The rescue snapshot at `2e63bde` rewrites storage and adapter code and removes the MariaDB job, PR 126 regression module, recovery runbook and an existing log from `2323d32`. This session inspected it read-only and ported no code or tests.

## Tokens or cost
Unknown or approximate, if known.

## Next step
ERP-026 still needs a green GitHub Actions MariaDB job, the live Frappe bench, and Tier 3 founder review and acceptance of ADR-0041. The local run verified the MariaDB store against the pinned image.
