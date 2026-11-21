# Session log: erp-002-review-fixes

Date: 2026-11-19
Author: partner
Tool and model: claude-code / sonnet-5.5
Plan IDs: ERP-002

## Summary
Fixed the MEDIUM and LOW findings from Eldon's independent review of PR #130. This log supersedes the earlier ERP-002 log where it says "0 isolation mismatches": that count came from in-wave checks that cannot detect wrong-site routing and is not an isolation result. The live run did not cross-check per-site rows; the new `verify_tag_isolation` does, but has not been run live. Real isolation proof remains `SEC-004`.

## Files touched
- `docs/architecture/fifty-tenant-load-spike-report.md`: added Scope and limits (clone vs real `ERP-003` provisioning, limited isolation evidence, host hardware not recorded, single run); renamed the mismatch column; withdrew the "145 MiB per site" RSS claim; labelled all sizing recommendations `UNVERIFIED`; recorded the MariaDB settings; added follow-ups.
- `infra/dev/docker/my.load-spike.cnf`: new opt-in file with the tuned MariaDB settings (`1 GiB` buffer pool, `table_open_cache = 8192`).
- `infra/dev/docker/run_50_tenant_load_spike.py`: `verify_tag_isolation` post-run per-site ToDo cross-check, `_collect_host_info` (docker and CPU limits in the JSON), `isolation_mismatches` renamed `response_check_failures`.
- `infra/dev/docker/tests/test_erp_002_load_spike.py`: stateful mocked flow plus 4 tests for the tag check (pass, wrong-site row, missing row, fail-closed).

## Decisions
- None. Cross-lane: n/a.

## Tokens or cost
Unknown.

## Next step
Re-run the 50-tenant spike live with the new harness to record `host` and `tag_isolation_check` (ERP-002 follow-up; no new plan row opened). Then `SEC-004`.
