# ADR-0061: Design of the regional role-assignment store

Status: Proposed
Owner: eldon
Approved by: pending (security review by a different model, then both founders; RULES 42, Tier 3 in ADR-0035, because it touches auth and tenancy)

Plan ID: SEC-024. Design only. No code, no contract change: the Tool API wording is GOV-065, the `sync_members` snapshot binding needs its own contract ADR. [ADR-0060](ADR-0060-role-assignments-in-regional-store.md) item 15 (line 38) forbids any code that reads roles from, or writes assignments to, the store until this ADR and GOV-065 are Accepted, and this ADR needs its own security review showing how ADR-0060 items 6 to 14 are met. The table in section 9 maps each item to the design points that meet it.

## Context
- ADR-0060 (Accepted) moved member-to-role assignments out of the tenant's engine site into a regional store run by the platform (item 1, line 20), superseding [ADR-0007](ADR-0007-identity.md) item 9 (line 26). It left the technology, schema and deployment open (item 5, line 24) and bound them by security conditions items 6 to 15 (lines 29-38), taken from [adr-0060-security-review.md](../security/adr-0060-security-review.md) (findings H1-H3, M1-M7, L1-L4).
- What reads and writes the store: the gateway reads the caller's roles per request (ADR-0007 item 2, line 19; [contracts/tool-api.md](../../contracts/tool-api.md) section 4 step 2, line 100). The adapter receives full snapshots through `sync_members` at a store-issued `syncVersion` (contract ADP-C-063, `contracts/engine-adapter.md` line 379; `sync-members.schema.json` line 17). [ADR-0039](ADR-0039-role-and-permission-mapping.md) (Proposed) item 7 (lines 35-43) and item 8 (lines 44-48) define the fail-closed rules and the apply-sync fence; [ADR-0040](ADR-0040-tenant-provisioning-service.md) (Proposed) Step 7 (line 25) needs the first full sync at a store-issued version.
- Role changes are action-policy row `AP-PERM-01` ([action-policy-table.md](../security/action-policy-table.md) line 180): R4, Owner initiates, a second different Owner or admin approves, never self-targeted, agents draft only, one-hour expiry, no break-glass. Role loss voids a pending approval (line 75). Tenant break-glass is never for permission changes (line 131); platform break-glass never changes permissions in a tenant (line 138). Q-41 (resolved 2026-11-22) forbids self-approval of R4 rows.
- Today the control-plane regional database credential `S22` is held by "control-plane and provisioning services" ([secrets-management.md](../security/secrets-management.md) line 36), and control-plane compromise (T53) is rated "gap" ([threat-model.md](../security/threat-model.md) line 216). ADR-0060 item 6 forbids `S22` from giving assignment write access.
- Existing code: `services/control-plane/identity/policy.py` lines 26-41 already take roles only from an injected `RoleResolver` and fail closed on any unexpected answer; membership removal and suspension bump a session version in identity (`identity/service.py` lines 164, 185, 192). No store exists.
- Hosting is not chosen (INF-001, partner). Placement rules are in [hosting-rules.md](../security/hosting-rules.md) lines 11-18 (KSA and UAE only; daily in-country backups; per-tenant envelope keys; immutable audit logs). Legal positions per market are UNVERIFIED until counsel reviews them.

## Decision

