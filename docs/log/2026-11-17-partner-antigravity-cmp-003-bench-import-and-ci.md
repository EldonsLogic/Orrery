# Session log: cmp-003-bench-import-and-ci

Date: 2026-11-17
Author: partner
Tool and model: antigravity / gemini-4-hydrogen
Plan IDs: CMP-003

## Summary
Resolved the remaining CMP-003 bench-import gap, added ZATCA Phase 1 tests to CI, verified `change_engine.compliance` inside the pinned bench container, and marked CMP-003 done (ZATCA sandbox verification belongs to CMP-004 Phase 2; no tax maths changed).

## Files touched
- `apps/engine/change_engine/change_engine/compliance/__init__.py`: added `_ensure_components_on_path()` to locate `components` from `PLATFORM_COMPONENTS_ROOT`, the bench virtualenv root, cwd, or repo root when running in a bench virtualenv.
- `infra/dev/docker/docker-compose.dev.yml`: bind-mount `../../../components` read-only at `frappe-bench/components` in the `engine` container.
- `apps/engine/change_engine/change_engine/tests/test_zatca_phase1_engine.py`: added `test_bench_import_resolves_without_repo_root_on_sys_path`.
- `.github/workflows/ci.yml`: added `zatca-phase1-tests` job running `components/compliance/zatca_sa/tests` and `test_zatca_phase1_engine.py`.
- `docs/PLAN.md`: marked `CMP-003` `done`.

## Verification
- `python3 -m unittest discover -s components/compliance/zatca_sa/tests -t . -v`: 32 tests, OK.
- `python3 -m unittest apps/engine/change_engine/change_engine/tests/test_zatca_phase1_engine.py -v`: 3 tests, OK.
- `python3 -m unittest discover -s infra/dev/docker/tests -v`: 15 tests, OK (3 skipped).
- Live container check (`platform-erp001-20261111b-engine-1`): the bench virtualenv Python imported `change_engine.compliance`, generated a Phase 1 invoice (`115.00`), and decoded the TLV QR tag 4 (`BENCH_ZATCA_OK 115.00`); cleaned up the temporary `components` copy inside the container afterwards.

## Decisions
- None. `components/compliance/zatca_sa/phase1.py` and `manifest.json` (`certification.level: "tested"`) were left untouched; accountant review and `reviewedBy` under ADR-0034 remain for Phase 2 / CMP-004.

## Tokens or cost
Unknown.

## Next step
Eldon reviews the PR (touches shared `.github/workflows/ci.yml` and compliance wrapper). Next partner tasks: finish `ERP-006`, then `BPL-012`, `ERP-021`, `ERP-024`, `PLT-025`.
