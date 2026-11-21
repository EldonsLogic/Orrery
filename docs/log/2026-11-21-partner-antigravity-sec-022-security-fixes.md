# Session log: sec-022-security-fixes

Date: 2026-11-21
Author: partner
Tool and model: antigravity (Gemini 4 Neon)
Plan IDs: SEC-022,BPL-032

## Summary
Continued the interrupted Claude Opus review-fix run (WIP commit `391e18b` on `work/sec-022-fixes`, also on `rescue/sec-022-role-namespacing-r2`), merged `origin/main` cleanly, audited and hardened all 8 findings from Eldon's and Gemini 4 Hydrogen's security reviews of PR #235 (`0875ae1`), verified tests-first failures against `0875ae1`, ran live bench tests and masked-field/shadow-user probes on the pinned engine, and pushed to `sec-022-role-namespacing`.

## Files touched
- `apps/engine/change_engine/change_engine/adapter/mapping.py`: `ADAPTER_DOCTYPE_MODULE`, `reviewed_grant_doctype`, and `grant_plan_reason` (plan-time allowlist check, refusing non-list `permissions` as `unsupported_value_type` and any target outside `ENTITY_TO_DOCTYPE` minus protected or Blueprint-owned entities as `protected_subject`).
- `apps/engine/change_engine/change_engine/adapter/engine.py`: passes `blueprint_entities` into `_judge` and enforces `grant_plan_reason` on `role.upsert` at plan time.
- `apps/engine/change_engine/change_engine/adapter/frappe_backend.py`:
  - `role.upsert` requires `definition.id`, `subject.id`, and pointer segment `/roles/<id>` to agree (`definition_conflict`).
  - `_grant_doctype` replaces the grant denylist with an allowlist (`ENTITY_TO_DOCTYPE` minus protected, plus adapter-created `custom=1` DocTypes in `Custom` under exact name).
  - `_plan_rules` refuses with `protected_subject` if any foreign role rule or any field not placed by the adapter (matching `custom_*` + `Property Setter` `permlevel` with matching level value) sits on an owned permlevel.
  - `_deploy_report` validates `visibleToRoles` (non-empty list of valid, non-colliding managed roles) before `_ensure_doctype_exists`; empty/missing `visibleToRoles` is refused (`unsupported_value_type`), never falling back to `"All"`.
  - `_deploy_workflow` requires non-empty `allowedRoles` on every transition (`unsupported_value_type`) and indexes `role[r]` strictly.
- `apps/engine/change_engine/change_engine/guarded_apply/workflow_engine.py`: `find_workflow_state_collisions` propagates lookup errors and raises `RuntimeError` if no lookup is available (fail closed).
- `apps/engine/change_engine/change_engine/api/endpoints.py`: `FrappeDeploymentAdapter.get_workflow_state` propagates DB errors and raises `RuntimeError` when `db.get_value` is absent.
- `apps/engine/change_engine/change_engine/tests/ci_engine_fake.py`: seeds built-in engine DocTypes (`custom=0`, including `Session`) and adds `add_doctype`.
- `apps/engine/change_engine/change_engine/tests/test_sec_022_bpl_032_roles.py`: adds `TestSec022GrantAllowlist` (all 12 refused targets at apply and plan time), foreign-field probe (`secret_rate` and `custom_secret_rate`), `TestSec022StepInputs` (id agreement, report validate-before-create and empty roles, workflow empty/invalid `allowedRoles`), and `TestSec022LookupErrorsFailClosed`.
- `apps/engine/change_engine/change_engine/tests/test_bpl_027_fixture_real_adapter.py`: adds `test_06c_offline_literal_grants_and_untouched_engine_rules` and `test_06d_offline_grant_on_an_unreviewed_engine_document_type_is_refused`; removes stale `System Manager`/`All` fallbacks in `expected_engine_config`; keeps `@unittest.expectedFailure` on live `test_04b` and `test_06` because the allowlist refuses the fixture's unreviewed built-in ERPNext DocTypes (`Supplier`, `Price List`, `Delivery Note`, `Purchase Order`, `Purchase Receipt`, `Purchase Invoice`) in `test_03`.
- `docs/decisions/ADR-0051-adapter-role-and-state-namespacing.md`: documents the grant allowlist, owned-permlevel drift refusal, report/workflow fail-closed validation, migration statement (item 6), and live bench probe evidence (item 5).

