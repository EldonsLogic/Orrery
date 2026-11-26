# ADR-0073: Change-engine tenant identity from a durable site binding, and a dedicated deployment connection

Status: Proposed
Owner: partner
Approved by: pending (security review by a different model, then Eldon line by line; Tier 3, RULES 42: touches tenancy and the audit path)

Plan ID: CE-SEC-011 (slice 2, G1, design only). No code until this ADR is Accepted. Internal document: it names the engine (ADR-0016). `CE/` means `apps/engine/change_engine/change_engine/`. Line numbers are at `c8fbac58`. Items marked **(P)** are proposed choices of this ADR; everything else restates code or an existing ADR. Facts about Frappe or MariaDB behaviour that the repo code does not show are marked UNVERIFIED.

## 0. Assumptions
- B1. Q-311 as answered by Eldon in open PR #374 (pending the partner's agreement): the canonical tenant id is `t_` plus lowercase letters, digits and underscores. The host-name label is derived from it (underscores to hyphens) and is only compared, never parsed back into a tenant id.
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
1.1 **(P) Store.** One table, `adapter_site_binding`, in the site's own database (ADR-0006, ADR-0041). It holds exactly one row: `binding_version` (1), `kind` (`tenant` or `bench`), `tenant_id` (grammar `t_[a-z0-9][a-z0-9_]{1,59}[a-z0-9]`, as `endpoints.py:2235` and `frappe_backend.py:73`; NULL for `bench`), `site_name` (the exact site name the binding was made for), `bound_by` (the provisioning `workflowId`), `bound_at`, and `site_id` (ADR-0068's opaque incarnation id, NULL until ADR-0068 lands). This is the one-row record of ADR-0068 item 3, defined here first, so a site never carries two bindings. Reasons for a fourth table rather than reuse: the existing carriers are rewritten on every operation, and the binding must be create-only.

1.2 **(P) Writer and moment.** One writer function, `write_site_binding`, writes the row. Its callers are provisioning only: ADR-0040 Step 3 (`create_site`), by `provisioning-site-init`, right after `init_adapter_state` and before the site serves any call; `bind_existing_site` (2.1); and the dev and test setup (`scripts/provision_tenant_site.py`, the conformance harness). The steady-state adapter, including its `provision_site`, never writes it. The value comes from the control-plane record (ADR-0040 item 2), never from a request and never from the host name. The write is `INSERT` only, and it always applies the veto rules of 2.2:
- an existing equal row is the post-condition (observe, then act, ADR-0040 item 4);
- an existing different row, or tenant evidence for another tenant, blocks with `site_exists_different_target`.
Neither the engine nor the adapter has any `UPDATE` or `DELETE` path on the table. A rename, a move or a restore to another site name is a provisioning action (ADR-0068 item 3, trusted provisioning) that writes a new row before the site serves again. Deprovisioning drops the row with the database (ADR-0040 item 8.5).

1.3 **(P) Bench and dev sites** get `kind = bench`, written by the dev setup script, with the site name as their identity. Under the production guard of ADR-0041 a `bench` binding refuses with `site_binding_not_tenant`. The in-memory path, where there is no resolved site and Frappe cannot be imported (`endpoints.py:647-653`, `:2293-2294`), keeps its behaviour in tests. Under the production guard it refuses too (P). No such guard exists on that path today.

1.4 **(P) How the RPC path reads it.** `_resolve_site_id` reads the binding on the dedicated connection (section 3) before any lock. The result is the identity `C`: `tenant_id` for a `tenant` binding, `site_name` for a `bench` binding. It refuses, with disposition `SITE_UNRESOLVABLE` and a stable reason code, when:

| Condition | `reason_code` |
|---|---|
| table missing, or no row | `site_binding_missing` |
| read fails, more than one row, unknown version, or a value outside the grammar | `site_binding_unreadable` |
| `site_name` differs from `frappe.local.site` (exact, byte for byte) | `site_binding_stale` |
| `tabChange Engine Blueprint State` or `adapter_sites` holds a `tenant_id` other than `C` | `site_binding_conflict` |
| the row read again under the locks (2.4) differs from the first read | `site_binding_changed` |

