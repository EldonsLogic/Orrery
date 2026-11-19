# Session log: ce-sec-002-fail-closed-fix

Date: 2026-11-18
Author: partner
Tool and model: claude-code / opus-5.5
Plan IDs: CE-SEC-002

## Summary
Closed two fail-open holes left in the merged CE-SEC-002 fix (role lookup must fail closed), found by the cross-model review of PR #134. The merged security fix had a hole: two code paths could still grant roles the caller does not hold.

## The holes
1. `guarded_apply/rollback_engine.py` `execute_rollback`: when called with `caller_roles=None` and the Frappe role lookup raised (or there was no Frappe), it fell back to `["System Manager"]`.
2. `api/endpoints.py` `_resolve_caller_roles`: it decided "inside Frappe" by `frappe.session.user` only. In a Frappe site context with no session user it fell through to the caller-supplied `user_roles` / `caller_roles`.

## Reachability (evidence)
- Not reachable over the HTTP RPC surface as shipped. `revert_configuration_change`, the only caller of `execute_rollback`, always passes a list. Frappe always sets a session user on HTTP requests (Guest at minimum), and Guest cannot call these non-`allow_guest` methods. Proven on a live pinned bench: the PR #134 HTTP tests (six endpoints, low-privilege API token, spoofed roles in kwargs) pass on the unfixed code.
- Reachable in process: a direct `execute_rollback(..., caller_roles=None)` during a role-lookup failure, or any engine call made from a site context with no session user. On the live bench, before the fix, these returned `DEPLOYMENT_NOT_FOUND` (authorization passed) and `['System Manager']`.
- Severity: a latent defect, not an exploitable remote bypass. It breaks the CE-SEC-002 rule, so it is fixed as a regression.

## Files touched
- `apps/engine/change_engine/change_engine/guarded_apply/rollback_engine.py`: no roles when there is no session user or the lookup fails. Never System Manager.
- `apps/engine/change_engine/change_engine/api/endpoints.py`: `_resolve_caller_roles` gates on `_in_frappe_request()` (session user or request site), so a Frappe context never honours caller-supplied roles.
- `apps/engine/change_engine/change_engine/tests/test_caller_roles.py`: 5 new tests, 4 of which failed before the fix.
- `.github/workflows/tests.yml`: runs the CE-SEC mock suites in CI. They were not run by any job on main. The step text is identical to the one in PR #134, so the two merge cleanly.

## Verified
- Failing first: 4 of the new tests failed on `origin/main`. All 11 in `test_caller_roles.py` pass after the fix.
- No regressions (Python 3.12 venv, pydantic 2): `test_ce_sec_003_security` 25 passed, `test_ce_sec_003_policy_persistence` 8, `test_api_deployment` 10, `test_phase2_property_setter` 13, `test_phase3_workflow` 11, `test_bpl_007` 5, `test_bpl_008` 6, `test_bpl_012` plus `test_erp_012` 15. Adapter conformance passed 208 with `make_harness` and 208 with `make_frappe_harness`.
- `test_phase4_report.py::test_9_cross_doc_policy_passes_submitted_linked_doc` fails the same way on unmodified `origin/main`. It is not in CI and this change did not cause it.
- Live: the PR #134 tests `test_ce_sec_005_live_http` test_06 and test_07 fail on the unfixed code and pass with this fix (pinned bench, Compose project `cesec134fix`).

## Decisions
- None. This applies the existing CE-SEC-002 rule.

## Tokens or cost
Unknown.

## Next step
Eldon reviews this PR (security, `.github/`). Merge it before PR #134, whose live tests assert the fix.
