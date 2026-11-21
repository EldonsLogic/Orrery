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
