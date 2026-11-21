# Session log: erp-026-review-fixes

Date: 2026-11-18
Author: partner
Tool and model: claude-code / sonnet-5.5
Plan IDs: ERP-026

## Summary
Fixed the cross-model review of PR 126 (Critical and all Highs, most Mediums) with a failing test first for each: the idempotency key and site lock are reserved atomically in the database before the effect, finalize is one transaction with a lease-based crash recovery, and the production guard fails closed. Merged origin/main (one INDEX.md conflict, both rows kept).

## Files touched
- apps/engine/change_engine/change_engine/adapter/storage.py, mariadb_store.py, store_api.py: `acquire_operation` (reserve key and lock in one transaction), `idem_complete` (compare and set), `idem_release`, `expired_operations`, `recover_operation`, `set_sync_version`; sites read from the database (no `_sites_cache`); nested transactions as savepoints, DDL refused inside one, autocommit-off check; `production_grade`; widened tenant column, utf8mb4 entity tables, `DATETIME` created_at with index.
- adapter/engine.py: `_acquire`, `recover_interrupted`, `_run` finalize in one transaction, provision and sync_members reserve their key; random audit, operation and event ids (no `_seq`); `test_hooks` default off and refused in production; `reset()` needs hooks; `lease_seconds`.
- adapter/harness.py: `make_frappe_adapter` hooks default off (the harness factory passes hooks on). Two existing tests pass `test_hooks=True` explicitly.
- tests/test_erp_026_review_fixes.py (new), test_erp_026_durable_adapter_state.py (restore test now runs a real apply after the dump and a first-run retry after restore; conformance follows the new key rules).
- docs/decisions/ADR-0041: made true to the code (Proposed, unaccepted, edited in place).

## Decisions
- [ADR-0041](../decisions/ADR-0041-durable-adapter-state-on-tenant-database.md) updated. Choices inside it: a dead worker's apply ends as `recovery_required`, never a blind rerun (ADR-0028); default lease 3900 s (above the one-hour contract deadline) trades a slow recovery after a crash for never taking a live operation; the `in_progress` outcome is returned for apply and rollback only, provision and sync_members answer `concurrent_change`; `sync_version` moves only by compare and set; `save_site` never rewrites it.

## Review findings
Fixed: 1 Critical (concurrent same key), 2 High (transaction and crash), 3 High (production guard), 4 High (SQLite in production), 5 High (id uniqueness), 6 Medium (nested rollback, DDL in transaction, stale cache, autocommit; thread safety by a lock per connection), 7 Medium (tenant width), 9 Medium (utf8mb4; `ensure_ascii=False` for field data), 10 Low in part (`created_at` index and DATETIME, restore test runs apply, docstring).
Deferred (follow-ups, in ADR-0041): 8 Medium (bind a store to one tenant, `tenant_id` on `adapter_events`, filtered reads: needs a design decision on the platform tenant and a protocol change); 10 Low in part (30-day purge job; SQLite has no `created_at`, dev only).

## Verified
- Own throwaway container `erp026fix-mdb` (mariadb:10.6, 127.0.0.1:33927), removed afterwards; no other container touched. With ERP026_MARIADB and ERP026_MARIADB_CONTAINER set: test_erp_026 files 33 passed; the new file 19 passed three times in a row (race tests stable). Whole change_engine folder (without the live suite B, which needs its own database): 207 passed, 2 skipped. Adapter conformance suite (BPL-025) under both harnesses: 208 passed each.
- Scratch venv outside the repo with pymysql, pytest, jsonschema, pydantic.

## NOT done or not verified
- Not run against a real bench or the Frappe site connection (CE-SEC-005, ERP-003); engine effects still do not join `store.transaction()`.
- Only MariaDB 10.6. MariaDB tests still skip in CI without a server; no CI job yet.
- A crash in `provision_site` after the engine provisioned but before the site row is written is not proven safe to rerun (UNVERIFIED).
- The diff is about 875 lines in apps/engine (tests about 330): over the 400 guideline because the Critical, the Highs and the transaction fixes touch the same code and cannot be split safely.

## Tokens or cost
Unknown.

## Next step
Follow-up plan rows: tenant-bound store and `adapter_events.tenant_id` (finding 8), purge job, heartbeat and in-process immediate recovery, MariaDB CI service, engine effects on the tenant connection (ERP-003, CE-SEC-005).