## Follow-up rows audit (not added here)
Checked `docs/PLAN.md` for the three follow-up items named by the reviews:
- **Location-scoped permissions:** covered by `ERP-008` ("Blueprint roles to engine roles and user permissions mapping", `doing`) and ADR-0039 item 4.
- **Managed-name registry and drift check:** detailed in ADR-0039 item 9 (`ERP-008`), though not spelled out explicitly in the one-line `ERP-008` or `BPL-033` row text in `docs/PLAN.md`.
- **Journaled rule compensation:** detailed in ADR-0039 item 8 (`ERP-008`), while `BPL-033` mentions general step journaling in `adapter/engine.py` ("journal written before a step takes effect"), not specifically per-rule compensation. No rows were added in this PR.

## Verification
- **Tests-first (against scratch copy of pre-fix `0875ae1`):** 10 failures across items 1, 2, 3, 4, 5, 7, 8 (allowlist apply/plan tests, foreign field on owned permlevel for `secret_rate` and `custom_secret_rate`, report DocType creation before refusal and empty `visibleToRoles`, workflow empty `allowedRoles`, id-agreement mismatch, and workflow-state lookup error/missing-lookup fail-closed checks).
- **Live bench (`sec022fix-r1` throwaway Compose project on pinned engine + MariaDB 11.4, torn down with `down -v`):**
  - `TestBpl027FixtureRealAdapter`: `test_01` and `test_02` passed; `test_03` failed (`compensated`, step 64 `protected_subject`) because the trading fixture grants roles on built-in ERPNext DocTypes outside `ENTITY_TO_DOCTYPE` (`Supplier`, etc.); `test_04..test_08` skipped. Accordingly, `test_04b` and `test_06` stay flagged `@unittest.expectedFailure`.
  - Masked-field and shadow-user runtime probe (synthetic data on `Probe Widget` `custom=1` and built-in `Customer`): verified all 12 unallowed doctypes refused live (`protected_subject`, `side_effect_free=True`); `setup_custom_perms` preserved all 24 standard `Customer` rules; `Custom DocPerm` defaults (`select=0`, `report=0`, `print=0`, `export=0`); `permlevel` Property Setters moved `custom_cost` -> 1, `custom_note` -> 2, and `custom_margin_probe` on `Customer` -> 2 (skipping built-in `Sales User` level 1, leaving `Sales User` rules unchanged, returning to level 0 on unhide); `sync_members` shadow users enforced `has_permission`, `apply_fieldlevel_read_permissions()`, `get_list`, `if_owner=1` across levels 0..2, and `PermissionError` on masked write; foreign field on owned permlevel refused live (`protected_subject`).
- **Offline suites:** BPL-027 offline 9 passed / 9 skipped; SEC-022/BPL-032 44 passed (2 subtests); BPL-012/ERP-012 15 passed; BPL-008 6 passed; ERP-021 7 OK; ERP-023 73 passed; ERP-020 39 OK; CE-SEC mocks 61 passed (60 subtests); phase3_workflow 11 OK; `scripts/tests` 22 passed (29 subtests); conformance `make_harness` 208 passed; conformance `make_frappe_harness` 208 passed; `check_docs`, `check_repo_hygiene`, `scan_secrets`, `check_plan_independence`, and `check_lanes --actor partner` all clean.

## Decisions
- Updated Proposed [ADR-0051](../decisions/ADR-0051-adapter-role-and-state-namespacing.md) with review round 1 security fixes, migration policy, and live bench evidence.

