# Session log: erp-024-mariadb-lts

Date: 2026-11-17
Author: partner
Tool and model: antigravity / gemini-4-hydrogen
Plan IDs: ERP-024

## Summary
Moved the development bench database pin off end-of-life MariaDB `10.6` onto maintained `mariadb:11.4` LTS (`11.4.13-MariaDB-ubu2404`), enforced the `11.4.` series in `verify_dev_bench.py`, and verified full bench provisioning, unit/live tests, and the `ERP-021` Phase 0 proof suite (`E0-1`..`E0-6`) on an isolated MariaDB `11.4` Compose stack.

## Files touched
- `infra/dev/docker/docker-compose.dev.yml`: pinned `mariadb:11.4@sha256:f6eca93803e34766e787a96bad9e2ac5abbcdcb8e7f390a6f34e9bf3eee525e6` (`linux/amd64` digest).
- `infra/dev/docker/verify_dev_bench.py`: added `EXPECTED_MARIADB_SERIES = "11.4."` runtime verification via `SELECT VERSION()`.
- `infra/dev/docker/tests/test_bench_live_verifier.py`: added `test_eol_mariadb_10_6_fails_verification` and `BENCH_LIVE_SITE` env support for non-default site names.
- `infra/dev/docker/README.md`, `apps/engine/README.md`, `docs/legal/licence-register.md`, `docs/architecture/engine-version-policy.md`, `docs/open-questions.md`: updated MariaDB `10.6` pin references to `11.4` and recorded `ERP-024` verification findings (`Q-25`).
- `docs/PLAN.md`: set `ERP-024` to `done`.

## Verification
- Isolated Compose bench (`COMPOSE_PROJECT_NAME=erp024-lts-probe`, `ENGINE_PORT=18211`) booted `mariadb:11.4@sha256:f6eca93803e34766e787a96bad9e2ac5abbcdcb8e7f390a6f34e9bf3eee525e6` (`11.4.13-MariaDB-ubu2404`) healthy and provisioned two synthetic sites (`probe-a.localhost` and `probe-b.localhost`) via `bench new-site --install-app erpnext --install-app hrms --install-app change_engine`.
- Observed expected `bench new-site` warning from `frappe/database/mariadb/setup_db.py`: `Warning: MariaDB version ['11.4', '13'] is more than 10.8 which is not yet tested with Frappe Framework.` (non-blocking).
- `verify_dev_bench.py` passed: `Verified synthetic site probe-a.localhost on project erp024-lts-probe: apps, versions, HRMS commit, MariaDB 11.4.13-MariaDB-ubu2404, Redis and HTTP.`
- `BENCH_LIVE_PROJECT=erp024-lts-probe BENCH_LIVE_SITE=probe-a.localhost ENGINE_PORT=18211 python3 -m unittest discover -s infra/dev/docker/tests -v`: `Ran 17 tests in 12.824s`, `OK (skipped=1)` (16 passed including both live verifier checks; `test_mismatched_hrms_commit_fails_the_build` skipped without `BENCH_BUILD_INTEGRATION=1`).
- `ERP-021` Phase 0 proof suite (`run_phase0_proofs` on `probe-a.localhost` / `probe-b.localhost`): `"all_passed": true` across all 6 proofs (`E0-1` two-tenant isolation, `E0-2` balanced Trial Balance `1250.0 == 1250.0` & net closing `1150.0 == 1150.0` + `Bin` `900.0` + AR `150.0` + Q-23 immutable ledger cancel + Commercial Rounding, `E0-3` permission/role denial, `E0-4` Stage 4 live MariaDB `1205` MDL timeout recovery & Stage 6 fault recovery, `E0-5` duplicate/idempotency prevention, `E0-6` BPL-029 live meta check & ZATCA Phase 1 component).
- Disassembled and removed the ephemeral `erp024-lts-probe` Compose project and volumes (`docker compose down -v`).

## Decisions
- Selected MariaDB `11.4` LTS over `10.11` / `11.8` (`Q-25`) because it provides the longest upstream maintenance window listed in `docs/architecture/engine-version-policy.md` (`2029-05-29` UNVERIFIED) while remaining clean on Frappe `v15.126.0` / ERPNext `v15.124.5`; awaits Eldon's PR review before confirming `INF-005` target.

## Tokens or cost
Not measured directly (gateway metering is implemented separately under PLT-025).

## Next step
Wait for Eldon's review on ERP-024 (and confirm Q-25 for INF-005); proceed to `PLT-025` (gateway token and cost metering).
