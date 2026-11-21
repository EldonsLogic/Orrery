# Session log: erp-023-backend-runner-private

Date: 2026-11-21
Author: partner
Tool and model: opencode / DeepSeek V4.1 Flash
Plan IDs: ERP-023

## Summary
Closed the second level of the callback-runner bypass in ERP-023: 9c6a7ca made `ChangeEngineAdapter._execute_as_caller` private, but `FrappeRuntimeBackend.execute_as_caller` stayed public and was reachable as `adapter.frappe_backend.execute_as_caller(...)`. The backend method is now `_execute_as_caller` too (option (a)); the `frappe_backend` attribute stays public.

## Files touched
- `apps/engine/change_engine/change_engine/adapter/frappe_backend.py`: renamed the method to `_execute_as_caller` and noted that callers go through `ChangeEngineAdapter.execute_action`.
- `apps/engine/change_engine/change_engine/adapter/engine.py`: the one call now uses `self.frappe_backend._execute_as_caller(...)`.
- `apps/engine/change_engine/change_engine/tests/test_erp_023_action_policy.py`: regression assertion that `FrappeRuntimeBackend` has no public `execute_as_caller`; the two test fakes define `_execute_as_caller`.

## Decisions
- Option (a): make the backend runner private, keep the `frappe_backend` attribute name (hiding it is too wide a change).

## Checks
- ERP-023 suite: 73 passed (the new assertion failed before the rename: 1 failed, 72 passed).
- BPL-012/ERP-012 adapter tests: 15 passed. BPL-027 offline: 5 passed, 9 skipped.
- Adapter conformance: 208 passed for `make_harness` and 208 for `make_frappe_harness` (with `CHANGE_ENGINE_ENV=test`).
- CE-SEC mock command: 54 passed, 22 subtests. `scripts/tests`: 22 passed, 29 subtests.
- `check_docs`, `check_repo_hygiene`, `scan_secrets`, `check_plan_independence`: pass. Lane guard passes against the merge base; against the current `origin/main` tip it reports only upstream drift (PLT-016 removed control-plane files), no partner edits in the eldon lane.

## Tokens or cost
Unknown.

## Next step
Re-review PR #203 at the new head; no other ERP-023 code gap known.