## Tokens or cost
Unknown.

## Next step
- Cross-model re-review and Eldon's line-by-line review of PR #235 (`SEC-022`, `BPL-032`).
- Founder decision on adding the remaining trading-fixture built-in DocTypes (`Supplier`, `Price List`, `Delivery Note`, `Purchase Order`, `Purchase Receipt`, `Purchase Invoice`) to `ENTITY_TO_DOCTYPE` (and `route_guard.py`) so `TestBpl027FixtureRealAdapter` can complete end-to-end on the real bench (`BPL-027`, `BPL-033`).

## Round 2 (Opus review fixes)
Merged `origin/main` (`f7f6998`, past `99f3ca8`) cleanly with `git merge --no-ff origin/main`. Implemented tests-first fixes for all 5 findings from the Opus review (`#235` comment `7068128626`) and Eldon's decision (`#235` comment `7068164805`):

1. **Delivery Note in reviewed mapping and route allowlist:** Added `"delivery_note": "Delivery Note"` and `"delivery_note_line": "Delivery Note Item"` to `ENTITY_TO_DOCTYPE` in `adapter/mapping.py` (matching `contracts/examples/engine-mapping-golden-path.json:261,298`). Per the `ERP-020` drift guard (`test_erp_020_route_guard.py`), added `"Delivery Note"` (`GET`-only) to `api/route_guard.py:RESOURCE_ALLOWLIST` (Tier 3 route-exposure change for Eldon's review) and `"Delivery Note Item"` to the child-table exclusion set in `test_erp_020_route_guard.py`. Left `Supplier`, `Price List`, and purchase DocTypes unmapped pending `BPL-034`.
2. **Plan time agrees with apply time:** Updated `mapping.py:grant_plan_reason`, `engine.py:_evaluate`/`_judge`, and `frappe_backend.py:can_grant_own_doctype` so `plan` checks unmapped Blueprint entities against the engine's `DocType` metadata (and `table_exists`). Entities whose derived DocType already exists as a non-adapter type (`custom=0` or wrong module, e.g. `Supplier`, `Price List`, `Purchase Order/Receipt/Invoice`) are refused at plan time with `protected_subject` before any write, even when declared in `entity.add` of the same Blueprint. `delivery_note` and Blueprint-created custom entities remain allowed.
3. **Honest flags and ADR-0051 wording:** Updated `docs/decisions/ADR-0051-adapter-role-and-state-namespacing.md` (noting `test_04b` and `test_06` were unflagged at `0875ae1` and skip via `need("applied")` when `test_03` does not run). Removed the inert `@unittest.expectedFailure` decorators from `test_04b` and `test_06`. Added explicit `@unittest.skipUnless(os.environ.get("BPL027_PURCHASING_MAPPED") == "1", ...)` flags to `test_02` and `test_03` naming plan row `BPL-034` ("purchasing and price-list engine mapping", owned by `eldon`, PR #235) covering `Supplier`, `Price List`, and `Purchase Order/Receipt/Invoice` — using `skipUnless` rather than `expectedFailure` so live runs will not fail with "unexpected success" once `BPL-034` lands. Added `test_01b_plan_refuses_unmapped_builtins_and_allows_delivery_note` to exercise live plan refusal/allowance on the bench. Unflagging `test_03` (and `test_02`) and adding those five entities to the allowlist is a partner follow-up after `BPL-034` merges.
4. **Seeded `tests/ci_engine_fake.py` and updated `test_06c`:** Added `Supplier`, `Delivery Note`, `Price List`, `Purchase Order`, `Purchase Receipt`, and `Purchase Invoice` as `custom=0` in `ENGINE_DOCTYPES`.
   - `test_06c` (plus `_apply_fixture_offline` for `test_04b_offline` and `test_06_offline`): Because seeding makes `Supplier`, `Price List`, and the three purchase DocTypes fail closed as `custom=0` built-ins (just like the real engine), added `without_unmapped_builtin_grants(bp)` to strip only those five `BPL-034` entity grants for the offline mapped-grant read-back tests, and added literal `test_06c` assertions for `Delivery Note` (`bp-owner`: `read, export`; `bp-accountant`: `read, export`; `bp-sales_rep`: `read`, `if_owner=1`) plus assertions that all six seeded DocTypes remain `custom=0` with zero `bp-*` rules on the five unmapped ones.
   - `test_06d`: Removed the manual `add_doctype("Supplier", ...)` setup (now seeded by `CaseInsensitiveEngine`) and added plan-time checks on the compiled trading fixture (`8` `role.upsert` steps blocked with `protected_subject`, no writes) and on `without_unmapped_builtin_grants(bp)` (`needs_gate_approval`).
5. **Drift does not block revocation:** Updated `frappe_backend.py:_disable_role` and `_plan_rules(..., revoking=True)` so `role.disable` clears the role's rules and disables the role even when a foreign field or role rule sits on an owned permlevel, without ever adopting or moving the foreign field (`layout` includes only adapter-placed `custom_` fields with matching `Property Setter`, `reserved` includes `drifted` levels, `held` excludes `reserved`, and an exhausted free-level fallback clears only `role_name`'s rules with `setters=[]`). Grant and `role.upsert` paths keep refusing drift. Added `test_erpnext_upgrade_drift_on_owned_level_does_not_block_revocation` (both `keep_other_hider=False` and `True`).

### Round 2 Verification
- **Tests-first (before production edits):** 8 failures in `test_bpl_027_fixture_real_adapter.py` + `test_sec_022_bpl_032_roles.py` across items 1, 2, 4, and 5 (`test_04b_offline`, `test_06_offline`, `test_06c`, `test_06d`, `test_delivery_note_is_in_reviewed_mapping_and_granted_at_plan_and_apply`, `test_plan_time_agrees_with_apply_time_for_unmapped_builtin_entities`, and `test_erpnext_upgrade_drift_on_owned_level_does_not_block_revocation` subtests `False`/`True`).
- **Offline suites (after edits):**
  - BPL-027 offline + SEC-022/BPL-032: 56 passed, 10 skipped, 4 subtests passed.
  - BPL-012 / ERP-012 / BPL-008 / ERP-023: 94 passed.
  - ERP-021 + ERP-020 (`test_erp_021_phase0_proofs`, `test_erp_020_route_guard`, `test_erp_020_wsgi_guard`): 71 OK.
  - CE-SEC mocks: 61 passed, 60 subtests passed.
  - Conformance `make_harness`: 208 passed; conformance `make_frappe_harness`: 208 passed.
  - `scripts/tests`: 22 passed, 29 subtests passed.
  - `check_docs`, `check_repo_hygiene`, `scan_secrets`, `check_plan_independence`, `check_lanes --actor partner`: all clean.
- **Live check:** Not run (the throwaway `sec022fix-r2-bpl027` Compose bench failed during `bench new-site --install-app hrms` with `frappe.exceptions.DoesNotExistError: Module HR not found`, unrelated to this PR, and was torn down cleanly with `down -v`).

## Round 2 review Lows (coordinator, Claude Opus 5.5)
An Opus review of 68cba80 approved round 2 with four Lows:
- **Fixed, low 1:** removed the duplicate `test_erpnext_upgrade_drift_on_owned_level_does_not_block_revocation` from `test_sec_022_bpl_032_roles.py`. The bodies were identical, so no coverage is lost.
- **Fixed, low 2:** the BPL-034 skip reasons and ADR-0051 now cite contract PR #247 instead of #235.
- **Fixed, low 3:** `test_01b` gets an inverse `skipIf(BPL027_PURCHASING_MAPPED == "1")`, so the BPL-034 follow-up must invert or remove it rather than see it fail.
- **Accepted, low 4:** at plan time, an entity whose DocType was deleted by hand counts as "own". The apply then refuses with `protected_subject` and compensates, so it fails closed.