The existing `site_mismatch` (a caller value that is not `C`) and `invalid_site_id` stay (`:2289-2292`, `:2295-2297`). The caller never supplies the identity: a caller value is only compared. No identity is ever derived from the host name. `_tenant_of_site` and `FrappeSiteResolver.tenant_of` stop taking part in identity decisions (B1), and `_unmapped_site_refusal` is removed.

1.5 **(P) Every entry point that builds its own adapter** resolves `C` this way:
- `apply_configuration_change`, the property-setter, workflow and report endpoints, and `revert_configuration_change`;
- ADR-0070's recovery entry point, through `_resolve_site_id(None, ...)` (its item 4.3, step 1).

Revert refuses a record whose `site_id` is not among `C`'s read ids (1.7), and it takes its locks under `C`, never under the stored string. `propose_configuration_change` (`endpoints.py:226-446`) takes no lock and writes nothing, so it is unaffected.

1.6 **(P) Backend path.** `FrappeRuntimeBackend._site_session` (`frappe_backend.py:244-247`) resolves the site from `context.tenantId` and connects. It then reads the binding and requires `kind = tenant`, `tenant_id == context.tenantId` and `site_name ==` the resolved name. Otherwise it answers `tenant_not_found` (contract error table; the ADR-0041 misrouting answer) and logs `site_binding_mismatch` internally. `provision_site` finding no row answers `site_not_ready`; it never writes one (1.2).

1.7 **(P) Read ids.** `_read_site_ids(C)` adds the host name as a read-only legacy alias only when `binding.site_name == frappe.local.site` and the binding's identity is `C`. The alias is removed once ADR-0070's migration completes on the site.

### 2. Migration from the slice 1 evidence refusal
2.1 **(P) Source.** For every existing site, a one-shot provisioning operation, `bind_existing_site` (partner lane `services/provisioning/`, run per site), writes the row from the control-plane record. The site's database evidence only confirms the value or vetoes it. A veto blocks the site for a human, and nothing is written.

2.2 **(P) Cases** (the veto rules of `write_site_binding`).

| Site | Action |
|---|---|
| Has state rows (`tabChange Engine Blueprint State`, `adapter_sites`) | Bind when every `tenant_id` there equals the record's tenant. Any other value is a veto (a clone signal). |
| Has tenant-id-shaped audit `site_id`s only | Veto when one of them is another tenant the control plane knows. Other values are left to ADR-0070's rekey (`caller_chosen`, its item 2.1). |
| Custom `site_map` site with neither kind of row (the slice 1 gap) | Bind from the record: its `site_name` is the `site_map` value. From then on 1.6 checks the resolver against it on every backend call. |
| Default-domain tenant site with neither | Bind from the record, as above. |
| Bench or dev site | Write a `bench` row, or re-provision it (ADR-0051 item 6 precedent). |

2.3 **(P) Order.**
1. Ship the binding writer (Step 3) and `bind_existing_site`.
2. Bind and verify every site.
3. Ship the read side (1.4 to 1.7). An unbound site then refuses (fail closed; acceptable under B2).
4. Run ADR-0070's migration with `C` taken from the binding. This keeps ADR-0070 A1: CE-SEC-011 runs first, so nothing is rekeyed twice.
5. Remove the host-name alias (1.7).

2.4 **(P) Re-check under the locks.** Lock keys depend on `C`, so the binding is read before the locks. After the locks it is read again inside the dedicated connection's first snapshot (3.4) and compared column by column. A difference refuses with `site_binding_changed`, and nothing is written.

### 3. The dedicated deployment connection
3.1 **Why.** It removes or bounds the three engine-session hazards in the Context:
- the rollback that trusts a write counter which misses `REPLACE` (bounded by 3.2: the refresh commits instead of rolling back);
- audit commits that publish the caller's pending writes (removed);
- a lock loss that kills the caller's session (removed).
It also gives ADR-0070 and ADR-0068 the connection they already assume.

3.2 **(P) Scope.**

