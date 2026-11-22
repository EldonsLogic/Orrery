# ADR-0061: Design of the regional role-assignment store

Status: Proposed
Owner: eldon
Approved by: pending. Round 1 security review by a different model (Claude Fable 5.2, 2026-11-22, verdict REVISE, findings R-H1 to R-H3, R-M1 to R-M9, R-L1 to R-L6) is answered in this revision; a re-review by a different model and both founders' approval are still needed (RULES 42, Tier 3 in ADR-0035, because it touches auth and tenancy). **Acceptance is blocked until the founders answer Q-581 and counsel and the founders answer Q-582.**

Plan ID: SEC-024. Design only. No code, no contract change: the Tool API wording is GOV-065; the signed `sync_members` snapshot, the signed adapter receipt and the approval assertions need their own contract ADRs. [ADR-0060](ADR-0060-role-assignments-in-regional-store.md) item 15 (line 38) forbids any code that reads roles from, or writes assignments to, the store until this ADR and GOV-065 are Accepted. Section 11 maps ADR-0060 items 6 to 14 and the round 1 findings to the design points that meet them.

## Context
- ADR-0060 (Accepted) moved member-to-role assignments out of the tenant's engine site into a regional store run by the platform (item 1, line 20), superseding [ADR-0007](ADR-0007-identity.md) item 9 (line 26). It left technology, schema and deployment open (item 5, line 24) and bound them by conditions items 6 to 15 (lines 29-38), from [adr-0060-security-review.md](../security/adr-0060-security-review.md).
- Consumers: the gateway reads the caller's roles per request (ADR-0007 item 2, line 19; [contracts/tool-api.md](../../contracts/tool-api.md) section 4 step 2, line 100). The adapter takes full snapshots through `sync_members` at a store-issued `syncVersion` (`contracts/engine-adapter.md` ADP-C-063, line 379; `sync-members.schema.json` line 17). [ADR-0039](ADR-0039-role-and-permission-mapping.md) (Proposed) items 7 and 8 (lines 35-48) give the fail-closed rules and the apply-sync fence; [ADR-0040](ADR-0040-tenant-provisioning-service.md) (Proposed) Step 7 (line 25) needs the first full sync at a store-issued version.
- Role changes are action-policy row `AP-PERM-01` ([action-policy-table.md](../security/action-policy-table.md) line 180): R4 (line 59: second different approver, step-up, short expiry), Owner initiates, a second Owner or admin approves, never self-targeted, agents draft only, one hour, no break-glass. The payload hash binds an approval (line 64); role loss voids it (line 75). Break-glass never changes permissions (lines 131, 138). Q-41 (resolved) forbids self-approval for R4. Blueprint publish is `AP-BPL-01` (line 181).
- A Blueprint role has a `function` (one value is `owner`) and `isAdmin` (`contracts/blueprint.schema.json` lines 622, 655).
- `S22` (control-plane regional database) is held by control-plane and provisioning services ([secrets-management.md](../security/secrets-management.md) line 36); `S10b` per-tenant keys are for storage and backup jobs (line 24). Control-plane compromise T53 is rated "gap" ([threat-model.md](../security/threat-model.md) line 216); audit integrity is T56 (line 219); two-founder separation of duties is T52 (line 215).
- Code today: `services/control-plane/identity/policy.py` lines 26-41 take roles only from an injected `RoleResolver` keyed by person id and fail closed; removal and suspension bump a session version (`identity/service.py` lines 164, 185, 192). No store exists.
- Hosting is not chosen (INF-001). Placement rules: [hosting-rules.md](../security/hosting-rules.md) lines 11-18. Legal positions per market are UNVERIFIED until counsel reviews them.

## Decision

