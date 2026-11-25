# ADR-0070: Change-engine deployment journal, keyed MAC, legacy rekey migration and locked recovery entry point

Status: Proposed
Owner: partner
Approved by: pending (security review by a different model, then Eldon line by line; Tier 3, RULES 42: touches audit, tenancy and a new API surface)

Plan IDs: CE-SEC-009 and CE-SEC-010 (G1, design only), plus the keyed MAC from CE-SEC-011. No code until this ADR is Accepted. Internal document: it names the engine (ADR-0016). `CE/` means `apps/engine/change_engine/change_engine/`. Line numbers are at `b28a8709`. Items marked **(P)** are proposed choices of this ADR; everything else restates code or an existing ADR.

## 0. Assumptions and questions for Eldon

Assumptions (each is a reading I chose; say if it is wrong):
- A1. The canonical identity of a site is what `_resolve_site_id` returns with no caller value: the tenant id the backend binds (`t-alpha.<domain>` gives `t_alpha`, `CE/api/endpoints.py:2142-2187`), else the site name. Custom `site_map` sites get their tenant id from CE-SEC-011 first; the migration (section 2) runs after that, so it never rekeys twice.
- A2. Each engine site has its own database, and every row in that database's audit table describes that site, whatever `site_id` string it carries. UNVERIFIED for our provisioning (U5).
- A3. No real customer site holds legacy rows today (PR #322 text, marked HUMAN-ONLY there). Dev and pilot benches may, and the migration must handle them anyway.
- A4. This ADR covers the change-engine deployment hold (`PREPARED` / `RECOVERY_REQUIRED` rows). The adapter's own site state `recovery_required` (ADR-0041, `adapter_sites`) is a separate layer and is not cleared here.
- A5. ADR-0041 (journal on the tenant database) and ADR-0068 (signed grant, `siteId` incarnation) are Proposed. This ADR builds on them as written and changes neither.

Questions for Eldon (the coordinator numbers them):
1. **Key custody.** A per-tenant HMAC key held in engine-worker memory and read from the secret store (P, item 3.1), or a KMS-held MAC key (no key in memory, but one network call per verified row on the hold lookup)? With the chosen option, production deployments are refused until SEC-002's store exists. Is that acceptable before the first pilot?
2. **Inferred provenance.** When the live table is exactly the baseline plus the approved column, the dispatching connection is gone and the metadata matches, may recovery finalize `APPLIED` with `provenance: inferred` (P, row R13)? Or must it hold for a human? An out-of-band desk change that adds the identical field is indistinguishable.
3. **Migrated holds.** May recovery finalize a migrated CE-SEC-008-format hold whose unkeyed digest still verifies? Or does every migrated hold stay held (P)?
4. **Recovery caller.** `System Manager` only (P), or a dedicated role held only by a platform service user? Should the control plane later trigger recovery through an adapter contract operation (your `contracts/` lane, a later gate)?
5. **Scope.** Recovery v1 covers physical-DDL field deployments only. Property-setter, workflow and report holds stay held until CE-SEC-011 gives them durable baselines (P). Acceptable?
6. **Rollback residual.** A consistent rollback (old head row plus deleted recent rows) is not detectable locally (item 3.5). Accept it until SEC-008's off-box anchor (your G2 row)?
7. **Identity.** Key the journal on the tenant id (P), with ADR-0068's opaque `siteId` added as a column once that ADR is Accepted? Or wait and key on `siteId`?

## Context
- CE-SEC-008 (PRs #322, #331) made the guarded field path durable. It kept the evidence inside the old audit table `tabChange Engine Audit` (`CE/api/endpoints.py:459-483`, created at `:697-721`). One main row per deployment is updated in place (status, `outcome_json`; `:1635-1660`, `:879-902`). Evidence rows sit beside it under the key `<dep>#evidence`, with statuses `EVIDENCE_BASELINE`, `EVIDENCE_DDL_DISPATCH` and `EVIDENCE_DDL_COMPLETED` (`:1394-1409`).
- The plan column carries an unkeyed SHA-256 over id, site, doctype, field, payload hash, plan and baseline (`_bind_digest`, `:497-506`). Journal rows chain to it (`_row_digest`, `:509-512`). `load_durable_evidence` verifies all of it (`:1425-1511`). A legacy plain-list plan loads as `verified: False` and always holds (`:1275-1278`).
- Known limits, stated in the code and in Eldon's reviews of #322 and #331:
  - the digest is unkeyed, so anyone who can write the table can recompute it;
  - deleting the journal tail is not detected (probe T8);
  - `status`, `outcome_json`, `base_revision_hash` and `idempotency_key` sit outside the digest, so PREPARED to APPLIED lifts a hold undetected (T12 to T14);
  - replay and revert do not check the digest (N4).
- The index on `(site_id, idempotency_key)` is not unique (`:716`). Duplicate keys are caught only after the fact, by "one idempotency key is bound to several payloads" (`:957-958`).
- **Identity.** `_read_site_ids` reads the host name as a read-only alias for rows written before the single-identity rule (`:2152-2163`). Rows under a bare slug (`t-alpha`) or under any caller-chosen id are invisible to the hold and replay lookups (log `2026-11-25-partner-claude-code-ce-sec-008-deploy-path-durability.md:128`).
- **No release path.** Nothing releases a held deployment. `revert_configuration_change` refuses a held one (`:2955-2967`). The reconciler sends every restarted deployment to `RECOVERY_REQUIRED`, because provenance is never computed after a restart (`:1240-1252`; `CE/guarded_apply/schema_reconciler.py:595-603`). A held table therefore stays blocked forever.
- Eldon's carry-overs into CE-SEC-009: compare the stored doctype and site with the request (F4), and hold on `verified: False` (N3).

## Decision

### 1. Journal tables (CE-SEC-010)
1.1 **(P) Location.** Three plain InnoDB tables, utf8mb4, in the tenant site database beside the schema they describe (ADR-0041). A dump or restore returns journal and schema together.
- They are created by a patch in `CE/patches.txt`, not by `CREATE TABLE IF NOT EXISTS` on every adapter construction.
- They are not engine document types, so no desk view or REST resource exists for them. Their names join the protected list in `CE/guarded_apply/safety_guardrails.py:53-69`.

1.2 **(P) `tabChange Engine Deployment`.** One row per deployment, insert-only.

| Column | Type | Note |
|---|---|---|
| `site_id` | VARCHAR(140) NOT NULL | canonical identity (A1) |
| `deployment_id` | VARCHAR(140) NOT NULL | `caller_id_problem` grammar |
| `idempotency_key` | VARCHAR(140) NOT NULL | |
| `payload_hash` | CHAR(64) NOT NULL | |
| `engine_kind` | ENUM(`field`, `property_setter`, `workflow`, `report`) | |
| `doctype`, `fieldname` | VARCHAR(140) | |
| `base_revision_hash` | VARCHAR(64) | |
| `approved_plan` | LONGTEXT | JSON list of statements |
| `dispatch_connection_id` | BIGINT NULL | `CONNECTION_ID()` of the deployment session at prepare (field only) |
| `site_seq` | BIGINT NOT NULL | gap-free position of this deployment in its site (item 3.5) |
| `origin` | ENUM(`current`, `legacy`) | `legacy` only from the migration |
| `legacy_site_id`, `legacy_status` | VARCHAR NULL | the original values, kept for audit |
| `created_at` | DATETIME(6) | |
| `mac` | VARCHAR(80) NOT NULL | `<kid>:<hex>` |

Keys:
- `PRIMARY KEY (site_id, deployment_id)`;
- `UNIQUE uq_site_idem (site_id, idempotency_key)`, the database-level guarantee CE-SEC-010 asks for;
- `UNIQUE uq_site_seq (site_id, site_seq)`;
- `INDEX (site_id, doctype)`.

There is no status column (item 1.4).

1.3 **(P) `tabChange Engine Deployment Event`.** Append-only.
- Columns: `site_id`, `deployment_id`, `seq` (gap-free from 1 per deployment), `kind`, `stmt_seq` (NULL unless a dispatch kind), `payload` (canonical JSON), `actor`, `created_at`, `prev_mac` (the `mac` of event `seq-1`, or of the deployment row for `seq = 1`) and `mac`.
- `kind` is one of `baseline`, `dispatch_intent`, `dispatch_completed`, `outcome` or `recovery_attempt`.
- Key: `PRIMARY KEY (site_id, deployment_id, seq)`.
- The `payload` of an `outcome` event carries `status`, `final` (bool), the reconciler disposition and, after recovery, the classification row.

1.4 **(P) Status is derived, never stored.** A deployment's status is the status of its latest `outcome` event, or `PREPARED` when it has none.
- Final statuses: `APPLIED`, `ALREADY_APPLIED`, `FAILED_CLEAN`, `REJECTED`, `ROLLED_BACK`, `QUARANTINED`.
- `RECOVERY_REQUIRED` is a non-final outcome.
- Today's in-place updates (`persist_final_outcome_and_audit`, `mark_recovery_required`, `update_deployment_status`) become appended `outcome` events. A deleted outcome therefore reads as held, which fails closed.

1.5 **(P) `tabChange Engine Journal Head`.** One row per site: `site_id` (PK), `deployment_count`, `migration_state` (`none`, `blocked` or `complete`), `migration_source_sha256`, `updated_at` and `mac`. Every prepare updates it in the same transaction as the new deployment row: `SELECT ... FOR UPDATE`, then `deployment_count + 1 = site_seq`.

1.6 **(P) Triggers.** They guard against code bugs and naive SQL, not against an attacker. The MAC (item 3) is the integrity control.
- `BEFORE UPDATE` and `BEFORE DELETE` on the deployment and event tables `SIGNAL SQLSTATE '45000'`.
- On the head table, `BEFORE UPDATE` allows only `deployment_count = OLD + 1` (or a migration-state change) with `site_id` unchanged, and `BEFORE DELETE` signals.
- They are required in dev and CI. In production a missing trigger is reported by the health check but does not block, because creating a trigger may need privileges we do not hold (U1, U2).

1.7 **Writers and readers.** All four engines already write through `FrappeDeploymentAdapter`. Its prepare, finalize, hold, replay, revert-record and evidence functions switch to these tables in one change, so no engine writes the old table afterwards.
- The health check (`CE/adapter/frappe_backend.py:521-528`) and the phase-0 proof (`CE/proofs/phase0_bench_proof.py:1117`) switch too.
- The duplicate-key insert maps to the existing `DeploymentIntentConflictError` path (`schema_reconciler.py:387-414`).
- Replay and revert verify the MAC before using a row (closes N4).
- The hold lookup (item 4.5) returns held for any deployment on the target without a verified final outcome.

### 2. Migration of legacy rows (CE-SEC-010)
2.1 **(P) Canonical identity.** `C = _tenant_of_site(frappe.local.site) or frappe.local.site` (A1). Under A2 every legacy row in this database is rekeyed to `C`. The reason is recorded per row, comparing with `_collation_fold`:
- `canonical`: the row already says `C`;
- `host_alias`: the host name;
- `slug_alias`: the host label, such as `t-alpha`;
- `caller_chosen`: anything else.

The original value goes to `legacy_site_id`.

2.2 **Mapping.**
- Each main row (status not `EVIDENCE_*`, no `#` in its name) becomes one deployment row with `origin = legacy`, plus one `outcome` event carrying its old status and outcome, if any.
- Each evidence row `<dep>#<suffix>` becomes an event of its kind, under its main row, in name order. The old SHA-256 digest is copied into the payload.
- `payload_hash` is copied, never recomputed. A retry of a legacy key therefore still gets `IDEMPOTENCY_CONFLICT`, as today (log line 118). That fails closed.
- `site_seq` follows `created_at`, then `name`.

2.3 **(P) MAC without laundering.** Migrated rows are MAC'd so that later tampering is detected. `origin = legacy` is inside the MAC'd bytes, and recovery always holds a legacy deployment (R7). Tampering that happened before the migration is never turned into trusted evidence.

2.4 **(P) Ambiguity fails closed for the whole site.** Any of the following sets `migration_state = blocked` and writes nothing else:
- two main rows that fold to the same `(C, idempotency_key)` or the same `deployment_id`;
- an evidence row with no main row, an unparseable name or an unknown status;
- a main row whose status is not a known value;
- a source read error.

While a site is `blocked` or `none`, every deployment and every recovery on it refuses with `journal_migration_pending`.
- A site whose old table is absent or empty becomes `complete` at once.
- The patch records `blocked` and returns success, so `bench migrate` is not stopped for unrelated apps.
- Resolution is a reviewed runbook. On a dev bench, rebuild the site.

2.5 **Idempotent and atomic.**
- The table DDL runs first, in its own step. The row copy and the head update then run in one transaction with no DDL inside.
- A crash leaves no partial rows.
- `migration_source_sha256` is a SHA-256 over the canonical dump of all source rows. A re-run with `complete` and the same hash is a no-op. A changed source refuses with `migration_source_changed`.
- The migration never runs DDL against business tables, never dispatches a journalled statement and never finalizes anything.
- The old table is kept read-only for history and is never dropped by this ADR.

2.6 **Dry run.** `bench --site <site> execute change_engine.patches.ce_sec_010_journal.dry_run` (P). It prints JSON:
- `C`;
- counts by mapping reason and by evidence kind;
- held deployment ids;
- each ambiguous group with its reason;
- `would_complete`;
- the source hash.

It writes nothing, and its output never goes into the repo (synthetic data only on dev hosts).

### 3. Keyed MAC (CE-SEC-011 part, CE-SEC-010 store)
3.1 **(P) Key.** One 256-bit HMAC-SHA256 key per tenant per version, a new ADR-0038 inventory entry. The number is allocated by the coordinator; ADR-0068 proposes `S24`.
- It lives in the secret store, is read by the engine workers of the tenant's bench pool (the same reach as `S21`) and is held only in memory.
- It is never written to the site database, `site_config.json`, logs or responses.
- Until SEC-002 delivers a store, a `JournalKeyProvider` interface has a dev and test provider (throwaway keys, `S20`). A production adapter without a provider refuses to prepare (`journal_key_unavailable`), and recovery refuses too.

3.2 **Construction.** `mac = kid + ":" + hex(HMAC-SHA256(K[tenant, kid], canonical_json(...)))`.
- The MAC'd value is `{"v": 1, "t": <table tag>, "site": site_id, all columns except mac, "prev": prev_mac}`, in contract 5.8 canonical form.
- Comparison is constant-time.
- The table tag separates domains. Because the site and the per-tenant key are inside, a row copied from another tenant's database fails.

3.3 **(P) Rotation and versioning.**
- New writes use the current `kid`.
- Older `kid`s stay verify-only for as long as any row references them, like `S16` verification keys.
- Rotation is yearly and on suspected compromise.
- A compromised `kid` goes on a deny list. Rows under it read as unverified, so their deployments hold and their targets block until an incident runbook (follow-up) re-attests them.

3.4 **What it detects.**
- An edit to any column of any journal row, including status, outcome, base revision and idempotency key (closes T12 to T14).
- A forged event or deployment row.
- A row transplanted from another tenant.
- An event deleted or reordered inside a deployment (gap-free `seq` plus `prev_mac`; covers the M19 position mutant).
- A deleted deployment that is not the latest one (`site_seq` gap).
- A deleted latest deployment when the head was not rewound (`deployment_count` mismatch).

Every detection reads as held (`evidence_invalid`) and never as absent. A head mismatch holds every target on the site.

3.5 **What it does not detect, and why the tail is mostly harmless.**
- **Tail truncation inside a deployment.** Removing the final outcome reads as held. Removing dispatch rows cannot make recovery finalize `APPLIED` on a false claim: recovery decides from the live schema against the MAC'd baseline, and reads the dispatching connection from the deployment row, not the events.
- **Consistent rollback is NOT detected.** An attacker restores an earlier valid head row they saved, and deletes every later deployment. Locally this is indistinguishable from a legitimate restore (ADR-0041). Only an off-box anchor of the head MAC closes it (SEC-008, Eldon G2; question 6).
- **Anyone holding the key** (code execution in an engine worker of the pool) can forge rows. This is the same residual as `S05` in ADR-0038.

### 4. Recovery entry point (CE-SEC-009)
4.1 **(P) Shape.** It is an internal change-engine RPC. It is not customer-facing, not in any contract and never routed by the gateway (ADR-0016).

```
recover_deployment(deployment_id: str, mode: "classify" | "finalize" = "classify",
                   lock_wait_seconds: int = 3) -> {
  deployment_id, mode, status: APPLIED | FAILED_CLEAN | RECOVERY_REQUIRED | REJECTED,
  recovered: bool,         # true only when THIS call appended the final outcome
  classification: "R1".."R16", reason_code, stage: "RECOVER", execution_time_ms }
```

- `classify` writes only a `recovery_attempt` event. `finalize` also appends the final `outcome` when the row allows it.
- Responses carry stable codes only: no exception text, SQL, schema contents or engine names (`_stable_reason_code`, `CE/api/endpoints.py:2092`).
- Whitelisted POST-only (U8). Tests inject an adapter through a non-whitelisted `_recover_deployment_impl`, never through RPC kwargs.

4.2 **(P) Caller.**
- Roles come only from the authenticated session, via `get_current_user_roles` inside the engine.
- The caller needs `RECOVERY_ROLES = {"System Manager"}` (question 4).
- Refused before any read when present: `site_id`, `site`, `user_roles`, `caller_roles`, `actor`, `governance_tier`, `adapter`, `db`, `status` and `outcome`. The caller cannot choose the site, the roles or the result; classification is deterministic from evidence.
- An unauthorised caller gets the same refusal for known and unknown ids, and nothing is read.

4.3 **Locks and view.** The function:
1. Resolves `C` with `_resolve_site_id(None, ...)` and refuses on `journal_migration_pending`.
2. Reads the deployment row by `(C, deployment_id)` and verifies its MAC. This settles F4: the site is part of the key, and the doctype comes from the stored row, never from the caller.
3. Takes the same two locks in the same order as `execute_single_field_deployment` (`schema_reconciler.py:217-249`): the idempotency lock for `(C, stored idempotency_key)`, then the target lock for `(C, stored doctype)`.
4. Calls `begin_fresh_read_view`, then re-reads and re-verifies the row and all its events.

The function runs on CE-SEC-011's dedicated deployment connection. Every exit uses the verified release, and an unverified release discards the session (CE-SEC-008).

4.4 **Fresh complete read, under the locks:**
- `_read_table_schema(doctype)`: every fingerprint key, meaning columns, order, indexes, constraints, checks, triggers and table options (`CE/api/endpoints.py:1019`);
- the field's `tabCustom Field` row;
- `has_col`;
- dispatcher liveness: `SELECT ID FROM information_schema.PROCESSLIST WHERE ID = dispatch_connection_id` (U3).

Any error, an empty answer where a row must exist, or a partial fingerprint is "unreadable", never "equal".

4.5 **Classification table.** The rows are checked in order and the first match wins. B is the MAC'd baseline, L the live fingerprint, M the metadata row and D the dispatched statements from the events.

| Row | State | Result | Write |
|---|---|---|---|
| R1 | caller lacks the role, or a refused parameter is present | REJECTED `not_permitted` | none (server log only) |
| R2 | id fails `caller_id_problem` or lies in the evidence namespace | REJECTED `invalid_deployment_id` | none |
| R3 | site migration not `complete` | REJECTED `journal_migration_pending` | none |
| R4 | no deployment row under `(C, id)` | REJECTED `not_found` | none |
| R5 | journal key unavailable | REJECTED `journal_key_unavailable` | none |
| R6 | a lock is not granted, or the fresh view fails | REJECTED `locked` / `engine_unavailable` | none |
| R7 | latest outcome is final and verified | its stored status, `already_final` (idempotent) | `recovery_attempt` |
| R8 | MAC, chain, gap, head or parse failure | RECOVERY_REQUIRED `evidence_invalid` | `recovery_attempt` |
| R9 | `origin = legacy` (N3: `verified: False` holds) | RECOVERY_REQUIRED `evidence_unverified` | `recovery_attempt` |
| R10 | `engine_kind` is not `field`, or a field deployment has no baseline | RECOVERY_REQUIRED `kind_not_recoverable` | `recovery_attempt` |
| R11 | schema, metadata or liveness read failed or incomplete | RECOVERY_REQUIRED `schema_unreadable` | `recovery_attempt` |
| R12 | D is not a prefix of the approved plan | RECOVERY_REQUIRED `unapproved_dispatch` | `recovery_attempt` |
| R13 | D non-empty and the dispatching connection is alive or unknown | RECOVERY_REQUIRED `dispatch_may_be_in_flight` (retry later) | `recovery_attempt` |
| R14 | L == B on every key, M absent, has_col false | FAILED_CLEAN `baseline_verified` | final `outcome` (finalize mode) |
| R15 | L == B plus exactly the approved column (`new_column_matches_plan`, indexes unchanged, `assess_applied_ddl` clean), M present and matching, D equals the full approved plan, dispatcher gone | APPLIED `provenance: inferred` (question 2), then the doctype cache is cleared | final `outcome` (finalize mode) |
| R16 | anything else (orphan metadata, orphan column, a definition or index difference, an unapproved side effect) | RECOVERY_REQUIRED, with the reconciler's disposition | `recovery_attempt` |

4.6 **Never re-runs DDL.**
- The recovery module imports no dispatch function and is handed no field definition.
- Its SQL is restricted to `SELECT`, `GET_LOCK`, `RELEASE_LOCK`, `IS_USED_LOCK`, `CONNECTION_ID`, the head `FOR UPDATE` and `INSERT` into the event table.
- A test recorder fails on anything else.
- `R15` finalizes only what already exists. Nothing is created, dropped or repaired.

4.7 **Audit and idempotency.** For an authorised caller and an existing deployment, every call appends one MAC'd `recovery_attempt` event with:
- the session user and their roles;
- the mode and classification row;
- the reason code;
- the SHA-256 of the encoded live fingerprint;
- dispatcher liveness.

Finalization appends one `outcome` event (`final: true`, actor, classification) in the same transaction. A second call returns R7. Two concurrent calls serialize on the locks, and the second sees R7.

### 5. Threats and proposed tests
`bench:` means a real MariaDB test (CI service per ADR-0041).

| Threat | Control | Test |
|---|---|---|
| Status edit lifts a hold (T12) | outcome events MAC'd; hold lookup verifies | `test_ce_sec_010_forged_or_edited_outcome_keeps_target_held` |
| Base revision or key edited (T13, T14); replay or revert on an edited row (N4) | deployment row MAC'd; replay and revert verify | `test_ce_sec_010_edited_deployment_row_refused_by_replay_revert_and_recovery` |
| Held deployment deleted to unblock its table | `site_seq` plus head count | `test_ce_sec_010_deleted_deployment_holds_every_target_on_site` |
| Event deleted, reordered or renumbered (M19) | gap-free `seq`, `prev_mac` | `test_ce_sec_010_event_gap_or_reorder_is_evidence_invalid` |
| Dispatch tail truncated to fake "nothing ran" | decision from L against B, dispatcher id in the deployment row | `test_ce_sec_009_truncated_dispatch_tail_with_changed_schema_holds` |
| Row copied from another tenant's database | per-tenant key, site in the MAC | `test_ce_sec_010_row_from_other_tenant_fails_mac` |
| Two prepares with one key race | `UNIQUE (site_id, idempotency_key)` | bench: `test_ce_sec_010_concurrent_same_key_second_insert_refused` |
| Alias spelling opens a second scope | migration rekeys; writes use `C` only | `test_ce_sec_010_migration_rekeys_host_slug_and_caller_ids` |
| Ambiguous legacy rows merged silently | site `blocked`, deployments refused | `test_ce_sec_010_collision_or_orphan_blocks_site_and_dry_run_reports_it` |
| Migration launders tampered rows | `origin = legacy` inside the MAC; R9 | `test_ce_sec_009_legacy_origin_always_holds` |
| Partial or repeated migration | one transaction; source hash | `test_ce_sec_010_migration_crash_leaves_no_rows`, `test_ce_sec_010_rerun_noop_and_changed_source_refused` |
| Recovery runs DDL | no dispatch import; SQL allow-list | `test_ce_sec_009_recovery_issues_no_ddl_in_any_row` |
| Recovery races a deployment or another recovery | both locks from the stored row; fresh view | `test_ce_sec_009_blocks_while_target_lock_held`, `test_ce_sec_009_two_recoveries_one_finalizes` |
| Finalize while an ALTER still runs server-side | dispatcher liveness (R13) | `test_ce_sec_009_live_or_unknown_dispatcher_holds`; bench: `test_ce_sec_009_killed_client_alter_still_running_holds` |
| Partial schema read taken as "equal" | complete read or R11 | `test_ce_sec_009_partial_fingerprint_holds` |
| Caller chooses site, roles or outcome | refused parameters; session roles only | `test_ce_sec_009_caller_context_params_refused`, `test_ce_sec_009_non_system_manager_refused_without_reading` |
| Existence probing | identical refusal before any read | `test_ce_sec_009_unauthorised_same_response_for_known_and_unknown_id` |
| Evidence of another site or table (F4) | key `(C, id)`; doctype from the stored row | `test_ce_sec_009_other_site_row_not_found_and_doctype_from_store` |
| Key missing, or a `kid` compromised | fail closed; deny list | `test_ce_sec_010_missing_key_refuses_prepare_and_recovery`, `test_ce_sec_010_denied_kid_holds` |
| Out-of-band identical column finalized as APPLIED | accepted residual, flagged `inferred` (question 2) | `test_ce_sec_009_identical_out_of_band_column_is_inferred` |
| Update or delete through plain SQL | triggers (dev, CI) | bench: `test_ce_sec_010_update_and_delete_signal` |
| Recovery reached from outside | not routed (ADR-0016) | `test_ce_sec_009_gateway_has_no_route_to_recover_deployment` (`services/gateway/`) |
| Engine names or raw text in a response | stable codes | `test_ce_sec_009_responses_carry_no_engine_names_or_exception_text` |
| Consistent rollback | none locally (item 3.5) | residual; SEC-008 |

### 6. Proposed follow-up rows (partner lane, G1; IDs for the coordinator to confirm)
Each depends only on partner rows (ADR-0025):
- `| CE-SEC-012 | Change engine: deployment journal tables, triggers and keyed MAC per ADR-0070 sections 1 and 3 (JournalKeyProvider with dev and test providers, production refuses without a key); switch every FrappeDeploymentAdapter writer and reader (prepare, finalize, hold, replay, revert record, evidence, health check, phase-0 proof) to the journal; refuse deployments while the site's migration is not complete, and mark an absent or empty old table complete; add the key to the secrets inventory | Security | G1 | CE-SEC-010,CE-SEC-011 | partner | todo |`
- `| CE-SEC-013 | Change engine: legacy audit rows to journal migration per ADR-0070 section 2 (rekey to the canonical identity, legacy origin, whole-site block on ambiguity, one transaction, source hash, dry-run report), with the section 5 migration tests on real MariaDB | Security | G1 | CE-SEC-012 | partner | todo |`
- `| CE-SEC-014 | Change engine: locked recovery entry point per ADR-0070 section 4 (classification R1 to R16, never DDL, audit events, System Manager only, no route in the gateway), with the section 5 recovery tests | Security | G1 | CE-SEC-012,CE-SEC-013 | partner | todo |`

### 7. UNVERIFIED claims
- U1. In MariaDB with binary logging on, `CREATE TRIGGER` needs `SUPER` unless `log_bin_trust_function_creators` is set. Unchecked for the pinned version and the host.
- U2. The engine's site database user holds the `TRIGGER` privilege (the engine grants all privileges on the site database).
- U3. Without the `PROCESS` privilege, a user sees its own threads in `PROCESSLIST`. A disconnected client's `ALTER` keeps its thread until it ends or is killed. A reused connection id only causes a false "alive", which holds.
- U4. MariaDB atomic DDL recovers or rolls back an interrupted `ALTER` at server restart (10.6 and later).
- U5. Each site has its own database, custom `site_map` sites included (A2).
- U6. No legacy rows exist on a real customer site (A3).
- U7. The table collation folds exactly as `_collation_fold` does, so the unique index and the lock keys agree.
- U8. `frappe.whitelist(methods=["POST"])` exists in the pinned engine version.
- U9. The hold lookup's per-row MAC verification costs little at realistic deployment counts. To be measured.
- U10. The gateway routes no engine method path.

## Alternatives rejected
- **Keep the evidence in the audit table and add a unique index.** The index cannot cover main rows only, because MariaDB has no partial unique index. A generated-column workaround keeps the mixed table and its in-place status updates.
- **A mutable status column guarded by triggers.** Triggers do not stop the attacker who holds the database credential. A derived status makes a deleted outcome fail closed.
- **A per-site hash chain over every event.** It serializes all appends per site. Per-deployment chains plus a deployment-count head give the same detection, except the residual that remains either way.
- **Recompute `payload_hash` under the canonical id during migration.** That would let a legacy key replay as if it were verified.
- **Map unmappable rows to a quarantine key.** It drops a hold or a replay record. Blocking the whole site is simpler and fails closed.
- **Recovery that repairs, by dropping an orphan column or re-sending a statement.** Never in phase 1 (reconciler rule "no auto-delete"; ADR-0068 item 18).

## Consequences
- **Easier.**
  - A held table can be released when the evidence proves its state.
  - Holds, replay and revert become tamper-evident.
  - One key maps to one deployment at the database level.
- **Harder.**
  - A secret-store dependency on the deploy path.
  - A head-row lock at every prepare.
  - A legacy or migrated hold stays held until a runbook or a founder decision.
  - Non-DDL holds wait for CE-SEC-011.
- **Builds and records.**
  - The rows in section 6.
  - The inventory entry and rotation row in `docs/security/secrets-management.md` (shared path, Eldon reviews).
  - The incident runbook for a compromised `kid`.
  - SEC-008's off-box head anchor (Eldon, G2) for the rollback residual.

## Supersedes
None.
