# Session log: erp-002-50-tenant-load-spike

Date: 2026-11-18
Author: partner
Tool and model: antigravity
Plan IDs: ERP-002

## Summary
Completed `ERP-002` (50-tenant load spike on one pinned Frappe/ERPNext/HRMS v15 + MariaDB 11.4 + Redis 7.2.7 Compose bench pool). Provisioned 50 synthetic sites (`load-001.localhost` .. `load-050.localhost`, `42,600` InnoDB tables, `2,525.99 MB` logical data + index, `5.7 GiB` on disk), verified cross-tenant MariaDB user isolation (`errno 1142`), warmed all 50 sites (`50/50` HTTP `200`), and ran 4 concurrent mixed HTTP/REST read+write waves (`c=10, 25, 50, 100`, 250 requests each = 1,000 requests total) with `100.0%` HTTP `200` and `0` isolation mismatches. Documented throughput saturation (`~93.4 RPS` peak at `c=50` on 2 Gunicorn gthread workers), MariaDB `table_open_cache` / InnoDB dictionary RAM bottleneck (`7.10 GiB` RSS at 50 active sites vs `+26 MiB`/worker in Gunicorn and `25.01 MiB` in Redis), and recommendations for `PLT-003` and `INF-010`.

## Files touched
- `infra/dev/docker/run_50_tenant_load_spike.py`: Added 50-tenant provisioning + template-clone + mixed concurrent REST load spike runner and resource telemetry collector (`--dry-run`, `--provision-only`, `--skip-provision`, batched ranges, secret redaction).
- `infra/dev/docker/tests/test_erp_002_load_spike.py`: Added 7 offline unit and contract tests covering identifier validation, latency percentile math, Docker memory parsing, secret redaction, CLI `--dry-run`, missing-secret fail-closed exit, and mocked `run_spike` execution (auto-discovered by `.github/workflows/tests.yml`).
- `docs/architecture/fifty-tenant-load-spike-report.md`: Recorded all empirical measurements, bottleneck diagnosis, and capacity/provisioning recommendations for `PLT-003` and `INF-010`.
- `docs/PLAN.md`: Marked `ERP-002` as `done`.

## Decisions
- Recommended pre-warmed site pools (not inline `bench new-site` or synchronous SQL dump restore) for `PLT-003` and 50–100 tenant MariaDB sharding with `table_open_cache >= 32768` for `INF-010`. Cross-lane: n/a.

## Tokens or cost
Unknown.

## Next step
Pick up `SEC-004` (Cross-tenant isolation test suite) and then `CE-SEC-005` (Change engine real-bench CI).
