# Session log: erp-009-real-bench-evstream-fix

Date: 2026-11-20
Author: partner
Tool and model: antigravity
Plan IDs: ERP-009

## Summary
Removed the hard runtime `evstream` import dependency from the change-engine record event emitter so real-bench document hooks run self-contained inside the Frappe container without `ModuleNotFoundError`, configured `tenant_id` during real-bench CI site provisioning, and isolated test DB transactions across real-bench tests.

## Files touched
- `apps/engine/change_engine/change_engine/adapter/record_events.py`: replaced runtime `_import_evstream()` calls in `record_document_event()` and `publish_pending()` with a self-contained stdlib ULID generator, Contract 4 envelope builder/validator (`_build_record_event`, `_validate_record_data`, `RecordEventError`), and non-importing sink rejection detection (`_is_event_rejection_error`).
- `apps/engine/change_engine/pyproject.toml`: removed the unneeded `jsonschema==4.26.0` runtime dependency.
- `apps/engine/change_engine/README.md`: documented the self-contained stdlib Contract 4 emitter without runtime `evstream` or `jsonschema` requirements.
- `infra/dev/docker/run_real_bench_ci.py`: set trusted `tenant_id` via `bench --site "$site" set-config tenant_id "$tenant_id"` in `_provision_site()` (matching `run_phase0_proofs.py` and `provision_tenant_site.py`).
- `apps/engine/change_engine/change_engine/tests/test_ce_sec_005_real_bench.py`: added `frappe.db.rollback()` in `RealBenchTestCase.tearDown()` so an uncommitted write from a failed test cannot trigger `ImplicitCommitError` (`engine_unavailable`) in subsequent tests.
- `apps/engine/change_engine/change_engine/tests/test_erp_009_record_events.py`: added regression tests blocking `evstream` in `sys.modules`, `sys.path`, and an isolated subprocess (`sys.meta_path` blocker) verifying hooks, outbox capture, and publishing work without `ModuleNotFoundError` and validate cleanly against `evstream.validate_event`.
- `infra/dev/docker/tests/test_ce_sec_005_real_bench_ci.py`: asserted `_provision_site()` configures `tenant_id`.

## Verification
- `PYTHONPATH=apps/engine/change_engine pytest apps/engine/change_engine/change_engine/tests/test_erp_009_record_events.py`: 24 passed.
- `python3 -m unittest discover -s infra/dev/docker/tests`: 26 tests ran (23 passed, 3 live-bench-only skipped).
- Offline change-engine unit suites (`test_ai_control_plane`, `test_api_deployment`, `test_phase2_property_setter`, `test_phase3_workflow`, `test_phase4_report`, `test_policy_enforcer`, `test_caller_roles`): 79 passed.
- `services/blueprint/tests/events`: 87 passed.
- `check_docs.py`, `check_repo_hygiene.py`, `check_lanes.py --base origin/main`, `scan_secrets.py`, `check_plan_independence.py`: all green.
- Not verified locally: live Docker `real-bench-tests` workflow (will run in GitHub Actions on push).

## Decisions
- None.

## Tokens or cost
Not measured.

## Next step
Wait for `real-bench-tests` CI and Eldon review on PR #162 (`ERP-009`).