| On the dedicated connection | Stays on the engine session |
|---|---|
| The binding read (1.4, 2.4) | Engine effects through the ORM: Custom Field insert, property setter, workflow and report documents |
| Advisory locks: `GET_LOCK`, `IS_USED_LOCK`, `RELEASE_LOCK` | The DDL those effects send through `_admit_ddl` (`endpoints.py:1774`), with ADR-0070's dispatch binding on the sending session |
| Every locked read of the change-engine tables: holds, idempotency lookups, evidence, ADR-0070 head and site checks | Target and schema reads, before and after the effect (`read_apply_target`, `endpoints.py:1347`; the schema baseline), so the after-read sees the engine's own pending write, as today (for example `property_setter_engine.py:494-498`) |
| Every write to the change-engine audit and journal tables, and `CREATE TABLE IF NOT EXISTS` for them, each committed there (ADR-0070 item 1.8, ADR-0068 item 12) | The engine session's own `lock_wait_timeout` set and restore (slice 1), which bounds the ALTER's metadata-lock wait |

The engine session never reads or writes the audit and journal tables. It still needs a view opened after the locks, because the ORM's own reads and the target reads must see what the locks protect. So `begin_fresh_read_view` stays on the engine session, changed in one way (P): with the counter at zero it ends the transaction with `COMMIT`, not `ROLLBACK`. A counted pending write still refuses, as today. A write the counter misses (`REPLACE`) is then committed early rather than lost. The residual is that it is published before the caller's request ends. This reverses slice 1's "no commit fallback" (`:737-738`) for that case only, on purpose: silent loss is worse than early publication.

3.3 **(P) Lifecycle.**
1. Opened once per guarded call, after the caller and payload checks and before the binding read. Never pooled, never reused across calls, never shared across threads.
2. Same database user and database as the engine session, from the site configuration the engine already loaded. No new user and no new privilege. (UNVERIFIED: which Frappe helper opens a second connection on the pinned version.)
3. On open: `autocommit = 0`, `SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ`, `lock_wait_timeout` set and read back, and the session `wait_timeout` set above the call's ceiling (lock waits plus the statement limit) and read back, so the server does not drop the idle connection while the engine session runs an ALTER. It then checks that `DATABASE()` and `CURRENT_USER()` equal the engine session's.
4. Same server: after the first lock is granted, the engine session must see `IS_USED_LOCK(k)` equal to the dedicated connection's `CONNECTION_ID()`. Otherwise it refuses with `deployment_connection_mismatch`, because advisory locks on another server (a replica or a proxy route) would not serialise anything. `@@server_id` is not used: it is 1 by default on every server (UNVERIFIED on the pinned version).
5. Closed in the `finally`, after the verified release.
6. A third connection. The ADR-0041 store keeps its own connection (`mariadb_store.py:107-120`). ADR-0068 item 12's single transaction touches change-engine tables only, so it runs here.

3.4 **(P) Lock discipline (slice 1, moved).**
1. The idempotency lock, then the target lock, both on the dedicated connection, keys from `C` (`schema_reconciler.py:173-196`).
2. Then `START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY` on the dedicated connection for the locked reads, and the engine-session refresh of 3.2 before any target read or effect.
3. `_require_locks_held` (`endpoints.py:1410-1425`) runs on the dedicated connection: `IS_USED_LOCK(k) = CONNECTION_ID()` is the dedicated connection's id. It runs before every engine-session effect and before every journal append. The lock holder and the writer are different connections. The locks are cooperative between deployers, so that is enough as long as every guarded writer takes them (unchanged from slice 1).
4. The verified release frees the locks (`:800-822`). An unverified release closes the dedicated connection, which frees its locks, and leaves the engine session alone.

3.5 **(P) No self-block.** Before control passes to the engine session for any effect or DDL, the dedicated connection holds no open transaction: snapshots end with `ROLLBACK` and appends with `COMMIT`. The reason: an open transaction keeps a shared metadata lock on every table it has read until it ends, and row locks on what it has written. The engine session's ALTER would then wait on its own process. InnoDB sees no deadlock, only a timeout (1205). (UNVERIFIED live on the pinned MariaDB; documented MDL behaviour.) The rule holds even though the dedicated connection reads only change-engine tables, so that a later change to the scope cannot bring the problem back. A 1205 during an ALTER is held as today (ADR-0070 R17).

3.6 **(P) Failure modes.**

