# ADR-0036: Durable adapter state lives in the tenant database

Status: Proposed
Owner: partner
Approved by: pending (Eldon review)

## Context
The engine adapter ([contracts/engine-adapter.md](../../contracts/engine-adapter.md) 5.6 and the idempotency rules) promises that a key replays its stored result for at least 30 days, that the step journal proves no step ran twice, and that audit records survive. Until ERP-026 the adapter state sat in a SQLite store whose default is `:memory:`, so a restart or a restore could forget a key and let an apply run a second time. ADR-0028 requires durable checkpoints at every recovery boundary.

## Decision
- **Where:** all adapter state is stored in the tenant's own MariaDB database, beside the tenant data. One schema per tenant database; every table still carries `tenant_id` so a misrouted connection cannot read another tenant's rows.
- **Tables:** `adapter_sites` (state, applied ids, history, lock), `adapter_idempotency` (PK tenant, operation, key; input hash; stored outcome; `created_at`), `adapter_plan_tokens`, `adapter_plan_evidence`, `adapter_prepare_intents`, `adapter_execution_journal`, `adapter_audit_log` (unique audit id), `adapter_events`, `adapter_members`. Schema is created idempotently (`CREATE TABLE IF NOT EXISTS`, InnoDB, utf8mb4).
- **Transactions:** every store write is its own committed transaction. `MariaDBAdapterStore.transaction()` groups several writes, and the store accepts the caller's own connection, so an effect run on the tenant connection and its idempotency record commit or roll back together. Effects the adapter cannot put on that connection (DDL, which commits implicitly; external sends) use the journal and the recovery rules of ADR-0028: the key is bound at `acquire`, the outcome is stored at the end, and a crash in between is resolved by recovery, not by a second blind run.
- **Retention:** idempotency keys at least 30 days (the contract's `idempotencyRetentionSeconds`); the purge job is a follow-up and deletes by `created_at`, never earlier. Journal and audit records are not purged by the adapter; the audit retention period belongs to the compliance docs and is UNVERIFIED here.
- **Restore:** because keys, journal and the data they describe live in one database, a dump or point-in-time restore returns them together as of one moment. A key issued after the restore point is unknown after the restore, and its effect was rolled back with it, so a retry is a correct first run. Tested with a real dump and restore.
- **Production guard:** the adapter takes an `AdapterStore`. When the environment is production it refuses a volatile (in-memory) store at construction. Production is `environment="production"`, or `CHANGE_ENGINE_ENV` set to anything other than `dev`, `development` or `test`, or, when neither is set, hooks switched off. Unknown values fail closed. The in-memory store stays for unit tests and dev.

## Alternatives rejected
- A central state store (one database for all tenants): a second place to back up and restore, so keys and effects can disagree after a restore of either side; a shared failure and cross-tenant exposure point; breaks per-tenant export and deletion.
- Redis or another cache for keys: not durable by default and not covered by the tenant backup.
- Keep SQLite files per tenant: not covered by the tenant database backup and a second durability story to operate.

## Consequences
- Follow-ups (not in ERP-026): wire the engine so an apply's effect and its idempotency write share one connection where the effect is transactional; the 30-day purge job; require MariaDB (not a SQLite file) in production once ERP-003 provisions it; a restore drill on the real bench (CE-SEC-005). A SQLite file is durable but is only accepted for dev.
- Tests: conformance for both stores, restart replay, restore, guard; MariaDB tests need a server and are skipped without one.

## Supersedes
None.
