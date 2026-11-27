# ADR-0073: Change-engine tenant identity from a durable site binding, and a dedicated deployment connection

Status: Proposed
Owner: partner
Approved by: pending (security review by a different model, then Eldon line by line; Tier 3, RULES 42: touches tenancy and the audit path)

Plan ID: CE-SEC-011 (slice 2, G1, design only). No code until this ADR is Accepted. Internal document: it names the engine (ADR-0016). `CE/` means `apps/engine/change_engine/change_engine/`. Line numbers are at `c8fbac58`. Items marked **(P)** are proposed choices of this ADR; everything else restates code or an existing ADR. Facts about Frappe or MariaDB behaviour that the repo code does not show are marked UNVERIFIED.

## 0. Assumptions
- B1. Q-311 as answered by Eldon in open PR #374 (pending the partner's agreement): the canonical tenant id is `t_` plus lowercase letters, digits and underscores. The host-name label is derived from it (underscores to hyphens) and is only compared, never parsed back into a tenant id. No exception: with the drained cutover of 2.5 (Q-688), no lock key and no read id in the new code comes from the label either.
- B2. No real customer site exists (ADR-0070 A3, ADR-0051 item 6). Dev and bench sites may hold rows, and the migration must handle them anyway.
- B3. ADR-0040 (provisioning), ADR-0041 (adapter state in the tenant database), ADR-0068 (signed grant, `siteId`) and ADR-0070 (journal) are Proposed. This ADR builds on them and edits none of them. Section 7 lists what each would need to say.

## Context
- **How identity is chosen today.** `_resolve_site_id` (`CE/api/endpoints.py:2269-2298`) takes `frappe.local.site` and maps it to a tenant id with `_tenant_of_site` (`:2240-2251`). Without the backend's resolver, that function parses the host label back into a tenant id (`t-alpha.<domain>` gives `t_alpha`). Q-311 forbids that parse (B1). With the resolver, `FrappeSiteResolver.tenant_of` (`CE/adapter/frappe_backend.py:163-178`) matches `site_map` values exactly and otherwise parses the label too. If nothing maps, the identity is the host name (`endpoints.py:2284`).
- **Why that matters.** The identity scopes everything the guards rely on. Lock keys hash `site_id` (`CE/guarded_apply/schema_reconciler.py:138-151`). MariaDB advisory locks are global to the server, not to one database (UNVERIFIED for our pinned MariaDB; documented MariaDB behaviour). So two identities for one site give two lock scopes. Holds and replay records written under one identity are also invisible to lookups under the other (`_read_site_ids`, `:2254-2266`).
- **The slice 1 stopgap.** An RPC call that builds its own adapter has no resolver (`:2549-2551`, `:2804-2806`, `:2925-2927`, `:3045-3047`). `_unmapped_site_refusal` (`:2315-2334`) therefore refuses when the site's database shows another tenant identity: a row in `tabChange Engine Blueprint State`, or a tenant-id-shaped `site_id` in the audit table (`has_other_tenant_identity`, `:1382-1402`). A custom `site_map` site with neither kind of row passes and runs under its host name. A later backend call on the same site writes under the tenant id. That is the gap this slice closes (PLAN row CE-SEC-011).
- **Revert.** `revert_configuration_change` builds its own adapter (`:3096-3098`) and does not resolve the site at all. `execute_rollback` takes `site_id` from the stored record (`CE/guarded_apply/rollback_engine.py:154`) and locks under it (`:163`). A record stored under the host name therefore locks a different scope from a live deployment under the tenant id.
- **Session hazards on the engine session.**
  - `begin_fresh_read_view` (`endpoints.py:731-756`) rolls the engine session back after the locks. It trusts Frappe's `transaction_writes` counter to show that nothing is pending, and its own docstring says the counter misses writes such as `REPLACE` (`:740-741`). A missed write is rolled back silently.
  - Audit and evidence commits use the engine session (`_commit_durable`, `:1433-1438`), so they also publish any caller writes pending on it.
  - A lost or unverified lock discards the whole engine session (`mark_session_unusable`, `:762-775`), which ends the caller's request.
  - ADR-0070 already places its snapshot reads (item 1.6), journal appends (item 1.8, "Dispatch rules") and recovery (item 4.3) on "CE-SEC-011's dedicated connection" without defining it. ADR-0068 item 12 writes its reservation on "the deployment's own connection".
- **Three tenant-identity carriers already exist in the tenant database.** None of them fits as a binding:
  - `tabChange Engine Blueprint State` is upserted on every state write (`frappe_backend.py:401-462`, `ON DUPLICATE KEY UPDATE` from `:430`).
  - `adapter_sites` (ADR-0041; `CE/adapter/mariadb_store.py:25-28`) has one row per tenant and is changed by every operation.
  - ADR-0068 item 3's one-row in-site `siteId` record is designed but not built.

## Decision

### 1. The site binding (where identity lives, who writes it, how it is read)
1.1 **(P) Store.** One table, `adapter_site_binding`, in the site's own database (ADR-0006, ADR-0041). Its key is a constant, `id TINYINT NOT NULL PRIMARY KEY` with `CHECK (id = 1)`. A second row therefore fails on the key, atomically, so two concurrent writers cannot both insert and observe-then-act has no race. (CHECK enforcement on the pinned MariaDB is UNVERIFIED; the primary key alone already stops a second `id = 1`, and the read still refuses more than one row.) Columns: `binding_version` (1), `kind` (`tenant` or `bench`), `tenant_id` (grammar `t_[a-z0-9][a-z0-9_]{1,59}[a-z0-9]`, as `endpoints.py:2235` and `frappe_backend.py:73`; NULL for `bench`), `site_name` (the exact site name the binding was made for), `bound_by` (the provisioning `workflowId`), `bound_at`, and `site_id` (ADR-0068's opaque incarnation id, NULL until ADR-0068 lands). This is the one-row record of ADR-0068 item 3, defined here first, so a site never carries two bindings. Reasons for a fourth table rather than reuse: the existing carriers are rewritten on every operation, and the binding must be create-only. Eldon answered Q-684 (2026-11-26): this table, shared with ADR-0068's `siteId` record, inside the backup boundary, create-only by triggers as in ADR-0070 (1.8), not `site_config.json`. He answered Q-685 the same day: the row stays unsigned for G1, guarded by the triggers and the one-row key; a MAC under ADR-0070's per-tenant key, once Q-635's key exists, is row CE-SEC-019.

