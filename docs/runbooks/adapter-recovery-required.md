# Runbook: clear `recovery_required` on a tenant site

Status: draft (ERP-026)
Owner: partner

## Purpose
An apply or rollback that dies, loses its lease, or cannot undo its own steps ends `recovery_required` ([ADR-0041](../decisions/ADR-0041-durable-adapter-state-on-tenant-database.md), [ADR-0028](../decisions/ADR-0028-recoverable-journaled-change-apply.md), [engine adapter contract](../../contracts/engine-adapter.md) 5.6). The site is then blocked: every later `apply` and `rollback` is refused in `inspect` with `recovery_required` until a human resolves it. In production the test hooks are refused, so this runbook is the only way back to `ready`. Do not clear the state on a guess: a wrong clear lets a second apply run on top of a half-applied site.

## Preconditions
- Two people: one runs the steps, the other confirms the comparison in step 4 before step 6. Neither guesses.
- Access to the tenant's own database (adapter state lives beside the tenant data) and to `export_config` for that tenant.
- Know the tenant id and the artifact id from the alert (`blueprint.apply_failed` with `error_code` `recovery_required`).
- Never put customer data in the incident record; use ids and hashes. The record itself lives outside this repo.

## Steps
1. Confirm nothing is running. In the tenant database both queries must return no row for the tenant (a running apply holds the lock; wait for its lease, 3900 s by default, to end and be recovered, never clear around it):
   `SELECT lock_id FROM adapter_sites WHERE tenant_id = :t AND lock_id IS NOT NULL;`
   `SELECT operation, idempotency_key FROM adapter_idempotency WHERE tenant_id = :t AND status = 'in_progress';`
   A `BaseException` or a failed finalize transaction can leave the lock held until the lease expires, so let a healthy adapter recover the expired operation at startup, confirm both queries return no rows, and follow the remaining steps to clear `recovery_required`.
2. Read what happened (read only): `SELECT state, applied_json FROM adapter_sites WHERE tenant_id = :t;`, the stored outcome of the failed key in `adapter_idempotency` (`outcome_json`: `stages`, `steps`, `error.stage`), the rows of `adapter_execution_journal` for the artifact (phase `execute` or `compensate`, per step), and the `adapter_events` rows for the tenant. This tells you which steps ran.
3. Take the live configuration from the engine with `export_config` (read only) and its hash. Take the base revision (`applied_json`) and the artifact's target revision from the plan.
4. Compare, and have the second person confirm. Exactly one case holds:
   - **A. Live equals base** (no step took effect, or compensation finished): safe to clear (step 6), then re-run the change with a new idempotency key.
   - **B. Live equals target** (every step ran, only the outcome was lost): the adapter record still says base, so a re-run would execute the steps against the engine a second time. UNVERIFIED that the engine accepts that for every step kind. Do not re-run; treat it as C and return to base first.
   - **C. Anything else** (a partial state, or B): do not clear. Return the engine to base by hand with the artifact's stored inverse (for an initial build, quarantine what it created, contract 5.6.2), or restore the tenant database from the last backup (keys, journal and data come back together, ADR-0041 Restore); then compare again until it is A.
5. Do not delete or edit the failed key's row in `adapter_idempotency`. It must keep replaying `recovery_required` so a retry of that key can never run the steps again.
6. Clear the state in one statement, only if the lock is still free:
   `UPDATE adapter_sites SET state = 'ready' WHERE tenant_id = :t AND state = 'recovery_required' AND lock_id IS NULL;`
   It must change exactly one row. Paste the statement, the rows changed, and the export hashes into the incident record.
7. Re-run the change (case A) through the control plane with a new idempotency key and a fresh plan token.

## Verification
- `site_status` returns `ready` with `lockedBy` empty and `applied` equal to the intended revision.
- `export_config` hash equals the target hash (after step 7) or the base hash (if the change was abandoned).
- The execution journal shows no step run twice for the new artifact: `adapter_execution_journal` has one `execute` row per step.

## Rollback
Step 6 is undone by `UPDATE adapter_sites SET state = 'recovery_required' WHERE tenant_id = :t AND lock_id IS NULL;`. If step 7 fails again the site ends `recovery_required` again; start over at step 1 and do not retry blindly.

## Who
On-call engineer (partner lane) runs it; the other founder or a second engineer confirms step 4. Every use is logged in the incident record. An audited admin operation to replace the manual `UPDATE` would need a contract change (`contracts/` is Eldon's lane); it is not planned.