### 1. Shape and placement
1. **One store instance per served country**, in that country, with its backups, replicas, logs and key material in the same country (ADR-0060 item 14; hosting-rules lines 11, 15, 16). Records of different countries are never replicated, joined or queried together. A market with no in-country location is not served (Egypt and Qatar today; UNVERIFIED, pending INF-001, a founder decision and counsel).
2. **Its own logical database, not the control-plane workflow database.** It has its own database credentials (section 4), so `S22` and the provisioning workflow reach nothing in it. It sits in its own network segment, reachable only from the assignment service (section 2).
3. **Technology.** A relational database with serializable or row-locking transactions, row-level security bound to a per-session tenant setting, stored procedures that run with definer rights, and in-country managed or self-run hosting. PostgreSQL meets these on paper and is the reference shape for the review; the choice, its licence and its hosting are UNVERIFIED until INF-001 and LEG-004 record them. Nothing in this ADR depends on a vendor feature that a second relational engine lacks.
4. **One service in front of it**, the assignment service, in `services/control-plane/` (Eldon's lane). It has two separately deployed parts with separate credentials: the **read path** (gateway lookups, snapshot reads) and the **write service** (the only writer, ADR-0060 item 6). The gateway (`services/gateway/`, partner) and the adapter (`apps/engine/`, partner) consume it through interfaces fixed by later contract ADRs.

### 2. Schema (logical)
All tables are keyed by the platform-generated `tenantId` (ADR-0040 line 16). Members are identified by `memberRef`, the identity service's per-tenant membership id: random, platform-generated, never reused, never a person id, email or phone (ADR-0060 item 14). The store holds no names.

| Table | Key | Columns (purpose) |
|---|---|---|
| `tenant_state` | `tenantId` | `country`; `status` (`active`, `restore_fenced`, `site_fenced`, `deleting`); `generation` (restore epoch, section 3.3); `lastIssuedVersion`; `lastVerifiedSyncVersion` (highest version the adapter receipt and drift check confirmed); `appliedRevision` and its digest; `historyHead` (hash of the newest history entry); `bootstrapped` (bool) |
| `role_catalog` | `tenantId`, `roleId` | Roles active in the applied Blueprint revision with each role's scope per granted entity, so the store can refuse an unknown role and a `scope_conflict` (ADR-0039 item 4, line 32; item 7, line 40) |
| `assignment` | `tenantId`, `memberRef` | `granted` (the committed role set with scopes); `usable` (what the gateway may use now, section 5.3); `setAtVersion`; both role sets encrypted (section 2.2) |
| `history` | `tenantId`, `seq` | One entry per event, `seq` gap-free per tenant; `syncVersion` set only on entries that change roles: `kind` (`bootstrap`, `change`, `member_removed`, `catalog_refresh`, `sync_verified`, `restore_reconciled`, `refused`), `generation`, `memberRef`, roles and scopes before and after, `approvalRequestId`, approved payload hash, actor and approver refs, `prevHash`, `entryHash`, commit time. Append-only |

1. **History is the store's audit trail.** It is the tenant-visible, append-only record ADR-0060 item 12 asks for, kept in the tenant's country. Each `entryHash` covers the canonical entry plus `prevHash`, forming one chain per tenant. Refused writes are recorded as `refused` entries that change no role and consume no `syncVersion`. The chain head is exported off-box with each entry to the audit store of SEC-008 and to a signed checkpoint outside the store's backup boundary (T56, line 219). The external copy is the anchor that catches a rewrite of both chain and head (the gap recorded for other stores in Q-481 and Q-502).
2. **Encryption.** Role sets in `assignment` and `history` are encrypted under the tenant's own envelope key (`S10b`, secrets-management line 24) with authenticated encryption whose associated data is `tenantId`, `memberRef` and, for history, `syncVersion` and `generation`. A row read under the wrong tenant context, or moved to another row, fails to decrypt, and a failed decrypt denies (section 5). This adds a cryptographic tenant boundary under the row-level policy.
3. **Rebuild at any version.** Folding `history` up to version N rebuilds the assignment set at N (ADR-0060 item 12). The drift check and investigations use this; no live path does.
4. **No other data.** No display names, contacts, agent grants or support principals. Agent grants and support principals may join the store only by a later ADR under the same conditions and their own writer rules (ADR-0060 item 15; [agent-least-privilege.md](../security/agent-least-privilege.md); PLT-019).

### 3. `syncVersion`, snapshots and restore
1. **Allocation.** The write procedure locks the tenant's `tenant_state` row, sets `syncVersion = lastIssuedVersion + 1`, inserts the history entry, updates `assignment` and `tenant_state` in the same transaction, and commits all or nothing. The version is never chosen by a caller and never reused (ADR-0060 item 8). It is a column of the procedure, not an input.
2. **Snapshot binding.** A snapshot for `sync_members` is built by the read path from `assignment.granted` at one version and signed with a per-country signing key held in in-country KMS, non-exportable, usable only by the assignment service. The signed statement covers `tenantId`, `generation`, `syncVersion`, snapshot kind (full) and the hash of the canonical payload. The adapter verifies the signature, that `tenantId` equals the tenant its store is bound to (ADR-0041 tenant binding), and that the version is above its last applied one (ADP-C-063); any failure refuses the snapshot and changes nothing. A signature, not a shared MAC, so the adapter can verify but never mint a snapshot. The schema fields for this are a contract ADR (Eldon's lane), not this ADR. `displayName` in the payload (`sync-members.schema.json` line 26) is joined from identity when the snapshot is built and is covered by the payload hash, never stored here (Q-580).
3. **Store restore.** Every committed version is exported off-box with its chain head (2.1), so the highest version ever issued per tenant survives outside the store's backups. On start, and after any restore, the assignment service compares each tenant's `lastIssuedVersion` and `historyHead` with the external anchor. If the store is behind or differs, the tenant moves to `restore_fenced`: every read for it denies, every write is refused. A human-reviewed reconciliation (runbook, two people, tenant notified) rebuilds the set from the exported history, records a `restore_reconciled` entry, increments `generation`, and sets `lastIssuedVersion` above the highest anchored version, so versions resume above any ever issued. A restore procedure also fences every tenant of that store explicitly before the service starts, so detection does not rest on the comparison alone.
4. **Site restore.** The store records `lastVerifiedSyncVersion` from adapter receipts. The drift check compares it with the version the site reports. A site reporting a lower version has been restored or tampered with: the tenant moves to `site_fenced` until a full sync at a fresh version and the full drift check pass (ADR-0060 item 8; ADR-0039 item 9, line 49).

### 4. Writers and their authorisation
1. **Database roles.** Three login roles per store, each a distinct secret (ids assigned when SEC-002 updates secrets-management.md; none of them is `S22`):
   - `assign_reader`: `SELECT` on `assignment`, `tenant_state` and `role_catalog` only, through row-level security bound to the tenant set for the session; held by the read path.
   - `assign_writer`: `EXECUTE` on the write procedures only, no direct `INSERT`, `UPDATE` or `DELETE` on any table; held by the write service.
   - `assign_bootstrap`: `EXECUTE` on the bootstrap procedure only; held by the write service's bootstrap handler, never by provisioning.
   - Schema owner: used only by the reviewed migration pipeline (IaC, ADR-0040 style, hosting-rules line 13). Migrations change structure; a migration that changes assignment data is refused in review. Its credential is sealed, two-person, alerting on use.
2. **The procedures enforce the invariants** (version allocation, chain, encryption associated data, catalog check, history-first, refusal of writes in a fenced or deleting tenant), so a compromised write service still cannot reuse a version, skip the chain or write into a fenced tenant.
3. **A change is only the execution of an approved `AP-PERM-01` request.** The write service's change entry point takes one argument, an approval request id. It reads the request from the action-policy evaluator, not from the caller, and accepts it only if all hold at execution time:
   - state `approved`, not voided or expired (one hour), payload hash recomputed and equal (action-policy-table line 64);
   - initiator holds an Owner role and approver holds an Owner or admin role in the tenant, both re-read from this store now (ADR-0060 item 10), both active members with live session versions;
   - approver is not the initiator, and neither is the target member (SOD-DIFF, SOD-NOT-SELF; Q-41 forbids self-approval for R4);
   - both are human principals; agent, assistant, model, staff and service principals are refused as initiator, approver or executor (ADR-0060 item 6; prompt-injection-defence goal G-C, line 37);
   - tenant, member and roles come from the approved payload only; the tenant must equal the tenant of the verified context of the call that triggers execution (ADR-0007 item 3, line 20);
   - every role id is in `role_catalog`, the resulting set has no `scope_conflict`, and MFA is enrolled for the target when a role needs it (ADR-0007 item 6, line 23).
   A refusal writes a `refused` history entry and changes nothing.
4. **Bootstrap (the one named exception, ADR-0060 item 6).** During ADR-0040 Step 7, after the initial Blueprint revision is applied and `role_catalog` is filled, the bootstrap handler writes the first Owner assignment. It accepts only a statement signed by the identity service binding `tenantId`, `memberRef`, the verified signup identity and the provisioning `workflowId`; provisioning's own word is not enough. The procedure refuses it when any history entry exists for the tenant or `bootstrapped` is true, so it runs once by construction. It is audited as `bootstrap`.
5. **Catalog refresh.** When a Blueprint revision is applied, the write service loads that revision's roles from the Blueprint registry by revision digest bound to the tenant (never from a request) and records a `catalog_refresh` entry. A revision that drops a role still assigned is refused before apply (`subject_in_use`, ADR-0039 line 47), so the catalog never orphans an assignment.
6. **Narrowing-only lifecycle writes.** Member removal and tenant deletion must delete assignment rows (ADR-0060 item 14), but item 6 names only bootstrap as an exception to `AP-PERM-01`. This ADR proposes two more store operations that can only remove, never grant, each audited: `member_removed`, accepted on a signed identity statement that the membership is already removed (status removed, session version bumped); and `tenant_delete`, accepted only from the deprovisioning workflow after its two approvals (ADR-0040 line 42). Restore reconciliation (3.3) is the third. They need founder confirmation as a reading of item 6 (Q-581); until then they are design only, like the rest of this ADR.
7. **Staff and break-glass.** No staff, support or break-glass path writes assignments (ADR-0060 item 13). Support access is a separate expiring grant (PLT-019), never a row here. Any change to store data that is not a procedure call by `assign_writer` or `assign_bootstrap` breaks the chain or the external anchor, is found by the drift check (section 6), and is handled as a security incident with tenant notification.

### 5. Read path
1. **Every gateway request and every approved-action execution reads the store** (ADR-0060 item 10). The tenant comes only from the verified token; `memberRef` comes from the membership the token names. The read path sets the session tenant from those claims before querying, so row-level security and the decryption associated data both bind to it.
2. **Answer.** `{tenantId, memberRef, generation, syncVersion, roles (usable)}`. The gateway checks that `tenantId` equals its claim and that `status` is `active`.
3. **Narrowing now, widening after sync** (ADR-0060 item 11). A change that removes a role or scope sets `usable` to the narrower set in the same transaction. A change that adds one leaves `usable` as it was; after the adapter's receipt for that version verifies and the drift fingerprint passes, the write service records `sync_verified` and sets `usable = granted`. A change that both removes and adds narrows at once and widens after sync.
4. **Deny on every failure** (ADR-0060 item 9): unreachable, timed out (a fixed budget set in the runbook), partial, malformed, wrong tenant, decrypt failure, fenced or deleting tenant, unknown member, empty role set. No fallback to the engine copy, a cached set or a default role, and no switch that enables one.
5. **No cache.** Maximum age is 0 until an ADR sets one (ADR-0039 open decision D-2, `role-and-permission-mapping.md` line 165). Reads go to the primary or to a replica that acknowledges commits synchronously; asynchronous replicas are never used for authorisation reads. Gateway-side memoisation within one request is allowed; across requests it is a cache.
6. **Revocation does not depend on the store.** Identity checks the per-membership session version on every call before roles are read (ADR-0007 item 10, line 27); removal and suspension bump it (`identity/service.py` lines 185, 192) and work while the store is down. Assignment rows of a removed member are deleted afterwards (4.6). A tenant can still not change roles during a store outage; that is the accepted cost.
7. **Availability.** The store has its own uptime target, monitoring and runbook before it serves a live tenant. A store outage locks out every tenant in that country: correct, and a denial-of-service target (adr-0060-security-review M1).

### 6. Sync and drift
1. Each committed change enqueues a full-snapshot sync to the tenant's adapter at once (transactional outbox in the store, same transaction). A sync failure after a narrowing change leaves the member narrowed at the gateway; it is drift: alert, remove the extra engine access first, fence the tenant if it cannot be removed (ADR-0060 item 11; ADR-0039 item 9).
2. The drift check compares the engine fingerprint with the snapshot at `lastVerifiedSyncVersion`, verifies the history chain against the external anchor, and checks `lastVerifiedSyncVersion` against the site (3.4). The store always wins: nothing read from the engine changes or repairs the store.

### 7. Lifecycle and residency
1. **Member removal** deletes the member's `assignment` row (4.6). History entries stay as the audit trail; they hold only `memberRef` and role ids, and erasure is met by removing the `memberRef`-to-person link in identity, as for other audit logs ([data-retention.md](../security/data-retention.md) line 157).
2. **Tenant deletion** deletes `assignment`, `role_catalog` and `tenant_state` rows in ADR-0040's `delete_site` step; the history copy in the store goes with the crypto-shred of `S10b` (ADR-0040 line 49). The off-box audit copy (2.1) is what survives, under data-retention section 9 (Q-582). ADR-0040's deprovisioning list must add this step (partner's lane, follow-up).
3. **Residency.** As 1.1. A person with memberships in two countries has unrelated `memberRef` values in two stores; nothing links them inside this design.

### 8. Tests the implementation must ship (names are proposals)
RAS-T01 cross-tenant read and write through the API and directly in the database under each role (joins SEC-004); RAS-T02 version reuse and caller-chosen version refused; RAS-T03 snapshot for another tenant, altered payload, lower version refused by the adapter; RAS-T04 store restore drill fences the tenant and resumes above the anchored version; RAS-T05 site restore fences until full sync; RAS-T06 every failure in 5.4 denies; RAS-T07 agent, staff and self-targeted `AP-PERM-01` refused; RAS-T08 bootstrap runs once; RAS-T09 widening not usable before sync; RAS-T10 direct table edit is detected by the drift check; RAS-T11 member removal and tenant deletion leave no assignment rows; RAS-T12 audit write failure fails the assignment write.

### 9. How ADR-0060 items 6 to 14 are met
| Item | Met by |
|---|---|
| 6 Writers | 4.1-4.7; 1.2 (no `S22` reach) |
| 7 Keying and isolation | 2 (keys), 2.2 (encryption), 4.1 (row-level security), 5.1 |
| 8 `syncVersion` integrity | 3.1-3.4 |
| 9 Deny on outage | 5.4, 5.6, 5.7 |
| 10 No stale reads | 5.1, 5.5 |
| 11 Store wins | 5.3, 6 |
| 12 Audit | 2.1, 2.3, 4.3 (refusals), RAS-T12 |
| 13 Staff and break-glass | 4.1 (schema owner), 4.7 |
| 14 Residency and lifecycle | 1.1, 2 (`memberRef`), 7 |

## Alternatives rejected
- **Tables in the control-plane workflow database under `S22`.** ADR-0060 item 6 forbids `S22` write access; separating grants inside one database shared with provisioning is weaker than a separate database and credential set.
- **Application-only tenant checks.** ADR-0060 item 7 requires the store to enforce the boundary; row-level security plus tenant-bound decryption gives two store-side checks.
- **One store per region spanning countries.** Moves one country's data abroad (ADR-0060 item 14).
- **A version counter only inside the store.** Lost on restore; the external anchor (3.3) is what makes the highest issued version survive.
- **A shared MAC for snapshots.** The adapter could mint snapshots; a signature limits minting to the assignment service.
- **Separate audit table beside history.** Two records of one change can disagree; one hash-chained history exported off-box is the audit trail.
- **Widen at the gateway before sync.** Breaks ADR-0060 item 11.

## Consequences
- Easier: one design that ERP-008 (snapshot consumer, drift) and PLT-003 (bootstrap, deletion step) can build on once Accepted; `RoleResolver` in `identity/policy.py` already has the right fail-closed shape for the read path.
- Harder: one database read per request on the authorisation path; per-country signing keys, credentials and anchors to run; restore drills per country. The store is a country-wide high-value target: these controls narrow and detect, they do not remove it. T53 should be re-rated with this design (adr-0060-security-review, residual risk).
- A sole-owner tenant cannot change anyone's roles: `AP-PERM-01` needs a second Owner or admin and Q-41 forbids self-approval for R4. Invites still work, but an invited member has no role and is denied everything until a second Owner or admin exists (Q-583).
- Must be done before any code: security review of this ADR by a different model (SEC-024); founder answers to Q-580 to Q-583; GOV-065 (Tool API wording); a contract ADR for the signed `sync_members` snapshot; SEC-002 assigning the three credentials and the signing key; INF-001 choosing in-country hosting; SEC-008 for the off-box audit anchor.
- No contract file changes in this ADR.

## Supersedes
none
