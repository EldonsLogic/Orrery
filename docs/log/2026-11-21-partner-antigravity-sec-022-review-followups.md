# Session log: sec-022-review-followups

Date: 2026-11-21
Author: partner
Tool and model: antigravity (Gemini 4 Argon)
Plan IDs: SEC-022,BPL-032

## Summary
Resolved all six Low review findings from Eldon's approving cross-model review of PR #235 (`e5b262e`): enabled live BPL-027 security read-backs (`test_04`, `test_04b`, `test_06`, `test_07`, `test_08`) on the mapped fixture while `BPL027_PURCHASING_MAPPED` is unset, separated `route_guard.RESOURCE_ALLOWLIST` into an explicit reviewed read-route set (`Customer`, `Item`, `Sales Order`, `Sales Invoice`) without `Delivery Note`, documented embedded child rows in single-record GETs as an accepted residual in ADR-0051, made plan-time `own_allowed` fail closed (`False`) when a backend lacks `can_grant_own_doctype`, switched all `_SAFE_SQL_IDENT_RE` checks to `fullmatch`, and verified the full BPL-027 live suite on a throwaway Docker bench. Tier 3 (auth).

## Files touched
- `apps/engine/change_engine/change_engine/tests/test_bpl_027_fixture_real_adapter.py`: when `BPL027_PURCHASING_MAPPED` is unset, `TestBpl027FixtureRealAdapter` uses `without_unmapped_builtin_grants(bp_full)` as its active fixture while `test_01b` still verifies `plan` rejects the unmapped built-ins on `art_full`; added `test_03b_apply_mapped_fixture_through_real_adapter` (skipped when `BPL027_PURCHASING_MAPPED=1`) so `test_04`, `test_04b`, `test_06`, `test_07` and `test_08` run live now while keeping `test_01b`, `test_02` and `test_03` gated as they are.
- `apps/engine/change_engine/change_engine/api/route_guard.py`: defined `READ_ROUTE_DOCTYPES = ("Customer", "Item", "Sales Order", "Sales Invoice")` for `RESOURCE_ALLOWLIST`, removing `"Delivery Note"` (which has no read consumer).
- `apps/engine/change_engine/change_engine/tests/test_erp_020_route_guard.py`: asserted `"Delivery Note"` and `"Delivery Note Item"` are refused on `/api/resource/*`, and replaced the equality drift check with a subset drift check asserting `RESOURCE_ALLOWLIST` equals `{"Customer", "Item", "Sales Order", "Sales Invoice"}`, is a subset of mapped non-locked non-child doctypes, and never contains a locked doctype or `Session`.
- `infra/dev/docker/HEADLESS.md`: updated the Layer 2 route table to name the explicit `READ_ROUTE_DOCTYPES` set (`Customer`, `Item`, `Sales Order`, `Sales Invoice`) and note that mapped grant entities without a read consumer (`Delivery Note`) are denied.
- `docs/decisions/ADR-0051-adapter-role-and-state-namespacing.md`: appended the accepted residual under `## Consequences` that a single-record `GET /api/resource/<DocType>/<name>` returns embedded child rows (lines, taxes), and aligned the grant-target allowlist and BPL-027 live bench bullets with the explicit read-route set and `test_03b`.
- `apps/engine/change_engine/change_engine/adapter/engine.py`: changed `own_allowed` in `_evaluate` to default to `False` (refusing with `protected_subject`) when `self.frappe_backend` is absent or lacks a callable `can_grant_own_doctype`.
- `apps/engine/change_engine/change_engine/adapter/frappe_backend.py`: replaced `_SAFE_SQL_IDENT_RE.match(doctype)` with `_SAFE_SQL_IDENT_RE.fullmatch(doctype)` in `can_grant_own_doctype`, `_grant_doctype` and `data_probe`.
- `apps/engine/change_engine/change_engine/tests/test_sec_022_bpl_032_roles.py`: added `test_plan_fails_closed_when_backend_lacks_can_grant_own_doctype` (both `None` and a bare backend without the method) and `test_trailing_newline_in_doctype_name_is_refused_everywhere` (`"widget\n"` -> `"Widget\n"`).

## Checks
- Target unit suites (`test_sec_022_bpl_032_roles`, `test_bpl_027_fixture_real_adapter` offline, `test_erp_012_frappe_adapter`, `test_bpl_012_engine_adapter`, `test_bpl_008_blueprint_rollback`, `test_erp_021_phase0_proofs`, `test_erp_023_action_policy`, `test_erp_020_route_guard`, `test_erp_020_wsgi_guard`): before `221 passed, 10 skipped, 530 subtests passed`; after `223 passed, 11 skipped, 532 subtests passed`.
- Conformance harnesses: `make_harness` `208 passed`; `make_frappe_harness` (`CHANGE_ENGINE_ENV=test`) `208 passed`.
- CE-SEC mocks (`test_caller_roles`, `test_ce_sec_003_security`, `test_ce_sec_003_policy_persistence`, `test_api_deployment`, `test_ce_sec_007_live_suite_opt_in`): `61 passed, 60 subtests passed`.
- Script tests (`scripts/tests`): `22 passed, 29 subtests passed`.
- Live Docker bench (`TestBpl027FixtureRealAdapter` + `TestBpl027Offline` on throwaway Compose project `sec022-followups-bpl027-305d01` on `127.0.0.1:56067`, MariaDB not published, torn down with `down -v --remove-orphans`): waited for `entrypoint.sh` to finish populating `sites/apps.txt` and starting `gunicorn` on port `8000` (matching `run_real_bench_ci.py:_wait_for_engine_ready`; running `bench new-site` before step 3 of `entrypoint.sh` finishes causes `--install-app hrms` to fail with `Module HR not found`), provisioned `bpl027.localhost` with `erpnext`, `hrms`, `change_engine`, set `tenant_id=t_bpl027`, and ran `unittest -v change_engine.tests.test_bpl_027_fixture_real_adapter`: `Ran 20 tests in 58.126s — OK (skipped=3, expected failures=1)`. Live `test_01`, `test_01b`, `test_03b`, `test_04`, `test_04b`, `test_06`, `test_07` and `test_08` all passed; `test_02` and `test_03` skipped as gated on `BPL027_PURCHASING_MAPPED=1`; `test_05` remained the expected failure for BPL-027 finding 2.
- Repo gates: `check_docs.py`, `check_repo_hygiene.py`, `scan_secrets.py`, `check_plan_independence.py`, and `check_lanes.py --base origin/main --actor partner` all passed.

## Decisions
- Updated [ADR-0051](../decisions/ADR-0051-adapter-role-and-state-namespacing.md) (Proposed) to record single-record GET child rows as an accepted residual under `## Consequences` and align the read-route and BPL-027 live test notes.

## Tokens or cost
Unknown.

## Next step
- Cross-model review and Eldon's Tier 3 review of this follow-up PR.
- Once `BPL-034` (#247) merges and the purchasing/price-list entities are added to `ENTITY_TO_DOCTYPE`, ungate `test_02` and `test_03` and remove the temporary `BPL027_PURCHASING_MAPPED` gate.
