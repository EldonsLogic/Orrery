# Session log: sec-004-merge-main

Date: 2026-11-21
Author: partner
Tool and model: codex
Plan IDs: SEC-004

## Summary
Merged main (`c3fce8b`) into PR #131 and restored all five SEC-004 adapter isolation tests.

## Files touched
- `.github/workflows/tests.yml` keeps main's path-filtered workflow and adds the SEC-004 adapter step under the engine filter. The existing gateway and Docker test discovery steps pick up their SEC-004 tests. The separate live workflow is unchanged.
- `frappe_backend.py` keeps SEC-004's strict tenant-ID validation, injective site-name mapping, and explicit mapping collision check. The invalid tenant ID is still marked side-effect-free, and BPL-027's rollback and warehouse company handling carry through from main.
- `test_sec_004_cross_tenant_isolation.py` opts both simulated adapters into offline DDL under a module-scoped `CHANGE_ENGINE_ENV=test`. Forward and inverse artifacts use the renamed field in their steps, source operations, and postconditions before resealing. The test requires tenant A's change to reach `applied` before probing data and keeps the same tenant isolation assertions.

## Decisions
- ERP-027 (`162c146`) requires an explicit offline DDL opt-in in dev or test. Without it, the injected runtime uses live DDL inspection and this fixture returns `approval_missing` for `gateApproved`. With the simulator enabled, the stale type postcondition (`pc_002`) still causes `postcondition_failed` and compensation. Updating it to inspect the renamed field lets the change pass reconciliation and finalize as `applied`.

## Verification
- SEC-004 adapter: 5 passed. Gateway: 57 passed. Docker unit discovery: 37 passed, 10 skipped. BPL-027: 5 passed, 9 skipped. BPL-012 and ERP-012: 15 passed. SQLite and simulated Frappe conformance: 208 passed each. Script tests: 22 passed.
- All 20 tracked YAML files parsed. Docs, repository hygiene, secret scan, plan independence, lane, and conflict-marker checks passed.

## Tokens or cost
Unknown or approximate, if known.

## Next step
Review PR #131 and its CI results for SEC-004.
