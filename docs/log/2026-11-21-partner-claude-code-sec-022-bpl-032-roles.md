# Session log: sec-022-bpl-032-roles

Date: 2026-11-21
Author: partner
Tool and model: claude-code (Claude Opus 5.5)
Plan IDs: SEC-022,BPL-032

## Summary
Resumed an interrupted session (rate limit): merged main into the claimed branch, re-applied the rescued work (commit 4d32a3c on `rescue/sec-022-role-namespacing`), reviewed and fixed it, wrote ADR-0051 (Proposed), and landed SEC-022 (adapter-owned `bp-` role and workflow-state names, case-insensitive collisions refused before any write) and BPL-032 (role.upsert writes the mapped permission rules and field levels) as two commits. Tier 3 (auth).

## Files touched
- `docs/decisions/ADR-0051-adapter-role-and-state-namespacing.md`, `docs/decisions/INDEX.md`: new Proposed ADR.
- `apps/engine/change_engine/change_engine/adapter/mapping.py`: `engine_role_name`, `engine_state_name` (prefix `bp-`, Blueprint id grammar only), `rule_flags` (action table).
- `apps/engine/change_engine/change_engine/adapter/frappe_backend.py` (role, state and report-role functions only): `_managed_role` collision check; `role.upsert`, `role.disable`, `workflow.upsert`, `report.upsert` and `sync_members` use managed names; `_role_grants`, `_plan_rules`, `_write_rules` reconcile `Custom DocPerm` rules and field levels.
- `apps/engine/change_engine/change_engine/guarded_apply/workflow_engine.py`: second state-collision gate before lock and journal.
- Tests: new `tests/ci_engine_fake.py` (simulated engine with case-insensitive names, built-ins and standard rules) and `tests/test_sec_022_bpl_032_roles.py` (33 tests); `test_bpl_027_fixture_real_adapter.py` (test_04b and test_06 tightened, expectedFailure removed, offline copies added); `test_erp_012_frappe_adapter.py` (T36 test seeds the managed role's read on its simulator) and `test_bpl_008_blueprint_rollback.py` (expects the managed state name).
- `.github/workflows/tests.yml`: wires `test_sec_022_bpl_032_roles.py`.

## Review of the rescued work (changes made)
- `workflow.upsert` created the document type before the collision check, so a refusal marked side-effect free could leave a write; all names (states, transition endpoints, roles) are now checked first. New test.
- The state pre-check went through a lookup that swallows engine errors (read as "no collision"); it now reads the engine directly so a failed read raises.
- The rescued work broke ERP-012 T36 and BPL-008 test_02 (raw role and state names); fixed in the tests only, with the reason in a comment.

## Checks
- Offline (CHANGE_ENGINE_ENV unset): BPL-027 7 passed, 9 skipped (main: 5 passed, 9 skipped); SEC-022/BPL-032 33 passed; BPL-012/ERP-012 15 passed; ERP-021 7 OK; ERP-023 73 passed; BPL-008 6 passed; ERP-026 30 passed, 36 skipped; CE-SEC mocks (caller roles, CE-SEC-003, API deployment) 59 passed; SEC-004 5 passed; ERP-009 25 passed; ERP-020, ERP-003, ERP-007, CMP-006, phase 2 to 4 OK; conformance 208 passed on `make_harness` and 208 on `make_frappe_harness`. Each commit was checked on its own.
- `scripts/tests` 22 passed; `check_docs`, `check_repo_hygiene`, `scan_secrets`, `check_plan_independence`, `check_lanes --actor partner` OK.
- Live bench (BPL-027 class): running on a throwaway Compose project (`sec022-bpl032-bench`, engine port 127.0.0.1:18232, MariaDB not published); result follows in this log.

## Decisions
- ADR-0051 (Proposed): reserved prefix `bp-`; collision refused with `protected_subject`; grants narrowed until the ADR-0039 bench gates pass (no report or print, masked entities read-only, location scopes withheld, unresolved hidden field withholds the entity grant).

## Residual risks (in ADR-0051 item 4)
- The prefix is the only adapter-managed mark; a role created by hand under `bp-` is treated as the adapter's until a registry and the drift fingerprint exist.
- No journaled compensation of rule changes inside one apply; rollback relies on the inverse artifact.
- Workflow states with no role-bearing outgoing transition, and transitions without `allowedRoles`, still fall back to the built-in `System Manager`; reports with no `visibleToRoles` to `All` (pre-existing).

## Tokens or cost
Unknown.

## Next step
- Security review by a different model and Eldon's line-by-line review (Tier 3) of the PR; then BPL-027 can close once its remaining bench gaps (test_05) are handled.
- ADR-0039 follow-ups: user-permission scoping for location scopes, drift fingerprint, plan-time rejection of unresolved hidden fields (DENY-07), managed-name registry in the durable adapter state.