### 1. Shape and placement
1. **One store per served country**, in that country, with backups, replicas, logs and keys in the same country (ADR-0060 item 14; hosting-rules lines 11, 15, 16). Countries are never replicated, joined or queried together. A market with no in-country location for both the store and its anchor (section 4) is not served; Egypt and Qatar today (UNVERIFIED, pending INF-001, a founder decision and counsel).
2. **Its own logical database**, not the control-plane workflow database, in its own network segment, reachable only from the assignment service. `S22` and the provisioning workflow reach nothing in it.
3. **Technology.** A relational database with row-locking transactions, row-level security that can be forced on table owners, transaction-local session settings, and stored procedures. PostgreSQL is the reference shape for review (`FORCE ROW LEVEL SECURITY`, `set_config(..., true)`); its behaviour on a pinned version, its licence and hosting are UNVERIFIED until INF-001 and LEG-004.
4. **The assignment service** in `services/control-plane/` (Eldon's lane) has three separately deployed parts with separate credentials and keys: the **read path**, the **write service** (the only writer, ADR-0060 item 6) and the **verifier** (drift and anchor checks, section 7). The identity service, which signs the assertions in section 5, is a separate deployment with its own signing key; no assignment-service part holds an identity key. The gateway (`services/gateway/`) and the adapter (`apps/engine/`) are partner's lane and consume interfaces fixed by later contract ADRs.

### 2. Schema (logical)
Every table is keyed by the platform-generated `tenantId` (ADR-0040 line 16). Members are identified by `memberRef`, the identity service's per-tenant membership id: random, never reused, never a person id, email or phone (ADR-0060 item 14). The store holds no names. The `RoleResolver` adapter maps the verified person to `memberRef` through the membership the token names.

| Table | Key | Columns |
|---|---|---|
| `tenant_state` | `tenantId` | `status` (`active`, `apply_fenced`, `restore_fenced`, `site_fenced`, `deleting`), `generation`, `lastIssuedVersion`, `lastVerifiedSyncVersion`, `appliedRevision` and digest, `historyHead`, `bootstrapped`, `stateSig` |
| `tenant_tombstone` | `tenantId` | Permanent; written at tenant deletion; never deleted |
| `role_catalog` | `tenantId`, `roleId` | From the applied revision: `function`, `isAdmin`, scope per granted entity |
| `assignment` | `tenantId`, `memberRef` | `granted` and `usable` (encrypted role sets with scopes), `setAtVersion`, `rowSig` |
| `history` | `tenantId`, `seq` | One entry per accepted event, `seq` gap-free per tenant; `syncVersion` set only on entries that change `granted` (`bootstrap`, `change`, `member_removed`, `catalog_refresh`, `restore_reconciled`): `kind` (`bootstrap`, `change`, `member_removed`, `catalog_refresh`, `sync_verified`, `status`, `restore_reconciled`), `generation`, `memberRef`, encrypted before and after sets, `approvalRequestId` (unique per tenant), the signed assertions or evidence that authorised it, `prevHash`, `entryHash`, commit time. Append-only |
| `refusal_log` | `tenantId`, `seq` | Refused requests: reason code, request id, hashes, time. Append-only, own hash chain, not anchored, exported to the SEC-008 audit store |

1. **History is the store's audit trail** (ADR-0060 item 12), tenant-visible through a per-tenant audit view. `entryHash` covers the entry header (tenant, `seq`, version, generation, kind, `memberRef`, request id, assertion hashes) and the ciphertexts plus `prevHash`, so the chain still verifies after the tenant's key is destroyed (Q-582).
2. **Encryption happens in the service, not in the database** (R-M1). Role sets are encrypted with authenticated encryption under a per-tenant **assignment key**, a separate key from `S10b` (R-M5) wrapped by an in-country KMS key used only by the assignment service, and destroyed together with `S10b` at crypto-shred (ADR-0040 line 49). Associated data: `tenantId`, `memberRef`, column name (`granted`, `usable`, `before`, `after`), `setAtVersion` and `generation`. A ciphertext moved to another row, column or version fails to decrypt, and a failed decrypt denies. This stops misplaced or swapped ciphertext. It does not protect against a compromised read path, which can unwrap every tenant's assignment key in the country. Unwrapped keys stay in process memory only, for a bounded time set in the runbook (proposed 5 minutes); KMS unreachable with no unexpired key denies.
3. **Signed rows.** The write service signs every `assignment` row (`rowSig`: tenant, member, both ciphertext hashes, `setAtVersion`, `generation`) and the `tenant_state` row (`stateSig`: status, generation, versions, head) with a per-country **store-state key** in KMS, non-exportable, held only by the write service. The read path verifies with the public key. A direct edit that swaps `granted` into `usable`, lifts a fence or changes a version fails verification and denies (R-M4).
4. **Rebuild at any version** by folding `history`; used by the verifier and reconciliation, never by a live read.
5. **No other data.** No display names, contacts, agent grants or support principals (ADR-0060 item 15).

### 3. What the database enforces and what the service enforces (R-M1)
- **Database (procedures, constraints, grants):** version allocation in the write transaction; gap-free history with `prevHash` linking; unique `approvalRequestId`; compare-and-set on the target row's `setAtVersion`; refusal of every write while the tenant is not `active` (except the operation that lifts that state); refusal of bootstrap against a tombstone, a set `bootstrapped` flag or an existing `bootstrap` or `change` entry; `member_removed` and `tenant_delete` can only delete rows; `usable` promotion only up to the receipt version (6.3). Row-level security is forced on every table, so procedure owners are bound too (UNVERIFIED on the pinned version), and procedures also take the tenant as an argument and set it transaction-local.
- **Write service:** verification of the signed assertions (section 5), role catalog and `scope_conflict` checks, last-Owner rule, narrowing and widening classification, encryption, row and state signatures, anchor append.
- **Plainly:** a compromised write service can grant any role in its country, because the authorisation checks run there. It cannot reuse a version, skip the anchor or replay an approval without the anchor or the database refusing, and every grant it forges is detected by the verifier, which re-verifies every history entry's assertions with identity's public key (section 7). Compromise of both the write service and identity's assertion key grants roles undetected by signature; that residual stays (T53).

### 4. Versions, anchor and snapshots
1. **Anchor.** An append-only log per country, in-country, in a separate cloud account or project from the store, with its own credentials: the write service holds append-and-read only; the verifier and the audit reader hold read only; no principal holds update or delete, enforced by the storage itself (object lock or equivalent; UNVERIFIED per provider). It holds, per tenant, every history entry as written (header, ciphertexts, hashes, assertions) and a signed checkpoint per entry under the store-state key. It is a full encrypted copy of the assignment history, so it is placed and protected like the store (ADR-0060 items 7, 12, 14). Whether every market has such a home is UNVERIFIED (R-L6).
2. **Conditional append.** The anchor accepts an entry for a tenant only if its `seq` is the anchor's last `seq` for that tenant plus one and its `prevHash` equals the anchor's head. An entry, and so a version, can therefore exist only once.
3. **Anchor before effect** (R-H2). A write runs in one database transaction that locks the tenant row, allocates the next `seq` and, for a `granted` change, `v = lastIssuedVersion + 1`, writes history and rows, then appends that entry to the anchor and commits only after the anchor acknowledges. Nothing is usable, no snapshot is signed and no caller is told "done" before the commit. If the anchor is unreachable or refuses, the transaction rolls back and the write is refused; this blocks narrowing changes too during an anchor outage, which is accepted, because revocation goes through identity (6.5). The anchor call has a fixed timeout set in the runbook.
4. **Failure between the two.** Anchor acknowledged, database commit failed: the anchor is ahead. Anchor appended without acknowledgement, database rolled back: the next write's append for that `seq` is refused as a duplicate. Either way the tenant moves to `restore_fenced` (reads deny) and section 4.7 applies. No version is issued twice with different content, because the anchor holds the only accepted entry for each version.
5. **Snapshot binding.** The read path signs each full snapshot for `sync_members` with a per-country **snapshot key** (KMS, non-exportable, assignment service only), over `tenantId`, `generation`, `syncVersion`, the canonical payload hash, `issuedAt` and a short validity (proposed 10 minutes, R-L4). The adapter refuses a snapshot whose signature fails, whose tenant is not the tenant its store is bound to (ADR-0041), whose `generation` is lower than the highest it has accepted, whose version is not above its last applied one (ADP-C-063), or that has expired; nothing changes. A signature rather than a shared MAC, so the adapter can verify but not mint. `displayName` (`sync-members.schema.json` line 26) is joined from identity when the snapshot is built, covered by the payload hash, never stored here (Q-580).
6. **Detecting a store restore.** On start, after any restore, and on every verifier run, each tenant's `lastIssuedVersion` and `historyHead` are compared with the anchor. Store behind or different: `restore_fenced`. A restore procedure also fences every tenant of that store before the service starts.
7. **Reconciliation is a deterministic replay, never a free-form rebuild** (R-H3). The reconciliation tool (reviewed code in the assignment service) reads the tenant's anchored chain, verifies every link and checkpoint signature, and replays it to compute the assignment rows. The database procedure accepts only rows whose ciphertexts are the latest anchored `after` ciphertexts per member and whose chain digest matches the anchored head it re-hashes, and continues `seq` from the anchor; any other input is refused. Two people approve or refuse the result; they never edit it. A chain that does not verify leaves the tenant fenced, and the tenant is notified. The tool then records `restore_reconciled`, increments `generation`, and sets `lastIssuedVersion` above the maximum of the anchor's, the store's and the adapter's last applied version. `usable` for each member becomes the narrower of the restored and the replayed set until a full sync at the new generation verifies (6.3). Rows of members whose membership identity reports as removed are then removed (5.6). With two founders the two approvers are the founders (T52), and staff abroad acting on in-country data is a Q-14 question.
8. **Site restore.** `lastVerifiedSyncVersion` comes only from verified receipts (6.3). A site reporting a lower version or generation is restored or tampered: `site_fenced` until a full sync at a fresh version and the full drift check pass (ADR-0060 item 8; ADR-0039 item 9, line 49).

### 5. Writers and their authorisation
1. **Database roles**, each its own secret (ids assigned when SEC-002 updates secrets-management.md; none is `S22`):
   - `assign_reader`: `SELECT` on `assignment`, `tenant_state`, `role_catalog` and the member's latest history header, under forced row-level security; read path only.
   - `assign_writer`: `EXECUTE` on the write procedures only, no direct DML; write service only.
   - `assign_bootstrap`: `EXECUTE` on the bootstrap procedure only; the write service's bootstrap handler, never provisioning.
   - `assign_audit_reader`: `SELECT` on `history`, `refusal_log`, `tenant_state`; the verifier, reconciliation and the tenant audit view (filtered by tenant) (R-L2).
   - Schema owner: the reviewed migration pipeline only (IaC, hosting-rules line 13); a migration that changes assignment data is refused in review; credential sealed, two-person, alert on use.
2. **Approval assertions** (R-H1). Each human decision on an `AP-PERM-01` request produces an **assertion signed by identity** at the moment the person acts: kind (`initiate` or `approve`), `tenantId`, the actor's `memberRef`, principal kind `human`, session version, `approvalRequestId`, the canonical payload hash, the time of a step-up within 300 seconds (ADR-0007 item 6, line 23), issue time and a one-hour expiry. Identity signs only for a verified human session in that tenant with a fresh step-up; it never signs for agent, assistant, model, staff or service principals. The assertion key is identity's own, in-country KMS, separate from its token-signing key. The action-policy evaluator keeps its request records in the control plane in-country, outside the tenant site; those records drive the workflow and the screens but are **not** trusted for authorisation: they carry the assertions as evidence.
3. **A change is accepted only if all hold at execution time:**
   - the payload is `{tenantId, memberRef, rolesBefore, rolesAfter, expectedSetAtVersion}` and the two assertions are over its hash; both signatures verify;
   - the initiator assertion's actor holds a role with `function: owner` and the approver's a role with `function: owner` or `isAdmin: true`, both read from their current `usable` sets and the catalog flags, not from role names (R-L5); both memberships are active and their session versions still current (asked of identity; no answer denies);
   - approver differs from initiator; neither is the target (SOD-DIFF, SOD-NOT-SELF; Q-41);
   - the assertions are unexpired; `approvalRequestId` has not been used (database unique constraint) (R-M3);
   - the target row's `setAtVersion` equals `expectedSetAtVersion` and its decrypted `granted` equals `rolesBefore` (R-M3);
   - the tenant equals the tenant of the verified context that submits the execution; who submits does not matter, because the authority is the two assertions;
   - every role id is in `role_catalog`, the result has no `scope_conflict`, MFA is enrolled for the target where a role needs it;
   - the change does not leave the tenant with no active member holding a `function: owner` role (last-Owner rule, R-M8).
   A refusal goes to `refusal_log`, changes nothing, and is rate-limited per member and per tenant before any lock is taken (R-L3).
4. **Bootstrap** (the one exception ADR-0060 item 6 names; R-M2). During ADR-0040 Step 7, after the initial revision is applied and its catalog recorded (5.5), the bootstrap handler writes the first Owner assignment. It accepts only a statement signed by identity binding `tenantId`, `memberRef`, the verified signup identity and the provisioning `workflowId`. The procedure refuses when a tombstone exists for the tenant, `bootstrapped` is true, or any `bootstrap` or `change` entry exists, and sets `bootstrapped` in the same transaction. The role must be the catalog's only role with `function: owner`; zero or several refuse.
5. **Catalog refresh** (a write outside `AP-PERM-01`; R-M7). When a revision is applied, the write service records `catalog_refresh` only with evidence that the revision was approved under `AP-BPL-01` and applied: the build state machine's sealed approval evidence for the revision digest ([ADR-0050](ADR-0050-build-state-machine.md)) and the adapter's signed apply receipt for that digest and tenant. Roles come from the Blueprint registry by that digest, never from a request. A refresh is refused if it drops a role still assigned (`subject_in_use`, ADR-0039 line 47) or creates a `scope_conflict` in any existing assignment. While ADR-0039 item 8's reconciliation fence is held, `tenant_state.status` is `apply_fenced` and business reads deny.
6. **Remove-only lifecycle writes** (R-M8). `member_removed`: only on an identity-signed statement that the membership is removed and its session version bumped; deletes the row; refused if it would remove the last Owner (identity refuses that removal first; ADR-0007 item 12 recovers a lost owner account, never a role). `tenant_delete`: only with signed evidence of both approvals of ADR-0040 line 42 (the owner's identity-signed deletion assertion and a staff-realm second approval), never on the workflow's word; it deletes rows and writes the tombstone.
7. **Founders must confirm this reading of item 6** (Q-581, blocker): two remove-only operations (5.6), one constrained full rebuild (4.7) and catalog refresh (5.5), beside bootstrap.
8. **Staff and break-glass.** No staff, support or break-glass path writes assignments (ADR-0060 item 13); support access is an expiring PLT-019 grant, never a row here. Reconciliation is the one human-approved operation and its result is fixed by the anchor. Any other change to store data fails a signature or the chain and is a security incident with tenant notification.

### 6. Read path
1. **Every gateway request and every approved-action execution reads the store** (ADR-0060 item 10). Tenant from the verified token, `memberRef` from the membership the token names. The read path sets the tenant transaction-local before each query; a policy with the setting unset returns no rows; pooled connections never carry a tenant between transactions (R-M5).
2. **Checks on every read.** The read path itself denies (R-L1) unless: `stateSig` and `rowSig` verify; `status` is `active`; the row's `setAtVersion` and `granted` ciphertext hash equal the member's latest `granted`-changing history entry (stops a one-row rollback, R-M4); decryption succeeds; the decrypted `usable` is a subset of `granted`. Answer: `{tenantId, memberRef, generation, syncVersion, status, roles (usable)}`; the gateway checks the tenant against its claim.
3. **Narrowing now, widening after a verified sync** (ADR-0060 item 11). A removal sets `usable` to the narrower set in the same write. An addition leaves `usable` unchanged. The adapter's receipt must be signed and bound to tenant, generation, version and payload hash (contract ADR); the write service verifies it, raises `lastVerifiedSyncVersion`, and the promotion procedure sets `usable = granted` only for rows with `setAtVersion <= ` the receipt's version, after the drift fingerprint passes (R-M6). A late receipt for version 5 never promotes a row set at version 6.
4. **Deny on every failure** (ADR-0060 item 9): unreachable, timed out, partial, malformed, wrong tenant, failed signature or decrypt, KMS unreachable, tenant not `active`, unknown member, empty role set. No fallback to the engine copy, a cached set or a default role, and no switch that enables one.
5. **No cache.** Maximum age 0 until an ADR sets one (ADR-0039 D-2, `role-and-permission-mapping.md` line 165). Primary or synchronously committing replica only; within one request memoisation is allowed, across requests it is a cache.
6. **Revocation does not depend on the store.** Identity checks the per-membership session version on every call first (ADR-0007 item 10, line 27); removal and suspension work while the store or anchor is down. Row deletion follows (5.6). No role change is possible during a store, anchor or KMS outage: accepted.
7. **Availability.** The store and the anchor have uptime targets, monitoring and runbooks before a live tenant. An outage locks out a whole country: correct, and a denial-of-service target.

### 7. Sync, drift and the verifier
1. Each commit enqueues a full-snapshot sync to the tenant's adapter (outbox in the same transaction, released only after commit). A failed sync after a narrowing leaves the member narrowed at the gateway and is drift: alert, remove extra engine access first, fence if it cannot be removed (ADR-0060 item 11; ADR-0039 item 9).
2. The verifier runs at a fixed maximum interval (proposed 15 minutes, set in the runbook), after every restore and on start. Per tenant it checks: chain and checkpoints against the anchor; `assignment == fold(history)` and `usable ⊆ granted`; every history entry's assertions and evidence against identity's and the build machine's public keys; rows against live memberships in identity; engine fingerprint against the snapshot at `lastVerifiedSyncVersion`; site version and generation (4.8). Any mismatch alerts and fences. The store always wins; nothing read from the engine changes the store.

### 8. Lifecycle and residency
1. **Member removal** deletes the row (5.6). History stays as audit with `memberRef` and encrypted role sets; erasure is met by removing the `memberRef`-to-person link in identity ([data-retention.md](../security/data-retention.md) line 157).
2. **Tenant deletion** deletes `assignment`, `role_catalog` and `tenant_state`, writes the tombstone, and the assignment key is destroyed with `S10b`, leaving store history and the anchor copy unreadable but chain-verifiable. Whether a readable record of role history must survive for the statutory period, under which key and with which controls, is Q-582 (blocker; legal position UNVERIFIED). ADR-0040's deprovisioning list must add this step (partner's lane, follow-up).
3. **Residency.** As 1.1. A person with memberships in two countries has unrelated `memberRef` values in two stores.

### 9. Tests the implementation must ship (names are proposals)
- RAS-T01 cross-tenant read and write through the API and in the database under each role (joins SEC-004).
- RAS-T02 version reuse and caller-chosen version refused.
- RAS-T03 snapshot for another tenant, altered payload, lower version, lower generation, expired: refused by the adapter.
- RAS-T04 store restore drill fences the tenant and resumes above the maximum of anchor, store and adapter versions.
- RAS-T05 site restore fences until full sync.
- RAS-T06 every failure in 6.4 denies.
- RAS-T07 approval refusals: initiator equals approver, self-targeted, expired, voided, payload hash mismatch, initiator or approver lost the role after approving, forged or unsigned assertion, assertion without step-up, agent or staff principal.
- RAS-T08 the same approval executed twice; an approval whose `rolesBefore` or `expectedSetAtVersion` no longer matches.
- RAS-T09 `S22`, the provisioning identity and `assign_reader` cannot write; `assign_writer` cannot touch tables directly; schema-owner use alerts.
- RAS-T10 tenant setting unset returns no rows; a pooled connection does not carry the previous tenant; procedure owners are bound by row-level security.
- RAS-T11 `granted` ciphertext copied to `usable`, an old row put back, `tenant_state.status` edited: the read denies (signature, decrypt or latest-history check).
- RAS-T12 anchor unreachable, refusing or lagging: write refused, nothing usable, no snapshot signed.
- RAS-T13 restore where the anchor is ahead of the store and where the adapter is ahead of the anchor: no version issued twice; the adapter refuses a lower generation.
- RAS-T14 reconciliation input differing from the anchored replay refused; an unverifiable chain stays fenced.
- RAS-T15 a revocation is visible to the very next read; no asynchronous replica serves authorisation reads.
- RAS-T16 narrowing holds when sync fails; a late receipt does not promote a newer widening; a forged or unbound receipt is refused.
- RAS-T17 store, anchor or KMS down: membership removal and suspension still deny; reads deny.
- RAS-T18 bootstrap: provisioning-only statement refused, second bootstrap refused, bootstrap after a catalog refresh succeeds once, bootstrap after tenant deletion refused, catalog with zero or two owner roles refused.
- RAS-T19 `member_removed` without an identity statement refused; `tenant_delete` without both signed approvals refused; neither can add a role; the last Owner cannot be removed.
- RAS-T20 `unknown_role` and `scope_conflict` refused and logged; a catalog refresh that drops an assigned role or creates a conflict refused; a refresh without approval and apply evidence refused.
- RAS-T21 refused requests are rate-limited and do not take the tenant lock.
- RAS-T22 the verifier finds a direct table edit, a forged history entry and a row not matching live memberships within one interval.

### 10. Residual risk
The write service, identity's assertion key, the anchor and the store-state key are each country-wide targets; write service plus identity key together grant roles. Reconciliation separation of duties is weak with two founders (T52). A store, anchor or KMS outage blocks every role change in the country. None of it is tested until code exists.

### 11. How ADR-0060 items 6 to 14 and the round 1 findings are met
| Item | Met by | Round 1 findings |
|---|---|---|
| 6 Writers | 3, 5.1-5.8 | R-H1 (5.2, 5.3), R-H3 (4.7, 5.7), R-M1 (3), R-M2 (5.4), R-M3 (5.3), R-M7 (5.5), R-M8 (5.6), R-L3, R-L5 |
| 7 Keying and isolation | 2, 2.2, 2.3, 3, 6.1, 6.2 | R-M4, R-M5 |
| 8 `syncVersion` integrity | 4.2-4.8 | R-H2, R-H3, R-M6, R-L4 |
| 9 Deny on outage | 6.4, 6.6, 6.7 | R-H2 (anchor outage), R-M5 (KMS), R-L1 |
| 10 No stale reads | 6.1, 6.5 | none |
| 11 Store wins | 6.3, 7 | R-M6 |
| 12 Audit | 2.1, 4.1, 5.1, 7.2 | R-H2, R-M9 (open as Q-582), R-L2 |
| 13 Staff and break-glass | 4.7, 5.1, 5.8 | R-H3 |
| 14 Residency and lifecycle | 1.1, 4.1, 8 | R-M8, R-M9, R-L6 (UNVERIFIED) |

## Alternatives rejected
- **Tables in the control-plane workflow database under `S22`.** Forbidden by ADR-0060 item 6.
- **Trust the action-policy evaluator's approval record.** A compromise of whatever writes it mints role changes; identity-signed assertions make the evidence independent of the evaluator.
- **Asynchronous export to the anchor.** A version could be used and then reissued after a restore; anchor-before-effect with conditional append rules that out.
- **Staff rebuild after a restore.** A free-form rebuild is a staff write (item 13); only the anchored replay is accepted.
- **Encrypt inside the database.** The key would have to reach the database; the service encrypts and the database enforces only what it can see.
- **Reuse `S10b`.** Widens a storage-and-backup key to an online service; a separate assignment key is destroyed with it.
- **Application-only tenant checks; one store spanning countries; a shared MAC for snapshots; widening at the gateway before sync.** Break ADR-0060 items 7, 14, 8 and 11.

## Consequences
- Easier: one design for ERP-008 (snapshot, receipts, drift) and PLT-003 (bootstrap, deletion); `RoleResolver` already fails closed.
- Harder: per request one database read with two signature checks and a decrypt; per role change one synchronous anchor append; per country three KMS keys (store-state, snapshot, assignment-key wrapping), an anchor account and restore drills. T53 should be re-rated with this design.
- A sole-owner tenant cannot change anyone's roles (`AP-PERM-01` needs a second Owner or admin; Q-41 forbids R4 self-approval); invited members stay without a role (Q-583).
- **Blocking acceptance:** Q-581 (founders: the writes outside `AP-PERM-01`) and Q-582 (founders and counsel: retained role history after tenant deletion). Q-580 and Q-583 can follow acceptance but block implementation.
- Must be done before code: a re-review of this ADR by a different model; GOV-065; contract ADRs for the signed snapshot, the signed adapter receipt and the identity approval assertion; SEC-002 ids for the database credentials and the three keys; SEC-008 and the anchor's home; INF-001.
- No contract file changes in this ADR.

## Supersedes
none