1.2 **(P) Writer and moment.** One writer function, `write_site_binding` (partner lane `services/provisioning/`), creates the change-engine store tables if absent (3.8), then the binding table and its triggers (1.8), verifies the triggers, then inserts the row. Its callers are provisioning only: ADR-0040 Step 3 (`create_site`), by `provisioning-site-init`, right after `init_adapter_state` and before the site serves any call; `bind_existing_site` (2.1); and the dev and test setup (`scripts/provision_tenant_site.py`, the conformance harness). The steady-state adapter, including its `provision_site`, never writes it. The value comes from the control-plane record (ADR-0040 item 2), never from a request and never from the host name. The write is a single `INSERT`, and it always applies the veto rules of 2.2:
- an existing equal row is the post-condition (observe, then act, ADR-0040 item 4); a duplicate-key error from a concurrent writer is answered the same way, from the row that won;
- an existing different row, or tenant evidence for another tenant, blocks with `site_exists_different_target`.
The only change to a bound row is `rebind_site` (1.9). Deprovisioning drops the row with the database (ADR-0040 item 8.5).

1.3 **(P) Bench and dev sites** get `kind = bench`, written by the dev setup script, with the site name as their identity. Under the production guard of ADR-0041 a `bench` binding refuses with `site_binding_not_tenant`. The in-memory path, where there is no resolved site and Frappe cannot be imported (`endpoints.py:647-653`, `:2293-2294`), keeps its behaviour in tests. Under the production guard it refuses too (P). No such guard exists on that path today.

1.4 **(P) How the RPC path reads it.** `_resolve_site_id` reads the binding on the dedicated connection (section 3) before any lock. The read is one short transaction that ends with `ROLLBACK` before the first `GET_LOCK`, so no metadata lock on the binding, `tabChange Engine Blueprint State`, `adapter_sites` or the store tables is held while the call waits for locks (3.5). The store existence check of 3.8 runs in the same read. The result is the identity `C`: `tenant_id` for a `tenant` binding, `site_name` for a `bench` binding. It refuses with a stable reason code when:

| Condition | `reason_code` | Disposition |
|---|---|---|
| table missing, or no row | `site_binding_missing` | `SITE_UNRESOLVABLE` |
| read fails, more than one row, unknown version, or a value outside the grammar | `site_binding_unreadable` | `SITE_UNRESOLVABLE` |
| a binding trigger (1.8) is missing (blocks in production too, Q-687) | `site_binding_unguarded` | `SITE_UNRESOLVABLE` |
| `kind = bench` under the production guard (1.3) | `site_binding_not_tenant` | `SITE_UNRESOLVABLE` |
| `site_name` differs from `frappe.local.site` (exact, byte for byte) | `site_binding_stale` | `SITE_UNRESOLVABLE` |
| `tabChange Engine Blueprint State` or `adapter_sites` holds a `tenant_id` other than `C` (for a `bench` binding, any `tenant_id` at all), or the audit table, before ADR-0070's migration, holds a tenant-id-shaped `site_id` other than `C` (2.5; the shape test of `has_other_tenant_identity`, `endpoints.py:1382-1402`), or `tabChange Engine Journal Head` or `tabChange Engine Deployment`, after it, holds a `site_id` not among `_read_site_ids(C)` (1.7) | `site_binding_conflict` | `SITE_UNRESOLVABLE` |
| the store the site is on is missing: the audit table before ADR-0070's migration, the journal tables after it (3.8) | `deployment_store_missing` | `ENGINE_UNAVAILABLE` |
| the row read again under the locks (2.4) differs from the first read | `site_binding_changed` | `SITE_UNRESOLVABLE` |
| the dedicated connection is on another database, user or server (3.3) | `deployment_connection_mismatch` | `ENGINE_UNAVAILABLE` |

The existing `site_mismatch` (a caller value that is not `C`) and `invalid_site_id` stay (`:2289-2292`, `:2295-2297`). The caller never supplies the identity: a caller value is only compared. No identity, lock key or read id is ever derived from the host label (2.5); the host name itself is only the read alias of 1.7. `_tenant_of_site` and `FrappeSiteResolver.tenant_of` stop taking part in identity decisions (B1), and `_unmapped_site_refusal` is removed.

1.5 **(P) Every entry point that builds its own adapter** resolves `C` this way:
- `apply_configuration_change`, the property-setter, workflow and report endpoints, and `revert_configuration_change`;
- ADR-0070's recovery entry point, through `_resolve_site_id(None, ...)` (its item 4.3, step 1).

Revert takes its locks under `C`, never under the stored string. `execute_rollback` checks `record["site_id"] in _read_site_ids(C)` (1.7) right after the pre-lock `_read_record` (on the dedicated connection, ending with `ROLLBACK`), before `_already_finished` and before `acquire_scoped_locks` (today `rollback_engine.py:150` runs first), and again on the record read under the locks. A foreign record refuses with `site_mismatch` / `SITE_MISMATCH` and takes no lock, even when it is already finished. `propose_configuration_change` (`endpoints.py:226-446`) takes no lock. Today it is not write-free: constructing its adapter (`:325`) runs `_ensure_audit_table` (`:703`), DDL that commits the engine session. Under 3.8 that call goes, and only then does propose write nothing and send no DDL (CE11-T14).

1.6 **(P) Backend path.** `FrappeRuntimeBackend._site_session` (`frappe_backend.py:244-247`) resolves the site from `context.tenantId` and connects. It then reads the binding and requires `kind = tenant`, `tenant_id == context.tenantId` and `site_name ==` the resolved name. Otherwise it answers `tenant_not_found` (contract error table; the ADR-0041 misrouting answer) and logs `site_binding_mismatch` internally. `provision_site` finding no row answers `site_not_ready`; it never writes one (1.2). The read never runs on `f.db`, which is not freshly connected when `prev_site == site_name` (`frappe_backend.py:265`) and may hold the caller's work: `_site_session` opens a short-lived connection (3.3 items 2 and 3), reads, ends with `ROLLBACK` and closes it before yielding, so it covers backend calls that never build a deployment adapter. A guarded step (`execute_step`, `frappe_backend.py:1210`) then runs the full 1.4 read on its own dedicated connection with `context.tenantId` as the expected identity and the site name as the expected `site_name`; both reads are checked against the same expectations (`kind = tenant`, the context tenant, the resolved site name), and a failure on either answers `tenant_not_found`; 2.4 then compares the under-lock read with the step's own pre-lock read. No row object crosses between the two.

1.7 **(P) Read ids.** `_read_site_ids(C)` adds the host name as a read-only legacy alias only when `binding.site_name == frappe.local.site` and the binding's identity is `C`. The alias is removed once ADR-0070's migration completes on the site. There is no other alias (2.5).