| Failure | Result |
|---|---|
| Open fails, or database/user/server mismatch | Refuse before anything (`engine_unavailable`, `deployment_connection_mismatch`) |
| Connection lost before the intent | Locks freed by the server; the next `_require_locks_held` fails; refuse, nothing sent |
| Connection lost after the intent, before or during the effect | No further effect is sent. **New residual:** today the lock holder is the connection running the ALTER, so the lock cannot be lost while that statement runs. Now the idle dedicated connection can be dropped (timeout, `KILL`) during the ALTER, and another deployer could take the lock. Bounded by the `wait_timeout` of 3.3; detected by `_require_locks_held` before the completion append, and the deployment is held `RECOVERY_REQUIRED`. A `KILL` by an operator stays open (UNVERIFIED live). |
| Journal append fails after the effect | Held, as today (ADR-0070 item 1.8) |
| Close fails | Release reported unverified, adapter unusable for the call; the server frees the locks when it drops the connection (timing UNVERIFIED) |
| Worker crash | Both connections drop; locks freed; the intent is visible to recovery |

### 4. Threats
| # | Threat | Addressed by | Tests |
|---|---|---|---|
| H1 | Mapped site with no evidence runs under its host name: a second lock and hold scope beside the tenant id | 1.4, 1.6, 2.2 | CE11-T01, T02, T03 |
| H2 | Spoofed `site_map` entry: tenant A's id pointed at B's site, or B's id at A's | 1.6: the binding's tenant and site name must both match | CE11-T08, T09 |
| H3 | Stale binding after a rename, move, or a clone or restore under another site name | `site_name` compared exactly (1.4); rebinding only by provisioning (1.2) | CE11-T04, T05 |
| H4 | Another tenant's dump restored into this site | Its binding names another site (`site_binding_stale`); its state rows conflict (`site_binding_conflict`) | CE11-T05, T06 |
| H5 | Caller-chosen identity, or identity parsed from the label | Caller value only compared; no parse (1.4, B1) | CE11-T07, T10 |
| H6 | Revert locks the scope of the stored string | 1.5 | CE11-T11 |
| H7 | Caller's pending writes rolled back (`REPLACE`) or published by an audit commit | 3.2; residual: an uncounted write is published early | CE11-T13, T14 |
| H8 | Lock loss kills the caller's session | 3.4 | CE11-T15 |

**Out of scope.**
- Anyone who can write the site database as its user, or run code as the engine's OS user, can rewrite the binding (Q-685).
- An untracked copy made outside provisioning (ADR-0068 item 3 assumption).
- The keyed evidence MAC (ADR-0070 section 3).
- Durable baselines for non-DDL holds (Q-686).
- Gateway authentication and `context.tenantId` stamping (contract item 2).

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
| CE11-T08 | Backend: `site_map` maps the context tenant to a site bound to another tenant; `tenant_not_found`, nothing written |
| CE11-T09 | Backend: resolver site name differs from the bound `site_name`; `tenant_not_found` |
| CE11-T10 | Default-domain site `t-beta.other.test` bound to `t_gamma` resolves to `t_gamma`; the label is never parsed |
| CE11-T11 | Revert of a host-name record locks under `C`; a record under a foreign id refuses |
| CE11-T12 | Binding changed between the pre-lock read and the under-lock read refuses `site_binding_changed` |
| CE11-T13 | Live MariaDB: a caller's uncommitted `REPLACE` on the engine session survives a deployment (committed by the refresh, never rolled back) |
| CE11-T14 | Live MariaDB: an audit or journal commit on the dedicated connection does not publish an engine-session write; a counted pending write still refuses |
| CE11-T15 | Killing the dedicated connection mid-call frees its locks, refuses the next effect and leaves the engine session usable |
| CE11-T16 | Live MariaDB: the ALTER does not wait on the dedicated connection (no open transaction at dispatch); an injected open snapshot gives 1205 and a hold |
| CE11-T17 | Dedicated connection on another database, or one whose lock the engine session cannot see, refuses `deployment_connection_mismatch` |
| CE11-T18 | `bench` binding under the production guard refuses `site_binding_not_tenant`; allowed under `test` |
| CE11-T19 | `write_site_binding` (all callers): veto on a foreign state row; write on the mapped site with neither; idempotent on rerun; `site_exists_different_target` on a different row; the adapter's `provision_site` never writes it |
| CE11-T21 | The dedicated connection dropped during the ALTER: the completion is not appended as final; the deployment is held |
| CE11-T20 | No engine or adapter code issues `UPDATE` or `DELETE` on `adapter_site_binding` (static check) |

