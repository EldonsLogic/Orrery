# Session log: durable-adapter-state

Date: 2026-11-18
Author: partner
Tool and model: claude-code / sonnet-5.5
Plan IDs: ERP-026

## Summary
ADR-0036 (adapter state lives in the tenant database), an `AdapterStore` interface, a MariaDB store, and a production guard that refuses an in-memory store, with conformance, restart, restore and guard tests. ERP-026 is set to done; the engine-side atomic wiring, purge job and a MariaDB CI job are follow-ups (below).

## Files touched
- docs/decisions/ADR-0036-durable-adapter-state-on-tenant-database.md and INDEX.md: the decision (Proposed).
- apps/engine/change_engine/change_engine/adapter/store_api.py: `AdapterStore` protocol, `StoreRefused`, `is_production`, `assert_store_allowed`.
- adapter/mariadb_store.py: `MariaDBAdapterStore` (subclass of the SQLite store: MariaDB schema and upserts, nestable `transaction()`).
- adapter/storage.py: `volatile` flag. adapter/engine.py: `store` and `environment` arguments and the guard. adapter/harness.py: the no-hooks test harness passes `environment="test"`.
- tests/test_erp_026_durable_adapter_state.py; pyproject.toml: optional `mariadb` extra (pymysql). docs/PLAN.md: row done.

## Decisions
- [ADR-0036](../decisions/ADR-0036-durable-adapter-state-on-tenant-database.md). Production = `environment="production"`, or `CHANGE_ENGINE_ENV` other than dev/development/test, or (neither set) hooks off. The in-memory store was a `:memory:` SQLite default, not a separate class.

## Verified
- Own throwaway container `erp026-durable-state-mdb` (mariadb:10.6, 127.0.0.1:33726), removed afterwards; no other container touched. With `ERP026_MARIADB` and `ERP026_MARIADB_CONTAINER` set: 14 passed (7 SQLite/guard, 7 MariaDB including real `mariadb-dump` restore and rollback of effect plus key together).
- Whole change_engine test folder (without the live suite B): 182 passed, 8 skipped (the MariaDB ones, no server). Ran in a scratch venv with pymysql, pydantic, jsonschema.

## NOT done or not verified
- MariaDB tests skip in CI and on any machine without a server; no CI job runs them. Needs a MariaDB service in the tests workflow (Eldon's/CI lane request).
- Only MariaDB 10.6 tested. `ADD COLUMN IF NOT EXISTS` needs 10.0.2 or later.
- The engine does not yet put an apply's effect and its idempotency write on one connection; `transaction()` and the injectable connection are the tool for it. Idempotency purge job (30 days) not written. Production still accepts a SQLite file; requiring MariaDB waits for ERP-003.
- Not run inside a real bench or against the Frappe site connection (CE-SEC-005).

## Tokens or cost
Unknown.

## Next step
Follow-up plan row: engine wiring for atomic effect plus key, purge job, MariaDB CI service, require MariaDB in production (ERP-003 dependency).