1.8 **(P) Triggers** (as ADR-0070 item 1.7). `write_site_binding` installs a `BEFORE UPDATE` trigger that always signals `SQLSTATE '45000'`, and a `BEFORE DELETE` trigger that signals unless the session variable `@ce_site_rebind` equals `OLD.site_name` (set only by `rebind_site`, 1.9; a trigger reading a user variable is UNVERIFIED on the pinned MariaDB). Like ADR-0070's, they guard against code bugs and naive SQL, not against anyone who can write the database as the site's user (Q-685, answered in 1.1).
- A missing trigger blocks the site: `write_site_binding` fails with `site_binding_unguarded` and writes no row; ADR-0040 Step 5 and the health check report it; the binding read (1.4) checks both triggers in `information_schema.TRIGGERS` and refuses; the backend (1.6) answers `site_not_ready` and logs `site_binding_unguarded`. (Whether the site user sees its triggers there without the `TRIGGER` privilege is UNVERIFIED; if it does not, the check refuses, fail closed.) Eldon answered Q-687 (2026-11-26, for both founders; partner to confirm): block in production too (fail closed), not only report. (The "fail-closed trigger answer" cited in revision 2 is not on main; Q-687 replaces it.) ADR-0070 1.7 as written still lets its own missing trigger pass; this ADR does not change that.
- Creating them needs the `TRIGGER` privilege (ADR-0070 U1, U2). Without it every site blocks, so a pre-flight check runs on each database server before rollout (2.3 step 1) and before the first site on a new server (ADR-0040 Step 3): the provisioning user can create the triggers, and the site's database user sees them in `information_schema.TRIGGERS`. Either failure stops the rollout and binds nothing.
- Order: the table, then the triggers (each DDL commits on its own), then the `INSERT`. A crash in between leaves an empty or unguarded table that refuses, and a rerun completes it.

1.9 **(P) Rebind.** A rename, a move or a restore under another site name keeps the tenant and changes `site_name`. Because `UPDATE` always signals, it is also the path that fills `site_id` when ADR-0068 lands (same site name, NULL to the new id). It is a provisioning-only operation, `rebind_site` (partner lane `services/provisioning/`), called only by the provisioning workflow (ADR-0068 item 3, trusted provisioning):
1. **Drained.** The control plane has stopped routing calls to the site and waited past the call ceiling (3.3: lock waits plus the statement limit), so no call that read the old row is still running. The drain is a control-plane state that the database does not check (proposed for ADR-0040, section 7; UNVERIFIED that the gateway can hold one site).
2. **Vetoes.** The 2.2 vetoes are applied against the new site name. A different `tenant_id` or `kind` is refused with `site_exists_different_target`: that is a new provisioning, not a rebind.
3. **One transaction** on one connection, observe then act (ADR-0040 item 4): `SELECT ... FOR UPDATE` the row and compare the full tuple `(kind, tenant_id, site_name, site_id)`. Equal to the target: no `DELETE` or `INSERT`; the step goes on to its evidence (item 4), which a retry after a crash past the `COMMIT` still emits. Equal to the expected old tuple: `SET @ce_site_rebind = <old site_name>`, `DELETE` the row, `INSERT` the new one, `COMMIT`. Anything else refuses `site_exists_different_target`. The full tuple matters because filling `site_id` keeps the site name. `SET @ce_site_rebind = NULL` runs in the `finally`. A crash before the `COMMIT` rolls both statements back. The old row stays and the site keeps refusing under the new name (`site_binding_stale`); no committed state has the table empty.
4. **Evidence.** It emits a security event (`site_rebound`: old and new site name, tenant, workflow id) and writes the control-plane audit record of the workflow step, both before the site is undrained.

The T20 static check allows exactly one `DELETE` on the table and one assignment of `@ce_site_rebind`, both in `rebind_site`. No code issues `UPDATE` on the table, and nothing under `apps/engine/` issues either statement.

### 2. Migration from the slice 1 evidence refusal
2.1 **(P) Source.** For every existing site, a one-shot provisioning operation, `bind_existing_site` (partner lane `services/provisioning/`, run per site), writes the row from the control-plane record. The site's database evidence only confirms the value or vetoes it. A veto blocks the site for a human, and nothing is written.

2.2 **(P) Vetoes** (the rules of `write_site_binding` and `rebind_site`). They are cumulative: a site is bound only when no row below vetoes it. Matching state rows therefore do not excuse an audit `site_id` of another known tenant.