### 6. Follow-up rows (partner lane, to be added by the coordinator)
- CE-SEC-011 slice 2 build: items 1, 2.4 and 3, with CE11-T01 to T18, T20 and T21.
- `bind_existing_site` and the Step 3 writer in `services/provisioning/` (PLT-003), with CE11-T19.

### 7. Conflicts with other Proposed ADRs (none is edited here)
- **ADR-0070.** A1, item 2.1 (`C = _tenant_of_site(...) or frappe.local.site`) and item 4.3 step 1 derive `C` from the host. Under this ADR, `C` is the binding's identity. Item 1.6's "after `begin_fresh_read_view`" and item 4.3 step 5 become "a new snapshot on the dedicated connection" (3.4), with the engine-session refresh (3.2) before item 4.4's target and schema reads. Q-639 and its Consequences expect CE-SEC-011 to give non-DDL holds durable baselines; this slice does not (Q-686).
- **ADR-0040.** Step 3 must write the binding, Step 5 (`verify_adapter_state`) must verify it against the record, and a `bind_existing_site` operation is new.
- **ADR-0068.** Item 3's one-row in-site record becomes this table; `siteId` is its `site_id` column.
- **ADR-0041.** The binding sits inside the tenant database, so a dump or restore keeps it with the data. A restore under another site name refuses until provisioning rebinds the site. ADR-0041's follow-up that puts engine effects on the store connection is not taken here: effects stay on the engine session, and the dedicated connection is a third one (3.3).

## Consequences
- **Easier.**
  - One identity per site, from one create-only record, on every path: RPC, backend, revert and recovery.
  - The slice 1 heuristic and the label parse go.
  - The caller's session is never rolled back or discarded by a deployment, and audit commits never publish its writes. A write the counter misses is published early (3.2).
- **Harder.**
  - One more connection per guarded call.
  - Every site must be bound before the read side ships.
  - Live MariaDB tests need a binding row.
  - A rename or restore under a new name is down until provisioning rebinds it.
- **Must be done.** The rows in section 6, the ADR-0040, ADR-0068 and ADR-0070 updates in section 7, and the questions below.

## Alternatives rejected
- **Binding in `site_config.json`.** SQL writers cannot change it. But it sits outside the tenant database backup boundary that ADR-0041 relies on, and Frappe merges `common_site_config.json` into site config (UNVERIFIED on the pinned version), so a key placed there would bind every site to one tenant. Kept as an option in Q-684.
- **Reuse `tabChange Engine Blueprint State` or `adapter_sites`.** Both are rewritten on every operation, so neither is a create-only binding.
- **Keep the slice 1 evidence refusal.** It cannot see a site with no rows (Context).
- **Derive identity from the host label.** Forbidden by Q-311 (B1). Two spellings give two lock scopes.
- **A server-side write probe instead of a second connection** (`information_schema.INNODB_TRX.trx_rows_modified` for the engine session). It may need the `PROCESS` privilege (UNVERIFIED). It also still commits audit rows on the caller's session and still discards that session on lock loss.

## Open questions for Eldon (the coordinator adds them to `docs/open-questions.md`)
1. **Q-684 Binding store.** Should the binding be a one-row table in the site database, shared with ADR-0068's `siteId` (P, item 1.1)? Or `site_config.json`, which SQL writers cannot change but which sits outside the database backup and has the `common_site_config` merge risk?
2. **Q-685 Binding integrity.** Is an unsigned binding enough for G1 (P)? Database write as the site's user is already a full compromise of that site. Or should the row carry a MAC under ADR-0070's per-tenant key (this depends on Q-635), or a control-plane signature that the RPC path verifies?
3. **Q-686 Non-DDL baselines.** ADR-0070 Q-639 and its Consequences expect CE-SEC-011 to give property-setter, workflow and report holds durable baselines. This slice does not cover that. Should it move to its own row, for example beside CE-SEC-016 (P)? Or should it stay inside CE-SEC-011 as a slice 3?

## Supersedes
none (refines the CE-SEC-011 slice 1 site resolution; ADR-0070, ADR-0040 and ADR-0068 stay as written until revised)
