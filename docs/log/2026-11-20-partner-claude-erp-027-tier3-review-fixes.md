# Session log: erp-027-tier3-review-fixes

Date: 2026-11-20
Author: partner
Tool and model: Claude Sonnet 5.5 (Claude Code)
Plan IDs: ERP-027

## Summary
Fixed Eldon's Tier 3 review findings on PR #125. MED 1: the offline DDL simulator is now an explicit `FrappeRuntimeBackend(offline_ddl_simulator=...)` flag (default False, never inferred from a factory) and the constructor raises `offline_ddl_simulator_forbidden` unless `CHANGE_ENGINE_ENV` is `dev` or `test` (unset counts as production). MED 2: the Property Setter engine returns the `REVISION_HASH_UNAVAILABLE` rejection (like the other two callers) when the revision hash cannot be read, and the `rev_ps_default` stand-in is only used by an adapter that is explicitly in-memory or offline. LOW 3: a new test pins the exact statement-verb allowlist of `requires_ddl_check`.

## Files touched
- apps/engine/change_engine/change_engine/adapter/frappe_backend.py: explicit flag, environment guard, `_deployment_adapter` uses the flag.
- apps/engine/change_engine/change_engine/adapter/harness.py: `make_frappe_adapter` passes the flag for `simulated=True` only.
- apps/engine/change_engine/change_engine/guarded_apply/property_setter_engine.py, schema_reconciler.py, api/endpoints.py: rejection on `RevisionHashError`; `RevisionHashError` moved to schema_reconciler (shared, avoids an import cycle) and still importable from endpoints.
- apps/engine/change_engine/change_engine/tests/test_erp_027_review_fixes.py: new regression tests (factory defaults to False, production and unset env refuse True, harness opt-in, revision-hash rejection, verb allowlist).
- apps/engine/change_engine/change_engine/tests/test_erp_012_frappe_adapter.py, test_bpl_008_blueprint_rollback.py: simulator tests opt in explicitly and set `CHANGE_ENGINE_ENV=test` for the module.
- .github/workflows/tests.yml (shared path, all existing steps kept): new test file added to the ERP-027 step; `CHANGE_ENGINE_ENV: test` on the Frappe simulated conformance step.
- docs/log/2026-11-20-partner-claude-erp-027-tier3-review-fixes.md: this log.

## Decisions
- `CHANGE_ENGINE_ENV` does not exist elsewhere in the repo yet (ERP-026 is still `todo`), so this PR introduces the name and the dev/test allowlist; ERP-026 should reuse it.
- Verb allowlist test: the pinned benign set is the list that the `real-bench-tests` job passes with; the bench does not log the verbs it saw, so the test pins the code's list, not a captured trace. UNVERIFIED that no other benign verb is issued on other Frappe versions.
- Local runs: 291 engine tests and 208 conformance tests (simulated harness) pass; the live MariaDB and real-bench suites were not run locally, that proof is the `real-bench-tests` check on the PR head.
- Plan row stays `doing` until the real-bench check is green on the final head.

## Tokens or cost
Unknown.

## Next step
Eldon: Tier 3 line-by-line review of `ddl_plan_gate.py` and the `frappe_backend.py` apply path, then merge once `python-tests` and `real-bench-tests` are green on the new head. Then set ERP-027 `done`.