| Evidence on the site | Rule |
|---|---|
| State rows (`tabChange Engine Blueprint State`, `adapter_sites`) | Veto unless every `tenant_id` there equals the record's tenant. Any other value is a clone signal. |
| Tenant-id-shaped audit `site_id`s | Veto when any of them is another tenant the control plane knows. One of an unknown tenant is no veto: ADR-0070's rekey records it as `caller_chosen` and moves it into `C` (its item 2.1), so those rows merge into the site's own history; until that rekey the site refuses `site_binding_conflict` (1.4, 2.5). |
| Journal `site_id`s (`tabChange Engine Journal Head`, `tabChange Engine Deployment`, when present: a rebind or restore after ADR-0070's migration) | Veto unless every one equals the record's tenant (ADR-0070's rekey wrote them as `C`). |
| Neither kind of row: a custom `site_map` site (the slice 1 gap) or a default-domain tenant site | Bind from the record. For a custom `site_map` site its `site_name` is the `site_map` value, and from then on 1.6 checks the resolver against it on every backend call. |
| Bench or dev site | Write a `bench` row, or re-provision it (ADR-0051 item 6 precedent). |

2.3 **(P) Order.**
1. Pre-flight the `TRIGGER` privilege and trigger visibility on every database server (1.8, Q-687); a failure stops here. Then ship the binding writer (Step 3) and `bind_existing_site`.
2. Bind and verify every site.
3. Ship the read side (1.4 to 1.7) in a drained single-version cutover (2.5). An unbound site then refuses (fail closed; acceptable under B2).
4. Run ADR-0070's migration with `C` taken from the binding (the 1.4 read without its audit-table clause, 2.5). This keeps ADR-0070 A1: CE-SEC-011 runs first, so nothing is rekeyed twice.
5. Remove the host-name alias (1.7).

2.4 **(P) Re-check under the locks.** Lock keys depend on `C`, so the binding is read before the locks. After the locks it is read again inside the dedicated connection's first snapshot (3.4) and compared column by column, and the `site_binding_conflict` check of 1.4 runs again in the same snapshot. A difference refuses with `site_binding_changed`, a conflict with `site_binding_conflict`, and nothing is written.

2.5 **Drained single-version cutover for step 3** (Eldon answered Q-688, 2026-11-26, for both founders; partner to confirm). Step 3 ships as one cutover: stop all guarded traffic, wait past the call ceiling (3.3: lock waits plus the statement limit) so no slice 1 call is still running, switch every worker to the new code at once, then resume. Old and new code never run side by side.
- **What goes.** Revision 2's dual lock under the slice 1 identity `L = _tenant_of_site(host) or host` (`endpoints.py:2284`), its `L` read alias and its fence existed only for slice 1 workers running beside new ones. The cutover leaves none, so all three are removed. No lock key and no read id comes from `_tenant_of_site` or the label (B1). N1 (a label-parsed `L` such as `t_beta` contending with another tenant's lock keys on a shared server) therefore no longer arises.
- **(P) Rows slice 1 left behind.** Slice 1 wrote under `L`: the host name, or a label-parsed tenant id (`t_beta` on `t-beta.other.test` bound to `t_gamma`, CE11-T10); `default` only where no site resolves (`endpoints.py:2276`, and the evidence fallback at `:1473`). Host-name rows stay visible through the 1.7 alias. A tenant-id-shaped row other than `C` would be an unseen hold or replay record, so the 1.4 conflict check refuses the site with `site_binding_conflict` until ADR-0070's migration (step 4) rekeys it into `C`. That is fail closed and reads only stored `site_id`s, never the label. The migration itself reads the binding with every 1.4 check except that audit-table clause, which exists only to hold the site for it. Under B2 this can hit dev sites only. Rows under a bare slug or another non-tenant id from code before slice 1 (CE-SEC-010) are not caught and stay unseen until step 4 (UNVERIFIED that any exist on a dev site).
- **Residual.**
  - The drain and "every worker switched" are deploy states the database does not check (as in 1.9 item 1). That the cutover reaches every process that loads the change engine (web workers, background job workers, the scheduler) is UNVERIFIED. A missed slice 1 process would lock under `L` again (H1 for that process). Slice 1's own evidence refusal (`has_other_tenant_identity`, `:1382-1402`) stops its apply calls on a site once a new worker has committed a `C`-keyed audit row there, but this ADR does not rely on that.
  - All guarded calls stop for the length of the switch; acceptable under B2.

### 3. The dedicated deployment connection
3.1 **Why.** With 3.8 it removes or bounds the engine-session hazards in the Context:
- the rollback that trusts a write counter which misses `REPLACE` (bounded by 3.2: the refresh commits instead of rolling back);
- audit commits, and the store `CREATE TABLE` run when the adapter is built, that publish the caller's pending writes (removed: the audit moves here, the table creation to provisioning, 3.8);
- a lock loss that kills the caller's session (removed, except when the rollback after a lock loss fails, 3.7).
It also gives ADR-0070 and ADR-0068 the connection they already assume.

3.2 **(P) Scope.**

| On the dedicated connection | Stays on the engine session |
|---|---|
| The binding read (1.4, 2.4) | Engine effects through the ORM: Custom Field insert, property setter, workflow and report documents |
| Advisory locks: `GET_LOCK`, `IS_USED_LOCK`, `RELEASE_LOCK` | The DDL those effects send through `_admit_ddl` (`endpoints.py:1774`), with ADR-0070's dispatch binding on the sending session |
| Every locked read of the change-engine tables: holds, idempotency lookups, evidence, ADR-0070 head and site checks | Target and schema reads, before and after the effect (`read_apply_target`, `endpoints.py:1347`; the schema baseline), so the after-read sees the engine's own pending write, as today (for example `property_setter_engine.py:494-498`) |
| Every write to the change-engine audit and journal tables, each committed there (ADR-0070 item 1.8, ADR-0068 item 12); the runtime never creates them (3.8) | The engine session's own `lock_wait_timeout` set and restore (slice 1), which bounds the ALTER's metadata-lock wait |

The engine session never reads or writes the audit and journal tables and never sends DDL for them (3.8). Its only commits are the refresh below, the commit point of an effect (3.7, including the post-ALTER commit of `apply_native_custom_field`, `endpoints.py:1842-1844`), and the implicit commit of the effect's own DDL. The direct `frappe.db.commit()` fallbacks in the engines (`workflow_engine.py:703-743`, `report_engine.py:658`) become that commit point or go. It still needs a view opened after the locks, because the ORM's own reads and the target reads must see what the locks protect. So `begin_fresh_read_view` stays on the engine session, changed in one way (P): with the counter at zero it ends the transaction with `COMMIT`, not `ROLLBACK`. A counted pending write still refuses, as today. A write the counter misses (`REPLACE`) is then committed early rather than lost. The residual is that it is published before the caller's request ends. This reverses slice 1's "no commit fallback" (`:737-738`) for that case only, on purpose: silent loss is worse than early publication.

3.3 **(P) Lifecycle.**
1. Opened once per guarded call, after the caller and payload checks and before the binding read. Never pooled, never reused across calls, never shared across threads.
2. Same database user and database as the engine session, from the site configuration the engine already loaded. No new user and no new privilege. (UNVERIFIED: which Frappe helper opens a second connection on the pinned version.)
3. On open: `autocommit = 0`, `SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ`, `lock_wait_timeout` set and read back, and the session `wait_timeout` set above the call's ceiling (lock waits plus the statement limit) and read back, so the server does not drop the idle connection while the engine session runs an ALTER. It then checks that `DATABASE()` and `CURRENT_USER()` equal the engine session's.
4. Same server: after the first lock is granted, the engine session must see `IS_USED_LOCK(k)` equal to the dedicated connection's `CONNECTION_ID()`, and both sessions must report the same `@@hostname` and `@@port`. Otherwise it refuses with `deployment_connection_mismatch`, because advisory locks on another server (a replica or a proxy route) would not serialise anything. Connection ids are per server and can match across servers by chance, so the id check alone is weak. The host and port compare narrows it but does not close it: two servers with the same host name and port (containers, some proxies) still pass (residual; what `@@hostname` and `@@port` report behind a proxy is UNVERIFIED). `@@server_id` is not used: it is 1 by default on every server (UNVERIFIED on the pinned version).
5. Closed in the `finally`, after the verified release.
6. A third connection (a fourth, short-lived one, for the backend's binding read, 1.6). The ADR-0041 store keeps its own connection (`mariadb_store.py:107-120`). ADR-0068 item 12's single transaction touches change-engine tables only, so it runs here.

3.4 **(P) Lock discipline (slice 1, moved).**
1. The idempotency lock, then the target lock, both on the dedicated connection, keys from `C` (`schema_reconciler.py:173-196`).
2. Then `START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY` on the dedicated connection for the locked reads, and the engine-session refresh of 3.2 before any target read or effect.
3. `_require_locks_held` (`endpoints.py:1410-1425`) runs on the dedicated connection: `IS_USED_LOCK(k) = CONNECTION_ID()` is the dedicated connection's id. It runs before every engine-session effect and before every journal append. The lock holder and the writer are different connections. The locks are cooperative between deployers, so that is enough as long as every guarded writer takes them (unchanged from slice 1).
4. The verified release frees the locks (`:800-822`). An unverified release closes the dedicated connection, which frees its locks. The engine session has nothing of the deployment pending by then: the `finally` first rolls back an effect that has not reached the commit point of 3.7.

3.5 **(P) No self-block.** Before control passes to the engine session for any effect or DDL, the dedicated connection holds no open transaction: snapshots end with `ROLLBACK` and appends with `COMMIT`. The reason: an open transaction keeps a shared metadata lock on every table it has read until it ends, and row locks on what it has written. The engine session's ALTER would then wait on its own process. InnoDB sees no deadlock, only a timeout (1205). (UNVERIFIED live on the pinned MariaDB; documented MDL behaviour.) The rule holds even though the dedicated connection reads only change-engine tables, so that a later change to the scope cannot bring the problem back. A 1205 during an ALTER is held as today (ADR-0070 R17).

3.6 **(P) Failure modes.**

| Failure | Result |
|---|---|
| Open fails, or database/user/server mismatch | Refuse before anything (`engine_unavailable`, `deployment_connection_mismatch`) |
| Connection lost before the intent | Locks freed by the server; the next `_require_locks_held` fails; refuse, nothing sent |
| Connection lost after the intent, before or during the effect | No further effect is sent; a non-DDL effect is rolled back (3.7). **New residual:** today the lock holder is the connection running the ALTER, so the lock cannot be lost while that statement runs. Now the idle dedicated connection can be dropped (timeout, `KILL`) during the ALTER, and another deployer could take the lock. Bounded by the `wait_timeout` of 3.3; detected by `_require_locks_held` before the completion append, and the deployment is held `RECOVERY_REQUIRED`. A `KILL` by an operator stays open (UNVERIFIED live). |
| Journal append fails after the effect | Held, as today (ADR-0070 item 1.8) |
| Close fails | Release reported unverified, adapter unusable for the call; the server frees the locks when it drops the connection (timing UNVERIFIED) |
| Worker crash | Both connections drop; locks freed; the intent is visible to recovery |

3.7 **(P) Commit point of a non-DDL effect** (property setter, workflow, report). Today the effect and its audit row become durable together through `_commit_durable` on the engine session (`endpoints.py:1433-1438`). With the audit on the dedicated connection, the order is:
1. after the locks (3.4 item 2), the engine-session refresh (3.2) first, as today (`property_setter_engine.py:234`); a counted pending write refuses here, before any intent exists, so no `PREPARED` hold is left. Then the baseline and `target_before` reads on the engine session (`property_setter_engine.py:295-382`, `workflow_engine.py:607-641`, `report_engine.py:534-566`), then the intent append on the dedicated connection, committed before any effect (`persist_prepare_and_audit_intent`, `endpoints.py:1623`);
2. the effect on the engine session, not committed;
3. `_require_locks_held` on the dedicated connection;
4. an engine-session `COMMIT`. An engine that commits in two steps today (the property setter's `hidden`, then `reqd`, `property_setter_engine.py:435-470`) repeats steps 3 and 4 for each, and a loss between them is a partial apply (held), as today. The workflow engine commits once: `ensure_workflow_state`, `ensure_workflow_action`, `set_workflow_active` and `apply_workflow` stop committing (`endpoints.py:2030, 2045, 2107, 2118`), and their writes become durable together at step 4. Saving a Workflow may itself send DDL (a `workflow_state` custom field) and commit implicitly (UNVERIFIED on the pinned version): the engine cannot see such a commit, so after a failure and its rollback a clean result needs a read-back equal to `target_before` that covers the Workflow, the state rows, the action masters, the previous workflow's active flag and the target's columns (today only the Workflow is read, `workflow_engine.py:769`); any difference is held `RECOVERY_REQUIRED`, never `FAILED_CLEAN`, as `deactivated_prev` (`:699`) is today;
5. the completion append on the dedicated connection (with its own `_require_locks_held`, 3.4).

**Residual.** The `COMMIT` in step 4 publishes whatever else is pending on the engine session. The refresh has already committed or refused the caller's own pending writes, so what is left is the effect and what Frappe writes during it (version or log rows; UNVERIFIED which on the pinned version). Like the refresh `COMMIT`, this is part of the open human decision on 3.2 and is not accepted by this ADR.
- **An ordinary effect failure with the locks held** keeps today's handling: rollback (`settle_apply`), then `FAILED_CLEAN` or `RECOVERY_REQUIRED` from the target read-back (`property_setter_engine.py:474-512`).
- **Lock lost before step 4.** The engine session is rolled back (`_rollback_durable`, `:1440-1450`), so Frappe does not publish the effect at request end. The deployment is held: by an outcome append on the dedicated connection while it is usable, otherwise by the intent without a completion, which recovery sees (ADR-0070 item 4.3). If that rollback fails, the engine session is discarded as today; that is the one case where a deployment still ends the caller's session.
- **Lost or crashed between steps 4 and 5.** The effect is durable and the journal shows only the intent. The deployment is held `RECOVERY_REQUIRED`. With no durable non-DDL baseline (CE-SEC-018, Q-686), recovery holds it for a person and never finalises it.
- **An effect that sends DDL** through `_admit_ddl` commits implicitly at the ALTER, and the DDL rules apply (3.5, ADR-0070 R17). Its post-ALTER ORM writes then follow steps 3 to 5 (`endpoints.py:1842-1844`): when `_require_locks_held` fails there (for example the CE11-T21 drop), the engine session is rolled back, the ALTER stays durable and the deployment is held `RECOVERY_REQUIRED`; the session is discarded only if that rollback fails.

3.8 **(P) Store tables are created by provisioning only.** Today `FrappeDeploymentAdapter.__init__` (`endpoints.py:702-703`) and four other sites (`:893, :1652, :1719, :1962`) run `_ensure_audit_table` (`CREATE TABLE IF NOT EXISTS`) on the engine session; it is DDL and commits implicitly, which publishes the caller's pending writes (H7), also from `propose_configuration_change` (`:325`) and before `_resolve_site_id` in every RPC endpoint (`:2551`). All five calls go. `write_site_binding` creates the audit table, and once CE-SEC-012 lands the journal tables, in ADR-0040 Step 3; `bind_existing_site` and the dev and test setup do the same, so every site has them before 2.3 step 3. The runtime only checks, in the 1.4 read, that the store the site is on exists (`information_schema.TABLES`), and refuses `deployment_store_missing` otherwise. The other choice, creating them on the dedicated connection, was rejected: the propose path opens no dedicated connection, a runtime `CREATE` needs a privilege at request time, and it silently replaces a lost store with an empty one, so holds and replay records vanish instead of refusing. The comment and fresh view before revert's pre-lock read (`rollback_engine.py:130-135`) exist only for that DDL; the read moves to the dedicated connection (1.5).

### 4. Threats
| # | Threat | Addressed by | Tests |
|---|---|---|---|
| H1 | Mapped site with no evidence runs under its host name: a second lock and hold scope beside the tenant id; also while the read side ships | 1.4, 1.6, 2.2, 2.5 drained cutover (residual: a process the cutover misses) | CE11-T01, T02, T03, T24 |
| H2 | Spoofed `site_map` entry: tenant A's id pointed at B's site, or B's id at A's | 1.6: the binding's tenant and site name must both match | CE11-T08, T09 |
| H3 | Stale binding after a rename, move, or a clone or restore under another site name | `site_name` compared exactly (1.4); rebinding only by `rebind_site` on a drained site (1.9) | CE11-T04, T05, T23 |
| H4 | Another tenant's dump restored into this site | Its binding names another site (`site_binding_stale`); its state rows conflict (`site_binding_conflict`) | CE11-T05, T06 |
| H5 | Caller-chosen identity, or identity parsed from the label | Caller value only compared; no parse for identity, lock keys or read ids (1.4, B1, 2.5) | CE11-T07, T10 |
| H6 | Revert locks the scope of the stored string | 1.5 | CE11-T11 |
| H7 | Caller's pending writes rolled back (`REPLACE`), or published by an audit commit or a store `CREATE TABLE` | 3.2, 3.7, 3.8; residual: an uncounted write is published early, and the effect commit publishes what Frappe writes during the effect | CE11-T13, T14, T22, T27 |
| H8 | Lock loss kills the caller's session, or leaves an effect for Frappe to commit at request end | 3.4, 3.7; residual: a failed rollback still discards the session | CE11-T15, T22 |
| H9 | Binding changed by a code bug, naive SQL or two concurrent writers | constant key (1.1), triggers (1.8), one rebind path (1.9) | CE11-T20, T23, T25 |

**Out of scope.**
- Anyone who can write the site database as its user, or run code as the engine's OS user, can rewrite the binding (Q-685 answered; the keyed MAC is CE-SEC-019).
- An untracked copy made outside provisioning (ADR-0068 item 3 assumption).
- The keyed evidence MAC (ADR-0070 section 3).
- Durable baselines for non-DDL holds (Q-686 answered: row CE-SEC-018).
- Gateway authentication and `context.tenantId` stamping (contract item 2).
- Other runtime `CREATE TABLE` on the engine session outside the deployment store (`action_policy_store.py:81-115`, `action_outcome_reconciler.py:107`): not on the guarded deployment path; their own row if they are.

### 5. Tests
| Id | Check |
|---|---|
| CE11-T01 | Custom `site_map` site with no state row and no tenant-id audit row: the RPC uses the bound `tenant_id`, never the host name |
| CE11-T02 | Missing table or missing row refuses `site_binding_missing`; no lock, no write |
| CE11-T03 | Read error, two rows, a bad version or an off-grammar value refuses `site_binding_unreadable` |
| CE11-T04 | `site_name` differs from `frappe.local.site` (case, trailing dot, another domain) and refuses `site_binding_stale` |
| CE11-T05 | A dump of tenant B restored into site A refuses (stale) |
| CE11-T06 | A state row for another tenant refuses `site_binding_conflict` |
| CE11-T07 | Caller `site_id` equal to the host name, the slug or another case refuses `site_mismatch` |
| CE11-T08 | Backend: `site_map` maps the context tenant to a site bound to another tenant; `tenant_not_found`, nothing written; the binding read leaves no transaction open on `f.db` (also when `prev_site == site_name`); a binding that no longer meets those expectations at the step's dedicated read answers `tenant_not_found` |
| CE11-T09 | Backend: resolver site name differs from the bound `site_name`; `tenant_not_found` |
| CE11-T10 | Default-domain site `t-beta.other.test` bound to `t_gamma` resolves to `t_gamma`; the label is never parsed for identity, a lock key or a read id |
| CE11-T11 | Revert of a host-name record locks under `C`; a record under a foreign id refuses `site_mismatch` before any lock, also when it is already `ROLLED_BACK` or `QUARANTINED` |
| CE11-T12 | Binding changed between the pre-lock read and the under-lock read refuses `site_binding_changed` |
| CE11-T13 | Live MariaDB: a caller's uncommitted `REPLACE` on the engine session survives a deployment (committed by the refresh, never rolled back) |
| CE11-T14 | Live MariaDB: an audit or journal commit on the dedicated connection does not publish an engine-session write; a counted pending write still refuses, before the intent (no `PREPARED` row), and rolling the engine session back afterwards removes it; constructing the adapter and calling `propose_configuration_change` send no DDL and no commit on the engine session (3.8) |
| CE11-T15 | Killing the dedicated connection mid-call frees its locks, refuses the next effect, rolls back the uncommitted effect and leaves the engine session usable |
| CE11-T16 | Live MariaDB: the ALTER does not wait on the dedicated connection (no open transaction at dispatch); an injected open snapshot gives 1205 and a hold |
| CE11-T17 | Dedicated connection on another database, one whose lock the engine session cannot see, or one reporting another `@@hostname` or `@@port`, refuses `deployment_connection_mismatch` |
| CE11-T18 | `bench` binding under the production guard refuses `site_binding_not_tenant`; allowed under `test`; a `bench` binding with any state-row `tenant_id` refuses `site_binding_conflict` |
| CE11-T19 | `write_site_binding` (all callers): veto on a foreign state row; veto on matching state rows plus an audit `site_id` of another known tenant (cumulative); no veto on an unknown tenant's id; veto on a journal `site_id` of another tenant; write on the mapped site with neither; idempotent on rerun; `site_exists_different_target` on a different row; the adapter's `provision_site` never writes it |
| CE11-T20 | Static check: no code issues `UPDATE` on `adapter_site_binding`; the only `DELETE` and the only assignment of `@ce_site_rebind` are in `rebind_site`; nothing under `apps/engine/` issues either |
| CE11-T21 | The dedicated connection dropped during the ALTER: the completion is not appended as final; the deployment is held |
| CE11-T22 | Non-DDL effect (3.7): the order is locks, refresh, baseline and target reads, intent, effect, lock check, engine `COMMIT`, completion; a workflow commits once; a lock lost after the effect and before the `COMMIT` rolls the effect back (absent after request end) and holds; a crash after the `COMMIT` and before the completion leaves the intent, held for a person |
| CE11-T23 | `rebind_site`: refuses an undrained site and a different `tenant_id` or `kind`; applies the 2.2 vetoes; a retry after a crash past the `COMMIT` changes nothing and still emits the evidence; a row matching neither tuple refuses `site_exists_different_target`; a crash between `DELETE` and `COMMIT` leaves the old row; emits `site_rebound` and the audit record; a plain `DELETE` without the session variable signals |
| CE11-T24 | Cutover (2.5): a site whose store holds a slice 1 row under an id outside `C` and the host name (`t_beta` on `t-beta.other.test` bound to `t_gamma`) refuses `site_binding_conflict`, before and under the locks; ADR-0070's migration still reads the binding and runs on that site, and the site is accepted once it has rekeyed the row; a `default` evidence row does not refuse; host-name rows stay visible as holds and replays; static check: nothing under `apps/engine/` derives a lock key or a read id from `_tenant_of_site` or the label |
| CE11-T25 | Two concurrent first binds give one row (constant key); `UPDATE` and `DELETE` on the binding signal; a missing trigger fails the bind and refuses the RPC with `site_binding_unguarded` under the production guard too; the pre-flight (1.8) stops on a server where the provisioning user cannot create the triggers or the site user cannot see them, and binds nothing |
| CE11-T26 | Live MariaDB: the dedicated connection has no open transaction at the first `GET_LOCK`; a conflicting state row committed between the two reads refuses `site_binding_conflict` under the locks; so does a journal `site_id` not among the read ids |
| CE11-T27 | Missing store table refuses `deployment_store_missing`, creates nothing; static check: no `CREATE TABLE` for the audit or journal tables under `apps/engine/` outside the CE-SEC-013 migration's freeze step (3.8) |
| CE11-T28 | Workflow (3.7): a failure after an injected commit of a state row, an action master or a `workflow_state` column is held `RECOVERY_REQUIRED` by the wider read-back, never `FAILED_CLEAN`; the post-ALTER lock check failing rolls back the ORM writes and keeps the session |

### 6. Follow-up rows (partner lane, to be added by the coordinator)
- CE-SEC-011 slice 2 build: items 1.3 to 1.7, the read-side trigger check of 1.8, 2.4, 3 and the step 3 cutover procedure (2.5), with CE11-T01 to T18, T21, T22, T24, T26 to T28 and the engine parts of T20 and T25.
- `write_site_binding` with its table and triggers and the store tables (1.1, 1.2, 1.8, 3.8), `bind_existing_site` and `rebind_site` (1.9) in `services/provisioning/` (PLT-003), with the `TRIGGER` pre-flight (1.8, 2.3 step 1), CE11-T19, T23 and the provisioning parts of T20 and T25.

- Added to PLAN by this revision: CE-SEC-018 (non-DDL durable baselines, Q-686) and CE-SEC-019 (keyed MAC on the binding row, Q-685).

### 7. Conflicts with other Proposed ADRs (none is edited here)
- **ADR-0070.** A1, item 2.1 (`C = _tenant_of_site(...) or frappe.local.site`) and item 4.3 step 1 derive `C` from the host. Under this ADR, `C` is the binding's identity, read by the migration without the 1.4 audit-table clause (2.5). Item 1.6's "after `begin_fresh_read_view`" and item 4.3 step 5 become "a new snapshot on the dedicated connection" (3.4), with the engine-session refresh (3.2) before item 4.4's target and schema reads. Q-639 and its Consequences expect CE-SEC-011 to give non-DDL holds durable baselines; that is now CE-SEC-018 (Q-686). Its journal tables are created by provisioning, never at runtime (3.8); 2.5's freeze still creates an absent old table in the migration. Its item 1.7 lets a missing trigger pass in production; this ADR's binding triggers block (1.8, Q-687 answered). Whether ADR-0070's own triggers follow is for ADR-0070, not this ADR.
- **ADR-0040.** Step 3 must create the store tables (3.8) and write the binding and its triggers, Step 5 (`verify_adapter_state`) must verify both against the record, and `bind_existing_site` and `rebind_site` are new. `rebind_site` needs a drained site state that stops routing to one site; ADR-0040 does not define one today.
- **ADR-0068.** Item 3's one-row in-site record becomes this table; `siteId` is its `site_id` column.
- **ADR-0041.** The binding sits inside the tenant database, so a dump or restore keeps it with the data. A restore under another site name refuses until provisioning rebinds the site. ADR-0041's follow-up that puts engine effects on the store connection is not taken here: effects stay on the engine session, and the dedicated connection is a third one (3.3).

## Consequences
- **Easier.**
  - One identity per site, from one create-only record, on every path: RPC, backend, revert and recovery.
  - The slice 1 heuristic and the label parse go.
  - A deployment rolls back only its own uncommitted effect and discards the caller's session only when that rollback fails (3.7). Audit commits never publish the caller's writes. A write the counter misses is published early (3.2), and the effect commit publishes what Frappe writes during the effect (3.7).
- **Harder.**
  - One more connection per guarded call, and a short-lived one per backend call (1.6).
  - Every site must be bound before the read side ships.
  - Live MariaDB tests need a binding row.
  - A rename or restore under a new name is down until provisioning rebinds it, and a rebind needs a drained site (1.9).
  - The binding triggers need the `TRIGGER` privilege; without it every site blocks, so a pre-flight checks it before rollout (1.8, Q-687).
  - Step 3 needs a drained single-version cutover: all guarded calls stop for the switch (2.5, Q-688).
- **Must be done.** The rows in section 6, the ADR-0040, ADR-0068 and ADR-0070 updates in section 7, and the questions below.

## Alternatives rejected
- **Binding in `site_config.json`.** SQL writers cannot change it. But it sits outside the tenant database backup boundary that ADR-0041 relies on, and Frappe merges `common_site_config.json` into site config (UNVERIFIED on the pinned version), so a key placed there would bind every site to one tenant. Rejected by Eldon's Q-684 answer.
- **Reuse `tabChange Engine Blueprint State` or `adapter_sites`.** Both are rewritten on every operation, so neither is a create-only binding.
- **Keep the slice 1 evidence refusal.** It cannot see a site with no rows (Context).
- **Derive identity from the host label.** Forbidden by Q-311 (B1). Two spellings give two lock scopes.
- **A server-side write probe instead of a second connection** (`information_schema.INNODB_TRX.trx_rows_modified` for the engine session). It may need the `PROCESS` privilege (UNVERIFIED). It also still commits audit rows on the caller's session and still discards that session on lock loss.

## Open questions for Eldon (in `docs/open-questions.md`)
1. **Q-684 Binding store.** ANSWERED 2026-11-26 (Eldon): the one-row table (1.1). Was: should the binding be a one-row table in the site database, shared with ADR-0068's `siteId` (P, item 1.1)? Or `site_config.json`, which SQL writers cannot change but which sits outside the database backup and has the `common_site_config` merge risk?
2. **Q-685 Binding integrity.** ANSWERED 2026-11-26 (Eldon): unsigned for G1; the MAC is CE-SEC-019. Was: is an unsigned binding enough for G1 (P)? Database write as the site's user is already a full compromise of that site. Or should the row carry a MAC under ADR-0070's per-tenant key (this depends on Q-635), or a control-plane signature that the RPC path verifies?
3. **Q-686 Non-DDL baselines.** ANSWERED 2026-11-26 (Eldon): its own row, CE-SEC-018. Was: ADR-0070 Q-639 and its Consequences expect CE-SEC-011 to give property-setter, workflow and report holds durable baselines. This slice does not cover that. Should it move to its own row, for example beside CE-SEC-016 (P)? Or should it stay inside CE-SEC-011 as a slice 3?
4. **Q-687 Missing binding trigger.** ANSWERED 2026-11-26 (Eldon, for both founders; partner to confirm): block in production (fail closed), with a `TRIGGER` pre-flight before rollout (1.8, 2.3 step 1). Was: should a missing binding trigger block the site in production too (P, item 1.8)? Without the `TRIGGER` privilege every site then blocks. Or should it be reported and not block, as ADR-0070 item 1.7 says for its tables?
5. **Q-688 Rolling window.** ANSWERED 2026-11-26 (Eldon, for both founders; partner to confirm): a drained single-version cutover for step 3; the dual lock, the `L` read alias and the fence go (2.5). Was: accept the 2.5 residuals under B2 (no real sites) (P)? They are: a slice 1 apply call in flight when the first `C` row commits can miss a `C`-keyed hold (one call ceiling per site), and slice 1 revert is unfenced for the whole window. Accepting them also accepts the B1 exception that the label-parsed value is a lock key and read alias during the window. Or require a drained single-version cutover for step 3, which needs neither?

Also still open for a human (not settled here): accepting the early publication of 3.2, together with the 3.7 effect commit that is part of the same decision; accepting the idle-lock-connection residual during an ALTER (3.6); and B1, which needs the partner's agreement on #374.

## Supersedes
none (refines the CE-SEC-011 slice 1 site resolution; ADR-0070, ADR-0040 and ADR-0068 stay as written until revised)

## Revision 2 (review of Eldon at 396495f)
| Finding | Change | Where |
|---|---|---|
| M1 non-DDL commit point undefined | Order: refresh, reads, intent (corrected in revision 3), effect, lock check, engine `COMMIT`, completion append; rollback and hold on a lock loss before the `COMMIT`; crash after it held for a person; the `COMMIT` residual joins the 3.2 decision | 3.7; 3.1, 3.2, 3.4 item 4, 3.6, H7, H8, Consequences; CE11-T15, T22 |
| M2 rebind impossible as written | Provisioning-only `rebind_site`: drained site, 2.2 vetoes, same tenant and kind, `DELETE` plus `INSERT` in one transaction behind a session-variable trigger exception, security event and audit record; T20 allows only that path; it also fills `site_id` for ADR-0068 | 1.2, 1.9, H3, H9, section 6, ADR-0040 in section 7; CE11-T20, T23 |
| M3 rolling window reopens H1 | Fixed-order dual lock under `L` (host name or label-parsed id) after the `C` locks while the alias exists; `L` added to the read ids; no-deadlock argument; fence and residuals named (revert unfenced); drained cutover as fallback (Q-688; replaced in revision 3 by the cutover) | B1, 1.4, 1.7, 2.3, 2.5, H1, H5; CE11-T10, T24 |
| L1 no one-row guard | Constant key `id = 1` with `CHECK`; duplicate key answered as observe-then-act | 1.1, 1.2; CE11-T25 |
| L2 create-only by code only | `BEFORE UPDATE` and `BEFORE DELETE` SIGNAL triggers; a missing trigger blocks (`site_binding_unguarded`; the cited trigger answer corrected in revision 3, Q-687) | 1.8, 1.4, section 7; CE11-T25; Q-687 |
| L3 pre-lock transaction left open; conflict not re-checked | The pre-lock read ends with `ROLLBACK` before `GET_LOCK`; 2.4 re-runs the conflict check under the locks | 1.4, 2.4; CE11-T26 |
| L4 refusal table incomplete; bench conflict rule | Disposition column; `site_binding_not_tenant`, `deployment_connection_mismatch` and `site_binding_unguarded` added; a bench binding conflicts with any state-row `tenant_id` | 1.4; CE11-T18 |
| L5 vetoes read as exclusive | Vetoes cumulative; an unknown tenant's id merges into `C` through ADR-0070's `caller_chosen` rekey | 2.2; CE11-T19 |
| L6 weak same-server proof | `@@hostname` and `@@port` compared too; residual named (UNVERIFIED) | 3.3 item 4; CE11-T17 |
| Nit test order | T20 before T21; new tests T22 to T26 in order | section 5 |

## Revision 3 (Gemini security review at 8c679c0b; Eldon's re-review at 8c679c0; founder answers Q-684 to Q-688)
| Finding | Change | Where |
|---|---|---|
| Gemini M1, Eldon M4: refresh after the intent | Refresh first, then baseline and target reads, then the intent; a pending-write refusal leaves no `PREPARED` row. Supersedes the order in the Revision 2 M1 row | 3.7 item 1; CE11-T14, T22 |
| Gemini M2, Eldon M5: `CREATE TABLE` at adapter construction | All five `_ensure_audit_table` calls go; provisioning creates the store tables; runtime checks existence and refuses `deployment_store_missing`; propose is write-free only under 3.8 (corrected); 3.1 names the store DDL | 3.8, 1.2, 1.4, 1.5, 3.1, 3.2, H7, sections 6 and 7; CE11-T14, T27 |
| Gemini L1, Eldon L7: rebind retry | Observe then act on the full tuple under `FOR UPDATE`; a retry still emits the evidence | 1.9 item 3; CE11-T23 |
| Gemini L2, Eldon L8: revert site check order | Site check before `_already_finished` and the locks, and under the locks; `site_mismatch` | 1.5; CE11-T11 |
| Gemini L3, Eldon L9: workflow and post-ALTER commits | Workflow commits once; a wider read-back holds any commit Frappe makes earlier; the post-ALTER commit follows 3.7 steps 3 to 5 | 3.2, 3.7; CE11-T28 |
| Gemini L4, Eldon L10: backend read and journal tables | `_site_session` reads on a short-lived connection; the step's dedicated read is the 2.4 baseline; journal `site_id`s join the conflict check and the vetoes | 1.4, 1.6, 2.2; CE11-T08, T19, T26 |
| Eldon L11: record the founder answers | Q-684 to Q-688 marked answered here and RESOLVED in `docs/open-questions.md`; CE-SEC-018 and CE-SEC-019 named in section 6 and added to PLAN | questions, section 6 |
| Eldon N1: label-parsed `L` contends with another tenant's locks | No longer arises: the cutover removes every `L` lock | 2.5 |
| Eldon re-check of M1 to M3, L1 to L6 and the nit | M1 not closed (fixed above as M4 and L9); M2 closed, retry gap fixed (L7); M3 closed at 8c679c0, then replaced by the cutover (Q-688); L1 to L6 and the nit closed; L2's cited fail-closed trigger answer is not on main, so 1.8 now cites Q-687 | 1.8, 2.5, Revision 2 rows |
| Q-684 binding store | One-row table, shared with ADR-0068's `siteId`, create-only by triggers | 1.1, Alternatives |
| Q-685 binding integrity | Unsigned for G1; MAC is CE-SEC-019 | 1.1, 1.8, Out of scope, section 6 |
| Q-686 non-DDL baselines | Own row, CE-SEC-018 | 3.7, Out of scope, section 6 |
| Q-687 missing binding trigger | Blocks in production; `TRIGGER` pre-flight before rollout and before a new server's first site | 1.4, 1.8, 2.3 step 1, section 6, section 7, Consequences; CE11-T25 |
| Q-688 rolling window | Drained single-version cutover; dual lock, `L` read alias and fence removed; (P) slice 1 rows under another tenant-shaped id refuse `site_binding_conflict` until ADR-0070's rekey, which reads the binding without that clause; B1 exception gone | B1, 1.4, 1.7, 2.3, 2.5, H1, H5, Consequences; CE11-T10, T24 |
