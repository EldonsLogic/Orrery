# Session log: erp-021-engine-proof-suite

Date: 2026-11-17
Author: partner
Tool and model: antigravity / gemini-4-hydrogen
Plan IDs: ERP-021

## Summary
Implemented the `ERP-021` Phase 0 Engine Proof Suite (`E0-1`..`E0-7`), executed all proofs end-to-end against two ephemeral synthetic tenant sites on the live pinned bench (`platform-erp001-20261111b`), recorded seven concrete engine findings in the proof report, added offline CI tests, and marked `ERP-021` `done`.

## Files touched
- `apps/engine/change_engine/change_engine/proofs/__init__.py`, `apps/engine/change_engine/change_engine/proofs/phase0_bench_proof.py`: Phase 0 proof runner covering `E0-1` (two-tenant MariaDB/ORM/HTTP/adapter isolation), `E0-2` (Golden Path trading sale + `ADR-0033` + `Q-23` immutable ledger cancel + gross/net Trial Balance reconciliation), `E0-3` (role denials, `Item.valuation_rate` `permlevel` masking, `CE-SEC-001`, Zone 2 GL lock, adapter fail-closed authz), `E0-4` (PREPARE failure, live MariaDB `Error 1205` MDL timeout + lock release, Stage 6 finalize fault, adapter compensation), `E0-5` (duplicate-effect prevention, negative stock block, DDL/adapter idempotency), and `E0-6` (`BPL-029` mapping check + `ChangeEngineAdapter` + live `Custom Field` quarantine + `zatca_sa` Phase 1).
- `infra/dev/docker/run_phase0_proofs.py`: host-side CLI harness orchestrating synthetic tenant provisioning/teardown (`--skip-provision`, `--keep-sites`, `--output-json`) and component syncing without exposing credentials or host paths.
- `apps/engine/change_engine/change_engine/tests/test_erp_021_phase0_proofs.py`: offline unit and contract tests (7 tests) verifying mapping drift detection, gross + net Trial Balance reconciliation, adapter isolation/fault/quarantine contracts, `zatca_sa` bundle smoke, and runner CLI validation.
- `docs/architecture/phase0-engine-proof-report.md`: empirical Phase 0 proof matrix and `E0-7` catalog of 7 engine limitations/alternatives.
- `.github/workflows/ci.yml`: added `test_erp_021_phase0_proofs.py` step to `engine-adapter-conformance` job.
- `docs/open-questions.md`: added `Q-23` empirical bench verification update (`enable_immutable_ledger = 1` preserves `4` GL rows on cancel).
- `docs/PLAN.md`: updated `ERP-021` from `todo` to `done`.

## Verification
- `PYTHONPATH=apps/engine/change_engine python3 -m unittest apps/engine/change_engine/change_engine/tests/test_erp_021_phase0_proofs.py -v`: 7 tests, OK.
- `PYTHONPATH=apps/engine/change_engine python3 -m unittest apps/engine/change_engine/change_engine/tests/test_bpl_012_engine_adapter.py -v`: 8 tests, OK.
- Live pinned bench (`python3 infra/dev/docker/run_phase0_proofs.py --compose-project platform-erp001-20261111b --engine-port 18111 --site-a p0a-rerun.localhost --site-b p0b-rerun.localhost --skip-provision`): `"all_passed": true` (`E0-1`..`E0-6` all `passed: true`, Trial Balance gross turnover `1250.0 == 1250.0`, net closing `1150.0 == 1150.0`, `Bin` `900.0`, AR `150.0`, `BPL-029` `36` checked fields / `2` `Percent` vs `Float` mismatches), followed by clean teardown of both ephemeral sites.
- `COMPOSE_PROJECT_NAME=platform-erp001-20261111b SITE_NAME=erp001.localhost ENGINE_PORT=18111 python3 infra/dev/docker/verify_dev_bench.py`: verified clean bench state (`erp001.localhost`).
- Repo gates (`scripts/check_docs.py`, `scripts/check_repo_hygiene.py`, `scripts/scan_secrets.py`, `scripts/check_plan_independence.py`): all PASS.

## Decisions
- Kept `Q-23` open pending Eldon confirmation alongside `ERP-022` before turning `enable_immutable_ledger = 1` on globally in `ERP-003`.
- Recorded `BPL-029` `additional_discount_percentage` `Percent` vs `Float` mismatch and the 6 other live bench findings under `E0-7` in `docs/architecture/phase0-engine-proof-report.md` rather than altering Eldon's `contracts/` lane.

## Tokens or cost
Unknown.

## Next step
Eldon reviews this PR (shared `docs/PLAN.md`, `docs/open-questions.md`, `.github/workflows/ci.yml` + security/runtime review). Next partner queue items: `ERP-024` (MariaDB LTS move), `PLT-025` (gateway token metering), `ERP-022` (Phase 1A manual golden system).
