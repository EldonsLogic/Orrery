# Session log: ce-sec-005-real-bench-ci

Date: 2026-11-18
Author: partner
Tool and model: antigravity
Plan IDs: CE-SEC-005

## Summary
Implemented `CE-SEC-005` real-bench CI orchestration, a zero-mock Frappe/ERPNext/HRMS/MariaDB integration & negative security regression suite, and a `GOV-049` path-filtered GitHub Actions workflow, plus fixed live-schema inspection in `inspect_field_ddl`.

## Files touched
- `.github/workflows/real-bench.yml`: Added path-filtered (`GOV-049`) + `workflow_dispatch` CI workflow with `cancel-in-progress: true` running `python3 infra/dev/docker/run_real_bench_ci.py`.
- `infra/dev/docker/run_real_bench_ci.py`: Added orchestrator to boot the pinned Compose stack (`Frappe v15.126.0`, `ERPNext v15.124.5`, `HRMS v15.64.8`, `MariaDB 11.4`, `Redis 7.2.7`), provision a synthetic `.localhost` site, run `verify_dev_bench.py` and `test_ce_sec_005_real_bench.py`, and always tear down the stack.
- `apps/engine/change_engine/change_engine/tests/test_ce_sec_005_real_bench.py`: Added 6 zero-mock live-bench tests covering pinned versions/services, DDL gate & zone guardrails, real apply/idempotency/soft-quarantine rollback, `ChangeEngineAdapter` + `FrappeRuntimeBackend`, persisted runtime policies & `hooks.py` enforcement, and `CE-SEC-001`..`CE-SEC-004` negative security regressions.
- `apps/engine/change_engine/change_engine/adapter/mapping.py`: Fixed `inspect_field_ddl` to pass `existing_columns_desc=None` so live Frappe `MariaDBTable` reflects real DB columns instead of comparing DocType fields against `STANDARD_COLUMNS` alone.
- `infra/dev/docker/tests/test_ce_sec_005_real_bench_ci.py`: Added offline contract and fail-closed tests for the suite, orchestrator, and workflow.
- `docs/PLAN.md`, `docs/architecture/change-engine.md`, `apps/engine/change_engine/README.md`: Marked `CE-SEC-005` done and documented real-bench CI execution.

## Decisions
- Kept `.github/workflows/ci.yml` untouched and placed the heavy bench run in `.github/workflows/real-bench.yml` filtered to engine/bench/component paths (`GOV-049`), while keeping `test_ce_sec_005_real_bench.py` fail-closed under `CE_SEC_005_REAL_BENCH=1` and cleanly skipping offline.

## Tokens or cost
Unknown.

## Next step
Review and merge the `CE-SEC-005` PR, then pick up the next `partner` lane item (`SEC-002` or `ERP-001` / `ERP-003` depending on lane order).
