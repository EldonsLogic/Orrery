# Session log: erp-012-frappe-engine-adapter

Date: 2026-11-17
Author: partner
Tool and model: antigravity gemini-4-hydrogen
Plan IDs: ERP-012

## Summary
Implemented FrappeRuntimeBackend (`apps/engine/change_engine/change_engine/adapter/frappe_backend.py`) and wired `ChangeEngineAdapter` to real Frappe Framework / MariaDB operations (site-isolated provisioning with ADR-0033 / E0-7 safe defaults, guarded Custom Field DDL gate + Property Setter non-destructive quarantine/restore, workflow & report deployment, non-PII shadow `User` sync, T36 caller impersonation, MariaDB advisory lock + stale PREPARED health checks, and fail-closed acquisition when `frappe` is absent), verified against both an in-process Frappe/MariaDB simulator (208/208 BPL-025 conformance + unit tests) and the live dev bench (`erp001.localhost`).

## Files touched
- `apps/engine/change_engine/change_engine/adapter/frappe_backend.py`: Added `FrappeRuntimeBackend`, `FrappeSiteResolver`, `FrappeBackendError`, and shadow user helpers (`shadow_user_email`, `shadow_user_label`).
- `apps/engine/change_engine/change_engine/adapter/simulated_frappe.py`: Added `SimulatedFrappeRuntime` for offline unit tests and CI conformance verification of real Frappe/MariaDB code paths.
- `apps/engine/change_engine/change_engine/adapter/engine.py`: Wired `frappe_backend` into provisioning, health checks, plan inspection, live step execution, compensation error handling, member sync, probes, and T36 `execute_as_caller`.
- `apps/engine/change_engine/change_engine/adapter/harness.py`: Preserved `frappe_backend` in `without_test_hooks` and added `make_frappe_adapter` and `make_frappe_harness`.
- `apps/engine/change_engine/change_engine/adapter/__init__.py`: Exported `FrappeRuntimeBackend`, `FrappeSiteResolver`, `FrappeBackendError`, `SimulatedFrappeRuntime`, `make_frappe_adapter`, and `make_frappe_harness`.
- `apps/engine/change_engine/change_engine/tests/test_erp_012_frappe_adapter.py`: Added unit tests covering fail-closed absence of `frappe`, safe provisioning defaults, guarded field add/quarantine/restore, decimal `Custom Field` DDL, workflow & report deployment, shadow user sync & T36 impersonation, multi-tenant isolation, and stale `PREPARED` health reporting.
- `.github/workflows/ci.yml`: Updated `engine-adapter-conformance` job to install `pydantic>=2`, run `test_erp_012_frappe_adapter.py`, and execute the BPL-025 conformance suite under `make_frappe_harness`.
- `docs/PLAN.md`: Marked `ERP-012` as `done`.

## Decisions
- Kept `ddl_plan_gate.py`, `schema_reconciler.py`, and `api/endpoints.py` unmodified to avoid merge conflicts with PR #96 (`BPL-007`), handling decimal DDL additive gate (`_DECIMAL_ADD_RE`) and `WORKFLOW` direct-to-cancelled `doc_status=0` transitions in `FrappeRuntimeBackend`.
- Enforced fail-closed behavior (`engine_unavailable`) when `frappe` is absent unless `simulated=True` or an explicit `frappe_factory` is supplied.

## Tokens or cost
Unknown.

## Next step
Pick up `BPL-008` once PR #96 (`BPL-007`) merges, or proceed with `ERP-007`, `ERP-002`, `SEC-004`, or `CE-SEC-005` in the `partner` G1 lane.
