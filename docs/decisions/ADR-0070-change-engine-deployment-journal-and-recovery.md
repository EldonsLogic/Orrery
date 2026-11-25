# ADR-0070: Change-engine deployment journal, keyed MAC, legacy rekey migration and locked recovery entry point

Status: Proposed
Owner: partner
Approved by: pending (security review by a different model, then Eldon line by line; Tier 3, RULES 42: touches audit, tenancy and a new API surface)

Plan IDs: CE-SEC-009 and CE-SEC-010 (G1, design only), plus the keyed MAC from CE-SEC-011. No code until this ADR is Accepted. Internal document: it names the engine (ADR-0016). `CE/` means `apps/engine/change_engine/change_engine/`. Line numbers are at `b28a8709`. Items marked **(P)** are proposed choices of this ADR; everything else restates code or an existing ADR. Revision 2 answers the review listed at the end.

## 0. Assumptions and questions for Eldon

Assumptions (each is a reading I chose; say if it is wrong):
- A1. The canonical identity of a site is what `_resolve_site_id` returns with no caller value: the tenant id the backend binds (`t-alpha.<domain>` gives `t_alpha`, `CE/api/endpoints.py:2142-2187`), else the site name. Custom `site_map` sites get their tenant id from CE-SEC-011 first; the migration (section 2) runs after that, so it never rekeys twice.
- A2. Each engine site has its own database, and every row in that database's audit table describes that site, whatever `site_id` string it carries. UNVERIFIED for our provisioning (U5).
- A3. No real customer site holds legacy rows today (PR #322 text, marked HUMAN-ONLY there). Dev and pilot benches may, and the migration must handle them anyway.
- A4. This ADR covers the change-engine deployment hold (`PREPARED` / `RECOVERY_REQUIRED` rows). The adapter's own site state `recovery_required` (ADR-0041, `adapter_sites`) is a separate layer and is not cleared here.
- A5. ADR-0041 (journal on the tenant database) and ADR-0068 (signed grant, `siteId` incarnation) are Proposed. This ADR builds on them as written and changes neither.

Questions for Eldon (the coordinator numbers them):
1. **Key custody.** A per-tenant HMAC key held in engine-worker memory and read from the secret store (P, item 3.1), or a KMS-held MAC key (no key in memory, but one network call per verified row on a full site check)? With the chosen option, production deployments are refused until SEC-002's store exists. Is that acceptable before the first pilot?
2. **Inferred provenance.** When the live table is exactly the baseline plus the approved column, the dispatching connection is gone and the metadata matches the stored field definition, may recovery finalize `APPLIED` with `provenance: inferred` (P, row R18)? Or must it hold for a human? An out-of-band desk change that adds the identical field is indistinguishable.
3. **Migrated holds.** May recovery finalize a migrated CE-SEC-008-format hold whose unkeyed digest verified during the migration? Or does every migrated hold stay held (P)?
4. **Recovery caller.** `System Manager` only (P), or a dedicated role held only by a platform service user? Should the control plane later trigger recovery through an adapter contract operation (your `contracts/` lane, a later gate)?
5. **Scope.** Recovery v1 covers physical-DDL field deployments only. Property-setter, workflow and report holds stay held until CE-SEC-011 gives them durable baselines (P). Acceptable?
6. **Rollback residual.** A consistent rollback (an old head row plus deleted later rows) is not detectable locally (item 3.5). Accept it until SEC-008's off-box anchor (your G2 row)?
7. **Identity.** Key the journal on the tenant id (P), with ADR-0068's opaque `siteId` added as a column once that ADR is Accepted? Or wait and key on `siteId`?
8. **Metadata without column (R17).** A timed-out ALTER can leave the engine's field metadata committed with no column. Recovery holds it and never deletes metadata. Should a separate, audited operator action remove such metadata (a new row), or is a reviewed runbook enough for G1?

## Context
- CE-SEC-008 (PRs #322, #331) made the guarded field path durable. It kept the evidence inside the old audit table `tabChange Engine Audit` (`CE/api/endpoints.py:459-483`, created at `:697-721`). One main row per deployment is updated in place (status, `outcome_json`; `:1635-1660`, `:879-902`). Evidence rows sit beside it under the key `<dep>#evidence`, with statuses `EVIDENCE_BASELINE`, `EVIDENCE_DDL_DISPATCH` and `EVIDENCE_DDL_COMPLETED` (`:1394-1409`).
- The plan column carries an unkeyed SHA-256 over id, site, doctype, field, payload hash, plan and baseline (`_bind_digest`, `:497-506`). Journal rows chain to it (`_row_digest`, `:509-512`). `load_durable_evidence` verifies all of it (`:1425-1511`). A legacy plain-list plan loads as `verified: False` and always holds (`:1275-1278`).
- Known limits (code and Eldon's reviews of #322 and #331): the digest is unkeyed, so anyone who can write the table can recompute it; deleting the journal tail is not detected (T8); `status`, `outcome_json`, `base_revision_hash` and `idempotency_key` sit outside it, so PREPARED to APPLIED lifts a hold undetected (T12 to T14); replay and revert do not check it (N4).
- The index on `(site_id, idempotency_key)` is not unique (`:716`). Duplicate keys are caught only after the fact (`:957-958`).
- **Identity.** `_read_site_ids` reads the host name as a read-only alias for rows written before the single-identity rule (`:2152-2163`). Rows under a bare slug (`t-alpha`) or under any caller-chosen id are invisible to the hold and replay lookups (log `2026-11-25-partner-claude-code-ce-sec-008-deploy-path-durability.md:128`).
- **Dispatch.** The engine inserts the field metadata (`cf_doc.insert`), which sends the ALTER through the hooked `_admit_ddl` (`:1703-1723`). `_journal_dispatch_intent` commits on the same engine session (`:1516-1526`), and MariaDB commits implicitly before an ALTER anyway, so a timed-out ALTER (1205) leaves the metadata committed and the table unchanged.
- **No release path.** Nothing releases a held deployment. `revert_configuration_change` refuses a held one (`:2955-2967`). The reconciler sends every restarted deployment to `RECOVERY_REQUIRED` (`:1240-1252`; `CE/guarded_apply/schema_reconciler.py:595-603`). A held table therefore stays blocked forever.
- Eldon's carry-overs into CE-SEC-009: compare the stored doctype and site with the request (F4), and hold on `verified: False` (N3).

## Decision

### 1. Journal tables (CE-SEC-010)
1.1 **(P) Location.** Three plain InnoDB tables, utf8mb4, in the tenant site database beside the schema they describe (ADR-0041); a dump or restore returns journal and schema together. Created by a patch in `CE/patches.txt`. Not engine document types, so no desk view or REST resource; their names join the protected list in `CE/guarded_apply/safety_guardrails.py:53-69`.

1.2 **(P) `tabChange Engine Deployment`.** One row per deployment, insert-only.

| Column | Type | Note |
|---|---|---|
| `site_id`, `deployment_id`, `idempotency_key` | VARCHAR(140) NOT NULL | canonical identity (A1); ids as stored |
| `payload_hash` | CHAR(64) NOT NULL | |
| `engine_kind` | ENUM(`field`, `property_setter`, `workflow`, `report`) | |
| `doctype`, `fieldname` | VARCHAR(140) | |
| `base_revision_hash` | VARCHAR(64) | |
| `approved_plan` | LONGTEXT | JSON list; the MAC covers `approved_plan_sha256` CHAR(64) |
| `field_def` | LONGTEXT NULL | canonical JSON of the engine field definition (fieldtype, options, length, default, reqd, unique, index); the MAC covers `field_def_sha256` CHAR(64) |
| `dispatch_connection_id` | BIGINT UNSIGNED NULL | `CONNECTION_ID()` of the engine session that will send the statements, read on it at prepare (field only) |
| `dispatch_db_user` | VARCHAR(288) NULL | `CURRENT_USER()` of that session (ADR-0038 dual-slot users) |
| `site_seq` | BIGINT NOT NULL | gap-free `1..deployment_count` per site (item 1.5) |
| `origin` | ENUM(`current`, `legacy`) | `legacy` only from the migration |
| `legacy_site_id` | VARCHAR(140) NULL | original value |
| `legacy_status` | VARCHAR(64) NULL | original value |
| `created_at` | DATETIME(6) | |
| `mac` | VARCHAR(140) NOT NULL | `<kid>:<hex>` |

Keys: `PRIMARY KEY (site_id, deployment_id)`; `UNIQUE uq_site_idem (site_id, idempotency_key)`; `UNIQUE uq_site_seq (site_id, site_seq)`; `INDEX (site_id, doctype)`. No status column (item 1.4).

1.3 **(P) `tabChange Engine Deployment Event`.** Append-only.
- Columns: `site_id`, `deployment_id` (VARCHAR(140)), `seq` (gap-free from 1 per deployment), `kind`, `stmt_seq` (NULL unless a dispatch kind), `payload` (canonical JSON), `actor` (VARCHAR(140)), `created_at`, `site_seq` (BIGINT NOT NULL, gap-free `1..event_count` per site), `prev_mac` and `mac` (VARCHAR(140)).
- `kind` is one of `baseline`, `dispatch_intent`, `dispatch_completed`, `outcome`, `recovery_attempt` or `dispatcher_dead` (item 1.9). `prev_mac` is the `mac` of event `seq-1`, or of the deployment row for `seq = 1`.
- Keys: `PRIMARY KEY (site_id, deployment_id, seq)`; `UNIQUE (site_id, site_seq)`.
- An `outcome` payload carries `status`, `final` (bool), the reconciler disposition and, after recovery, the classification row.

1.4 **(P) Status is derived.** A deployment's status is the status of its latest `outcome` event, or `PREPARED` when it has none. Final: `APPLIED`, `ALREADY_APPLIED`, `FAILED_CLEAN`, `REJECTED`, `ROLLED_BACK`, `QUARANTINED`. `RECOVERY_REQUIRED` is non-final. Today's in-place updates (`persist_final_outcome_and_audit`, `mark_recovery_required`, `update_deployment_status`) become appended `outcome` events. Whether a deployment is open is ALSO recorded in the head (item 1.5); a disagreement between the two is `evidence_invalid`.

1.5 **(P) `tabChange Engine Journal Head`: the site anchor.** One row per site. Every append runs in one short transaction that takes `SELECT ... FOR UPDATE` on this row, gives each new row the next `site_seq` of its own table, and rewrites the head. No DDL is ever inside it.

| Column | Meaning |
|---|---|
| `site_id` | PK |
| `deployment_count`, `event_count` | rows in each table for this site, and its highest `site_seq`; `0` means the table is empty for this site |
| `open_deployments` | canonical JSON list, one entry per non-final deployment: `deployment_id`, `doctype`, `idempotency_key`, `engine_kind`, `dispatch_db_user` |
| `migration_state`, `migration_source_sha256` | item 2.5 |
| `updated_at`; `head_mac` VARCHAR(140) | MAC over every other column |

A prepare adds an `open_deployments` entry; a final `outcome` removes it, in the same transaction as the event.

1.6 **(P) Journal checks and their cost.** *D* is the site's deployment count and *E* its event count. Every check reads inside **one REPEATABLE READ snapshot** (`START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY` on the dedicated connection; under recovery's locks, after `begin_fresh_read_view`). Appends change the head and their rows in one transaction, so a snapshot never sees torn counts. Each read of `approved_plan` or `field_def` recomputes its SHA-256 and compares it with the MAC'd column.

| Check | Used by | Reads, all in the snapshot | Cost |
|---|---|---|---|
| **Head check** | hold lookup, `inspect_step_plan`, health | head row, `head_mac` verified; per table, with *n* its head count: if *n* = 0, `MAX(site_seq)` is NULL; else the row with `site_seq` = *n* exists, its MAC is recomputed and valid, and `MAX(site_seq)` = *n* | O(1): one row, four unique-index seeks, at most three HMACs |
| **Hold decision** | after the head check | the target is held iff an `open_deployments` entry has its doctype | O(open holds) |
| **Site check** | prepare (replay miss), replay hit, revert, recovery, end of migration | head check; `COUNT(*)` per table equals its head count (with the unique `site_seq` and `MAX` = *n*, that proves `1..`*n* gap-free); every deployment row's MAC recomputed | O(*D*) HMACs plus O(*D* + *E*) index-only counts |
| **Deployment check** | replay hit, revert, recovery | the deployment's events: gap-free `seq`, `prev_mac` chain, every MAC, latest `outcome` agrees with `open_deployments` | O(events of one deployment) |

Any failure is fail-closed: the hold lookup reports held (`evidence_invalid`), and replay, revert, prepare and recovery refuse. Holds come only from the signed head, and replay absence, revert and recovery need the site check, so an edited `doctype` or `idempotency_key`, or a deleted earlier trailing outcome, cannot hide a row. An empty `complete` site passes the head check with both counts `0`.

1.7 **(P) Triggers** guard against code bugs and naive SQL, not against an attacker; the MAC is the integrity control.

| Table | Trigger rule |
|---|---|
| deployment, event | `BEFORE UPDATE`, `BEFORE DELETE`: `SIGNAL SQLSTATE '45000'` |
| head, `OLD.migration_state <> 'complete'` | any update allowed except a change of `site_id` (migration batch; re-run after `blocked`) |
| head, `OLD.migration_state = 'complete'` | `site_id` and `migration_*` unchanged; both counts non-decreasing, and their sum increases |
| head | `BEFORE DELETE` signals |

Required in dev and CI. In production a missing trigger is reported by the health check and does not block, because creating one may need privileges we lack (U1, U2).

1.8 **Writers and readers.**
- All four engines write through `FrappeDeploymentAdapter`. Its prepare, finalize, hold, replay, revert-record and evidence functions switch to these tables in one change. The health check (`CE/adapter/frappe_backend.py:521-528`) and the phase-0 proof (`CE/proofs/phase0_bench_proof.py:1117`) switch too.
- The duplicate-key insert maps to the existing `DeploymentIntentConflictError` path (`schema_reconciler.py:387-414`).
- **Dispatch rules (P).** `_admit_ddl` reads `CONNECTION_ID()` and `CURRENT_USER()` on the sending session before every statement. It refuses to send unless they equal the stored `dispatch_connection_id` and `dispatch_db_user`. Journal appends (intent, completion, outcome) commit on CE-SEC-011's dedicated connection, never on the engine session, so a journal commit never publishes engine writes. MariaDB still commits the metadata implicitly before the ALTER; R17 classifies that state.

1.9 **(P) Rotation drain probe.** ADR-0038's dual-slot cutover leaves recovery running as the new user, which cannot see the old user's threads (U3). Before revoking user U:
- the rotation job runs the engine's `attest_dispatchers(U, force)` as U, which still holds U's credential;
- for each `open_deployments` entry naming U, the probe takes the deployment's two locks (a refused lock means alive), checks `CURRENT_USER() = U`, checks that its own id is visible, and checks that `dispatch_connection_id` is absent from `PROCESSLIST`;
- it then appends a MAC'd `dispatcher_dead` event (user, connection id, probe actor);
- the probe never classifies or finalizes.

| Case | Normal rotation | Forced (incident) revocation |
|---|---|---|
| every dispatcher naming U attested | revoke | revoke |
| a dispatcher live or unprovable | re-probe within a bounded drain window (configured, default 15 minutes), then postpone the rotation | `KILL CONNECTION` it as U, re-verify absence and attest (`killed: true`); if that cannot be verified, revoke anyway and leave the deployment held, unattested (R14) |

Long holds in other rows (R10, R15, R17, R19) do not block rotation once attested.

### 2. Migration of legacy rows (CE-SEC-010)
2.1 **(P) Canonical identity.** `C = _tenant_of_site(frappe.local.site) or frappe.local.site` (A1). Under A2 every legacy row in this database is rekeyed to `C`. The reason is recorded per row: `canonical` (already `C`), `host_alias` (the host name), `slug_alias` (the host label, such as `t-alpha`) or `caller_chosen` (anything else). The original value goes to `legacy_site_id`.

2.2 **Mapping.**
- Each main row (status not `EVIDENCE_*`, no `#` in its name) becomes one deployment row with `origin = legacy`, plus one `outcome` event carrying its old status and outcome when it has one. It joins `open_deployments` when its status is `PREPARED` or `RECOVERY_REQUIRED`.
- Each evidence row `<dep>#<suffix>` becomes an event under its main row. **Order (P):** baseline first, then by `stmt_seq`, and for one `stmt_seq` the `dispatch_intent` before the `dispatch_completed`; never by row name, which sorts `#c0001` before `#d0001`. The old SHA-256 digest is copied into the payload.
- `payload_hash` is copied, never recomputed, so a retry of a legacy key still gets `IDEMPOTENCY_CONFLICT`, as today (log line 118). Fail closed.
- `site_seq` follows `created_at`, then `name`, per deployment in the order above.

2.3 **(P) Verify, then MAC without laundering.**
- Before anything is written, every legacy deployment is checked the way `load_durable_evidence` checks it (`:1425-1511`): a digest-format plan must verify, with its journal rows chained, gap-free, and every completion matching an intent. Every non-NULL `outcome_json` must pass `_parse_outcome` (`:969-980`). A NULL outcome needs a `PREPARED` or `RECOVERY_REQUIRED` status.
- A plain-list (pre-digest) plan cannot be verified. It imports as `legacy` and always holds (R10). This is today's behaviour (`:1275-1278`).
- Any other failure blocks the site (item 2.4).
- Migrated rows are then MAC'd so that later tampering is detected. `origin = legacy` sits inside the MAC'd bytes, and recovery always holds a legacy deployment (R10, question 3).

2.4 **(P) Ambiguity fails closed for the whole site.** Any of the following sets `migration_state = blocked` and writes nothing else:
- a duplicate `(C, idempotency_key)` or `(C, deployment_id)` under the **journal table's own collation**, detected by the database and not by Python folding (item 2.5, U7);
- an evidence row with no main row, an unparseable name or an unknown status;
- an unknown main-row status;
- a failed verification under item 2.3;
- a source read error.

While a site is `blocked` or `none`, every deployment, hold decision, replay and recovery on it refuses with `journal_migration_pending`. A site whose old table is absent or empty becomes `complete` at once. The patch records `blocked` and returns success, so `bench migrate` is not stopped for unrelated apps. Resolution is a reviewed runbook; on a dev bench, rebuild the site.

2.5 **Idempotent and atomic.**
- The table DDL runs first, in its own step. The row copy and the head update then run in one transaction with no DDL inside.
- A duplicate-key error (1062) on insert rolls the whole transaction back. A second transaction then records `blocked` with reason `duplicate_key`. The dry run finds duplicates first with `GROUP BY ... COLLATE <journal collation> HAVING COUNT(*) > 1`.
- A crash leaves no partial rows.
- `migration_source_sha256` is a SHA-256 over the canonical dump of all source rows.

| Head state | Source hash | Action |
|---|---|---|
| `complete` | same | no-op, report `already_migrated` |
| `complete` | changed | refuse `migration_source_changed`; stays complete; nothing written |
| `blocked` or `none` | any | run again from scratch (a blocked run wrote no rows) |

- The migration never runs DDL against business tables, never dispatches a journalled statement and never finalizes anything. The old table is kept read-only for history and is never dropped by this ADR.

2.6 **Dry run.** `bench --site <site> execute change_engine.patches.ce_sec_010_journal.dry_run` (P) prints JSON: `C`, counts by mapping reason and evidence kind, held deployment ids, each ambiguous group or failed verification with its reason, `would_complete` and the source hash. It writes nothing, and its output never goes into the repo (synthetic data only on dev hosts).

### 3. Keyed MAC (CE-SEC-011 part, CE-SEC-010 store)
3.1 **(P) Key.** One 256-bit HMAC-SHA256 key per tenant per version, a new ADR-0038 inventory entry. The number is allocated by the coordinator; ADR-0068 proposes `S24`.
- It lives in the secret store, is read by the engine workers of the tenant's bench pool (the same reach as `S21`) and is held only in memory.
- It is never written to the site database, `site_config.json`, logs or responses.
- A `JournalKeyProvider` interface has dev and test providers (throwaway keys, `S20`). Under ADR-0041's production guard, a missing provider or key fails closed for **every** journal reader and writer: prepare refuses (`journal_key_unavailable`); the hold lookup and `inspect_step_plan` report blocked; replay, revert, health (`database` reported down) and recovery refuse.

3.2 **Construction.** `mac = kid + ":" + hex(HMAC-SHA256(K[tenant, kid], canonical_json(...)))`.
- The MAC'd value is `{"v": 1, "t": <table tag>, "site": site_id, all columns except mac (LONGTEXT replaced by its sha256), "site_seq", "prev": prev_mac}`, in contract 5.8 canonical form.
- Comparison is constant-time. The table tag separates domains. Because the site and the per-tenant key are inside, a row copied from another tenant's database fails.

3.3 **(P) Rotation and versioning.**
- New writes use the current `kid`.
- Older `kid`s stay verify-only for as long as any row references them, like `S16` verification keys.
- Rotation is yearly and on suspected compromise.
- A compromised `kid` goes on a deny list. Rows under it read as unverified, so their deployments hold and their targets block until an incident runbook (follow-up) re-attests them.

3.4 **What it detects.**

| Tamper | Caught by |
|---|---|
| Edit of any column of any row, including status, outcome, base revision, key, doctype (T12 to T14) | row MAC; holds from the signed head, replay absence from the site check (1.6) |
| Forged row, or a row from another tenant | MAC with the per-tenant key |
| Deleted or reordered event inside a deployment (M19) | `seq` and `prev_mac` |
| Deleted row anywhere, including an earlier deployment's trailing `ROLLED_BACK` or `QUARANTINED` outcome | `COUNT(*)` against the head count (site check) |
| Deleted last row of either table (a final outcome, a trailing `dispatch_intent`) | row at `site_seq` = count missing (head check) |
| Row appended without a head update | `MAX(site_seq)` above the head count |
| Deployment row deleted and then reported as absent | recovery runs the site check before `not_found` (R6) |
| Edited or replaced head | `head_mac` |

Every detection reads as held (`evidence_invalid`), never as absent. A head or site-check failure holds every target on the site.

3.5 **What it does not detect.**
- **Consistent rollback.** An attacker restores a saved, earlier valid head row and deletes every later row. Locally this is indistinguishable from a legitimate restore (ADR-0041). Even then, recovery never finalizes `APPLIED` on a journal claim: it decides from the live schema against the MAC'd baseline and checks dispatcher liveness from the deployment row (R14). Only an off-box anchor of `head_mac` closes it (SEC-008, Eldon G2; question 6).
- **Anyone holding the key** (code execution in an engine worker of the pool) can forge rows. This is the same residual as `S05` in ADR-0038.

### 4. Recovery entry point (CE-SEC-009)
4.1 **(P) Shape.** It is an internal change-engine RPC. It is not customer-facing, not in any contract and never routed by the gateway (ADR-0016).

```
recover_deployment(deployment_id: str, mode: "classify" | "finalize" = "classify",
                   lock_wait_seconds: int = 3) -> {
  deployment_id, mode, status: APPLIED | FAILED_CLEAN | RECOVERY_REQUIRED | REJECTED,
  recovered: bool,         # true only when THIS call appended the final outcome
  classification: "R1".."R19", reason_code, stage: "RECOVER", execution_time_ms }
```

- `classify` appends only a `recovery_attempt` event. `finalize` also appends the final `outcome` when the row allows it.
- Responses carry stable codes only (`_stable_reason_code`, `CE/api/endpoints.py:2092`): no exception text, SQL, schema contents or engine names.
- Whitelisted POST-only (U8). Tests inject an adapter through a non-whitelisted `_recover_deployment_impl`, never through RPC kwargs.

4.2 **(P) Caller.**
- Roles come only from the authenticated session (`get_current_user_roles`). The caller needs `RECOVERY_ROLES = {"System Manager"}` (question 4).
- Refused before any read when present: `site_id`, `site`, `user_roles`, `caller_roles`, `actor`, `governance_tier`, `adapter`, `db`, `status` and `outcome`. The caller cannot choose site, roles or result; the classification is deterministic from evidence.
- An unauthorised caller gets the same refusal for known and unknown ids, and nothing is read.

4.3 **Sequence.** Each step refuses with the row named, before the next step runs.
1. Resolve `C` with `_resolve_site_id(None, ...)`. Check the journal key (R3).
2. Run the head check, which also verifies `migration_state` (R4, R5).
3. Read the deployment row by `(C, deployment_id)`. If it is missing, run the site check and look the id up in `open_deployments` before answering (R6). Verify the row's MAC (R7). This read only learns the lock keys; nothing is written. It settles F4: the site is part of the key, and the doctype comes from the stored row.
4. Take the same two locks in the same order as `execute_single_field_deployment` (`schema_reconciler.py:217-249`): the idempotency lock for `(C, stored key)`, then the target lock for `(C, stored doctype)` (R8).
5. Call `begin_fresh_read_view`, then run the site check and the deployment check again in one snapshot (R9).
6. Run the fresh read (4.4) and classify (R10 to R19).

It runs on CE-SEC-011's dedicated deployment connection. Every exit uses the verified release, and an unverified release discards the session (CE-SEC-008).

4.4 **Fresh complete read, under the locks:**
- `_read_table_schema(doctype)`: every fingerprint key (`CE/api/endpoints.py:1019`);
- the field's `tabCustom Field` row, compared field by field with the stored `field_def` (Data, Link and Select all yield `varchar(140)`, so the column alone proves nothing);
- `has_col`;
- **liveness (P), for every field deployment, whether or not D is empty.** The dispatcher is "gone" when either:
  - a verified `dispatcher_dead` event is in the deployment's chain (1.9), whatever user recovery runs as; or
  - `CURRENT_USER()` equals `dispatch_db_user`, and `SELECT ID FROM information_schema.PROCESSLIST WHERE ID IN (CONNECTION_ID(), dispatch_connection_id)` returns the recovery's own id (the view works) but not `dispatch_connection_id`.

  Anything else is "alive or unknown" (U3).

Any error, an empty answer where a row must exist, or a partial fingerprint is "unreadable", never "equal".

4.5 **Classification table.** The rows are checked in order and the first match wins. B is the MAC'd baseline, L the live fingerprint, M the metadata row, F the stored `field_def` and D the dispatched statements from the events. "Attempt" means a `recovery_attempt` event is appended under the locks; "none" means the call is in the server log only.

| Row | State | Result | Write |
|---|---|---|---|
| R1 | caller lacks the role, or a refused parameter is present | REJECTED `not_permitted` | none |
| R2 | `evidence_namespace_problem(id)` (empty, `#`, control characters; looser legacy ids pass) | REJECTED `invalid_deployment_id` | none |
| R3 | journal key unavailable | REJECTED `journal_key_unavailable` | none |
| R4 | head check fails | RECOVERY_REQUIRED `evidence_invalid` | none |
| R5 | `migration_state` not `complete` (head verified) | REJECTED `journal_migration_pending` | none |
| R6 | no deployment row under `(C, id)`: site check fails, or the id is in `open_deployments` | RECOVERY_REQUIRED `evidence_invalid` | none |
| R6 | no deployment row, site check passes, id not open | REJECTED `not_found` | none |
| R7 | the deployment row's MAC fails before the locks | RECOVERY_REQUIRED `evidence_invalid` | none |
| R8 | a lock is not granted, or the fresh view fails | REJECTED `locked` / `engine_unavailable` | none |
| R9 | under the locks: the head, site or deployment check fails, or a current field deployment lacks its baseline event | RECOVERY_REQUIRED `evidence_invalid` | none (a broken chain gets no new link) |
| R10 | `origin = legacy` (N3: `verified: False` holds) | RECOVERY_REQUIRED `evidence_unverified` | attempt |
| R11 | latest outcome is final | its stored status, `already_final` (idempotent) | attempt |
| R12 | `engine_kind` is not `field` | RECOVERY_REQUIRED `kind_not_recoverable` | attempt |
| R13 | schema, metadata or liveness read failed or incomplete | RECOVERY_REQUIRED `schema_unreadable` | attempt |
| R14 | dispatcher alive or unknown (4.4), whatever D holds | RECOVERY_REQUIRED `dispatch_may_be_in_flight` (retry later) | attempt |
| R15 | `ddl_batch_rejection(doctype, fieldname, approved, D, B, complete=False)` returns a reason | RECOVERY_REQUIRED `unapproved_dispatch` | attempt |
| R16 | L == B on every key, M absent, has_col false | FAILED_CLEAN `baseline_verified` | final `outcome` (finalize) |
| R17 | L == B, has_col false, M present and equal to F, D non-empty | RECOVERY_REQUIRED `metadata_without_column` (question 8) | attempt |
| R18 | `assess_applied_ddl(doctype, fieldname, approved, D, B, L)` reports no side effect; `new_column_matches_plan`; indexes unchanged; M present and equal to F | APPLIED `provenance: inferred` (question 2); then clear the doctype cache | final `outcome` (finalize) |
| R19 | anything else (orphan metadata, orphan column, a definition or index difference, a side effect) | RECOVERY_REQUIRED, with the reconciler's disposition | attempt |

R17 is not R16. Finalizing `FAILED_CLEAN` would release the target while the engine still reads a field with no column, and recovery never deletes metadata (phase-1 "no auto-delete"). Committing the intent earlier cannot prevent the state, because MariaDB commits implicitly before an ALTER. The state is therefore named and held. R15 and R18 call the gate's own functions, so the allowlisted no-op decimal `MODIFY` clauses (`ddl_plan_gate.py:650-690`) pass exactly as they do at dispatch.

4.6 **Never re-runs DDL.**
- The recovery module imports no dispatch function and is handed no field definition to apply.
- Its SQL is restricted to: `SELECT`; `GET_LOCK`, `RELEASE_LOCK`, `IS_USED_LOCK`; `CONNECTION_ID()`, `CURRENT_USER()`; the head `SELECT ... FOR UPDATE`; and the event `INSERT` with its head `UPDATE`.
- A test recorder fails on anything else.
- R18 finalizes only what already exists. Nothing is created, dropped or repaired.

4.7 **Audit and idempotency.** An "attempt" event records:
- the session user and their roles;
- the mode and classification row;
- the reason code;
- the SHA-256 of the encoded live fingerprint;
- dispatcher liveness.

Finalization appends one `outcome` event (`final: true`, actor, classification) and removes the `open_deployments` entry, in the same transaction. A second call returns R11. Concurrent calls serialize on the locks, and the second sees R11.

### 5. Threats and proposed tests
`bench:` means a real MariaDB test (CI service per ADR-0041).

| Threat | Control | Test |
|---|---|---|
| Status edit lifts a hold (T12) | holds only from the signed head; outcome events MAC'd | `test_ce_sec_010_forged_or_edited_outcome_keeps_target_held` |
| Held row's `doctype` edited to unblock its table | holds from `open_deployments`, never a filtered row query | `test_ce_sec_010_edited_doctype_of_held_row_still_holds` |
| Finished row's `idempotency_key` edited to bypass replay | replay miss runs the site check | `test_ce_sec_010_edited_key_of_finished_row_refuses_prepare` |
| Base revision or field edited (T13, T14); replay or revert on an edited row (N4) | row MAC; replay and revert run the deployment check | `test_ce_sec_010_edited_deployment_row_refused_by_replay_revert_and_recovery` |
| Any row deleted, including an earlier deployment's trailing outcome before a revert | `COUNT(*)` against the head; revert runs the site check | `test_ce_sec_010_deleted_row_holds_every_target_on_site`, `test_ce_sec_010_revert_after_deleted_earlier_outcome_refused` |
| Deleted row reported as absent | site check before `not_found` (R6) | `test_ce_sec_009_deleted_open_row_is_evidence_invalid_not_not_found` |
| Torn counts while other targets append; empty site | one snapshot; `0` sentinel | bench: `test_ce_sec_010_checks_consistent_under_concurrent_appends`; `test_ce_sec_010_empty_complete_site_passes_head_check` |
| LONGTEXT plan or field definition edited | SHA-256 compared on every read | `test_ce_sec_010_edited_plan_or_field_def_text_refused` |
| Tail event deleted: final outcome, trailing `dispatch_intent`, or all events | head check (last row by count); R9 when the baseline is missing | `test_ce_sec_010_deleted_last_event_is_evidence_invalid`, `test_ce_sec_009_current_field_without_baseline_is_r8` |
| Event reordered or renumbered (M19) | `seq`, `prev_mac` | `test_ce_sec_010_event_gap_or_reorder_is_evidence_invalid` |
| Row copied from another tenant's database | per-tenant key; site in the MAC | `test_ce_sec_010_row_from_other_tenant_fails_mac` |
| Two prepares with one key race | `UNIQUE (site_id, idempotency_key)`; head lock | bench: `test_ce_sec_010_concurrent_same_key_second_insert_refused` |
| ALTER sent from another session or user | `_admit_ddl` connection and user check | `test_ce_sec_010_admit_refuses_other_connection_or_user` |
| Dispatcher hidden by dual-slot users | `CURRENT_USER()` must equal `dispatch_db_user`, own id visible, or a `dispatcher_dead` attestation | `test_ce_sec_009_other_db_user_holds`, `test_ce_sec_009_invisible_own_connection_holds`, `test_ce_sec_009_attested_dead_dispatcher_is_gone_under_new_slot` |
| Rotation wedged by a hold, or revoked under a live ALTER | drain probe; bounded window; forced kill and attest (1.9) | `test_ce_sec_010_probe_attests_and_unblocks_revocation`, `test_ce_sec_010_live_dispatcher_postpones_normal_rotation`; bench: `test_ce_sec_010_forced_revocation_kills_attests_or_leaves_held` |
| Finalize while an ALTER still runs | liveness on every field row, even with D empty | `test_ce_sec_009_live_or_unknown_dispatcher_holds_with_empty_d`; bench: `test_ce_sec_009_killed_client_alter_still_running_holds` |
| Timed-out ALTER leaves metadata without column | R17 named hold | bench: `test_ce_sec_009_lock_timeout_alter_classifies_r17` |
| Wrong field type behind a matching column | M compared with stored `field_def` | `test_ce_sec_009_select_instead_of_data_is_not_applied` |
| Allowlisted decimal no-op MODIFY refused | R15 and R18 use the gate's functions | `test_ce_sec_009_decimal_noop_modify_finalizes` |
| Alias spelling opens a second scope | migration rekeys; writes use `C` only | `test_ce_sec_010_migration_rekeys_host_slug_and_caller_ids` |
| Ambiguous or tampered legacy rows imported | verify (2.3); database-collation duplicates; site `blocked` | `test_ce_sec_010_tampered_digest_or_outcome_blocks_site`; bench: `test_ce_sec_010_non_ascii_fold_duplicate_blocks_site` |
| Legacy events misordered | ordering rule (2.2) | `test_ce_sec_010_completion_follows_intent_after_migration` |
| Migration launders tampering | `origin = legacy` inside the MAC; R10 | `test_ce_sec_009_legacy_origin_always_holds` |
| Partial migration, or a site stuck in `blocked` | one transaction; state table (2.5) | `test_ce_sec_010_migration_crash_leaves_no_rows`, `test_ce_sec_010_rerun_from_blocked_and_changed_source_refused` |
| Recovery runs DDL | no dispatch import; SQL allow-list | `test_ce_sec_009_recovery_issues_no_ddl_in_any_row` |
| Recovery races a deployment or another recovery | both locks from the stored row; fresh view | `test_ce_sec_009_blocks_while_target_lock_held`, `test_ce_sec_009_two_recoveries_one_finalizes` |
| Broken chain extended by a signed attempt | no append in R7 or R9 | `test_ce_sec_009_broken_chain_gets_no_new_event` |
| Caller chooses site, roles or outcome; existence probing | refused parameters; session roles; uniform refusal | `test_ce_sec_009_caller_context_params_refused`, `test_ce_sec_009_unauthorised_same_response_for_known_and_unknown_id` |
| Key missing, or a `kid` compromised | every reader fails closed; deny list | `test_ce_sec_010_missing_key_blocks_hold_replay_plan_revert_and_recovery`, `test_ce_sec_010_denied_kid_holds` |
| Out-of-band identical field finalized as APPLIED | accepted residual, flagged `inferred` (question 2) | `test_ce_sec_009_identical_out_of_band_field_is_inferred` |
| Update or delete through plain SQL; head misuse | triggers (1.7) | bench: `test_ce_sec_010_triggers_signal_and_allow_migration_batch` |
| Recovery reached from outside; names or raw text leak | not routed (ADR-0016); stable codes | `test_ce_sec_009_gateway_has_no_route_to_recover_deployment` (`services/gateway/`), `test_ce_sec_009_responses_carry_no_engine_names_or_exception_text` |
| Consistent rollback | none locally (3.5) | residual; SEC-008 |

### 6. Proposed follow-up rows (partner lane, G1; IDs for the coordinator to confirm)
Each depends only on partner rows (ADR-0025):
- `| CE-SEC-012 | Change engine: deployment journal tables, journal head (per-table gap-free site_seq with unique (site_id, site_seq), counts with 0 as empty, open_deployments, head_mac), triggers and keyed MAC per ADR-0070 sections 1 and 3; the head, site and deployment checks of item 1.6 in one REPEATABLE READ snapshot, LONGTEXT hashes verified on every read, and the site check on revert; store field_def, dispatch_connection_id and dispatch_db_user at prepare and refuse in _admit_ddl unless CONNECTION_ID() and CURRENT_USER() match them; journal commits on the dedicated connection; JournalKeyProvider with dev and test providers, and every journal reader and writer fails closed without a key under the production guard; switch every FrappeDeploymentAdapter writer and reader (prepare, finalize, hold, replay, revert record, evidence, inspect_step_plan, health check, phase-0 proof); refuse while the site's migration is not complete, and mark an absent or empty old table complete; add the key and the rotation drain step to the secrets inventory | Security | G1 | CE-SEC-010,CE-SEC-011 | partner | todo |`
- `| CE-SEC-013 | Change engine: legacy audit rows to journal migration per ADR-0070 section 2 (rekey to the canonical identity, verify CE-SEC-008 digests and stored outcomes first, intent-before-completion event order, legacy origin, duplicates by the journal collation, whole-site block on ambiguity, one transaction, source hash, re-run from blocked, dry-run report), with the section 5 migration tests on real MariaDB | Security | G1 | CE-SEC-012 | partner | todo |`
- `| CE-SEC-014 | Change engine: locked recovery entry point per ADR-0070 section 4 (classification R1 to R19 in the item 4.3 order, the site check before not_found, liveness by dispatch_db_user and own-connection visibility or a dispatcher_dead attestation, the rotation drain probe attest_dispatchers of item 1.9, never DDL, attempt and outcome events, System Manager only, no route in the gateway), with the section 5 recovery tests | Security | G1 | CE-SEC-012,CE-SEC-013 | partner | todo |`

### 7. UNVERIFIED claims
- U1. In MariaDB with binary logging on, `CREATE TRIGGER` needs `SUPER` unless `log_bin_trust_function_creators` is set. Unchecked for the pinned version and the host.
- U2. The engine's site database user holds the `TRIGGER` privilege (the engine grants all privileges on the site database).
- U3. Without the `PROCESS` privilege, a user sees only its own threads in `PROCESSLIST`. A disconnected client's `ALTER` keeps its thread until it ends or is killed. A revoked database user's open sessions keep running. `KILL CONNECTION` on one's own thread needs no extra privilege, and a killed `ALTER` rolls back (U4). A reused connection id only causes a false "alive", which holds.
- U4. MariaDB atomic DDL recovers or rolls back an interrupted `ALTER` at server restart (10.6 and later).
- U5. Each site has its own database, custom `site_map` sites included (A2).
- U6. No legacy rows exist on a real customer site (A3).
- U7. The journal tables' collation decides key equality, and `_collation_fold` matches it for the lock keys on ASCII ids. Non-ASCII ids are detected by the database (2.5), not by the fold.
- U8. `frappe.whitelist(methods=["POST"])` exists in the pinned engine version.
- U9. The site check's O(*D*) HMACs and O(*D* + *E*) counts stay cheap at realistic deployment counts. To be measured. The hold path is O(1).
- U10. The gateway routes no engine method path.

## Alternatives rejected
- **Keep the evidence in the audit table and add a unique index.** MariaDB has no partial unique index, and the mixed table keeps its in-place status updates.
- **A mutable status column guarded by triggers.** Triggers do not stop the attacker who holds the database credential.
- **Holds from a filtered row query, with per-row MAC checks.** An edited filter column hides the row (review finding 1). Holds come from the signed head instead.
- **Replaying the whole site hash chain on every check.** It is O(*E*). The signed head with per-table counts gives O(1) holds, and the O(*D*) site check runs only on prepare, replay, revert and recovery.
- **Recompute `payload_hash` under the canonical id during migration.** That would let a legacy key replay as if it were verified.
- **Map unmappable rows to a quarantine key.** It drops a hold or a replay record. Blocking the whole site is simpler and fails closed.
- **Recovery that repairs, by dropping an orphan column or metadata, or by re-sending a statement.** Never in phase 1 (reconciler rule "no auto-delete"; ADR-0068 item 18).

## Consequences
- **Easier.**
  - A held table can be released when the evidence proves its state.
  - Holds, replay and revert become tamper-evident.
  - One key maps to one deployment at the database level.
- **Harder.**
  - A secret-store dependency on every journal read.
  - A head-row lock on every append.
  - A legacy hold or an R17 hold stays held until a runbook or a founder decision (questions 3, 8).
  - Non-DDL holds wait for CE-SEC-011.
  - Rotation runs the drain probe first (1.9).
- **Builds and records.**
  - The rows in section 6.
  - The inventory entry, rotation row and dual-slot rule in `docs/security/secrets-management.md` (shared path, Eldon reviews).
  - The incident runbook for a compromised `kid`.
  - SEC-008's off-box head anchor (Eldon, G2) for the rollback residual.

## Supersedes
None.

## Review history
Security review Gemini 4 Argon at 5fe539bb ("changes required"), addressed in revision 2 (row numbers of revision 2):
- **1 filtered lookups:** holds come from the signed head; replay absence and recovery need the site check (1.5, 1.6).
- **2 tail truncation:** `event_count`, `last_row_mac`, `head_mac`; liveness even with D empty; a missing baseline is R8 (1.5, 3.4, 4.4, 4.5).
- **3 dual-slot liveness:** `dispatch_db_user`, the `_admit_ddl` connection and user check, own-connection visibility (1.2, 1.8, 4.4); U3 stays UNVERIFIED.
- **4 medium:** (a) stored `field_def`; (b) gate functions in R14 and R17; (d) MAC re-verified under the locks, no append in R6 or R8; (e) R2 uses `evidence_namespace_problem`. (c) is partly rebutted: the implicit commit before the ALTER publishes the metadata whatever connection commits the intent. Journal commits move to the dedicated connection anyway, and the state is held as R16, because finalizing `FAILED_CLEAN` would release a target with an orphan field.
- **5 migration:** (a) event order; (b) digest and outcome verification before the MAC; (c) duplicates by the database collation; (d) head trigger states and re-run from `blocked`; (e) every reader fails closed without a key; `mac` widened to VARCHAR(140), and every VARCHAR given a length.

Gemini 4 Argon re-review at 2777ff53: 4 and 5 resolved; N1 to N3 addressed in revision 3:
- **N1 check invariants:** per-table gap-free `site_seq` with a unique index, `0` as the empty sentinel, one REPEATABLE READ snapshot, the last row's MAC recomputed, LONGTEXT hashes verified on read, and the site check on revert (1.2, 1.3, 1.5, 1.6, 3.4). `last_site_seq` and `last_row_mac` are removed.
- **N2 rotation wedge:** a drain probe with a `dispatcher_dead` attestation, a bounded window and forced kill-and-attest; the "no revoke while named" rule is removed (1.9, 4.4).
- **N3 recovery order:** the key, then the head check with the migration state, then the site check before `not_found` (4.3, R3 to R6).
