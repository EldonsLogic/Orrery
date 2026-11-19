# Tenant provisioning

Status: draft
Owner: partner
Approved by: pending (with [ADR-0040](../decisions/ADR-0040-tenant-provisioning-service.md))

Plan ID: PLT-003. Detail for ADR-0040. Nothing here is built. Internal documentation; it may name the engine ([ADR-0016](../decisions/ADR-0016-engine-invisibility.md)). Depends on ADR-0038 (secrets, open PR #128), ADR-0039 (role mapping, open PR #129), and ADR-0041 (durable adapter state, open PR #126), referenced in plain text until those ADRs land on `main`.

## 1. Workflow record (control-plane regional database, credential `S22`)
| Field | Rule |
|---|---|
| `workflowId` | ULID |
| `tenantId` | Platform-generated; **globally unique and never reused** after cancellation or deprovisioning |
| `slug` | Canonical & homograph-normalized slug (`T51`); enforced by a DB unique index across active and quarantined slugs |
| `kind` | `provision` or `deprovision` |
| `requestHash` | sha256 of the canonical request; a second request for the same tenant with another hash is `conflict` |
| `request` | Verified caller identity (`PROV-001`), region, country pack, engine version set, site class (`sandbox` or `production`), Blueprint id and platform-approved revision (`ADR-0005`), owner membership ref |
| `placement` | bench pool and database server, written once in `reserve` |
| `secretIds` | ids, versions, and `{workflowId, state}` tracking from `SecretStore`, never values |
| `steps[]` | `{name, state, attempts, lastErrorCode, startedAt, finishedAt, idempotencyKey, evidenceRef}` |
| `state` | `running`, `awaiting_approval`, `waiting_grace`, `waiting_recovery_window`, `blocked`, `cancelling`, `cancelled`, `done` |
| `resumeAt` | Scheduled wake timestamp when parked in `waiting_grace` or `waiting_recovery_window` (worker lease released while parked) |
| `approvals` | For live (non-trial) deprovisioning: recorded tenant owner deletion request + second staff approval |
| `lease` | worker id, expiry, fencing token (monotonic); active holds checked under transactional DB lock (`SELECT ... FOR UPDATE`) before destructive calls |

## 2. Provisioning steps
| # | Step | Observe first | Act | Post-condition | Idempotency |
|---|---|---|---|---|---|
| 1 | `reserve` | Record has placement and reserved slug? | Atomic DB unique-index claim on canonical/homograph-normalized slug (`T51`); choose pool and server by capacity | Placement and permanently reserved slug persisted | Placement never re-chosen; slug unique across distinct `tenantId`s |
| 2 | `create_secrets` | Metadata & `{workflowId, state}` at each fixed path? | Reserve workflow-bound metadata for `S05`, `S08`, `S21` (values created in Step 3); put-if-absent `S09` (principal-kind-bound impersonation), `S10b` (per-tenant DEK/backup DEK wrapped under `S10a`); bind/verify pool `S07` | S05/S08/S21 reserved with no values; other secrets active; all stamped with current active `workflowId`; ids recorded. Any `pending_destruction` or foreign `workflowId` blocks (`PROV-T31`) | Fixed paths from never-reused `tenantId` |
| 3 | `create_site` | Adapter `site_status` **plus** raw MariaDB DB & `sites/<tenant>` filesystem residue | Execute via `provisioning-site-init` (ephemeral custody of `S06`/`S08`/`S05`; steady-state `engine-adapter` never holds `S06`/`S08`; file/fd/stdin/SQL secret delivery inside container before production, closing `scripts/provision_tenant_site.py` argv gap; or `site.schema.json` ADR). Reconcile partial DB/site residue if target matches, and **create `ADR-0041` adapter tables (`init_adapter_state`) immediately upon DB creation before app installs finish** | `site_status == ready`, matching target, apps installed, `adapter_sites` populated (`PROV-T33`) | Contract 5.2 + deterministic partial-site repair; `site_exists_different_target` blocks |
| 4 | `harden_site` | Read settings | Customer login off (`UNVERIFIED` on pinned version until bench test), engine email off, developer mode off, Administrator login off (`UNVERIFIED` on pinned version until bench test; does not block `sync_members` or `SEC2-042` break-glass) | All settings verified | Setting writes are absolute values |
| 5 | `verify_adapter_state` | `ADR-0041` schema & tables reachable? | Verify/repair durable `ADR-0041` store created in Step 3; refuse in-memory store in production | Durable store reachable; production in-memory fails (`PROV-T21`) | Idempotent DDL check |
| 6 | `verify_site` | n/a | `health`, `capabilities`, installed app list | All pass | Read-only |
| 7 | `apply_initial_blueprint` | `site_status.applied` equals target revision? | `plan`; if `needs_gate_approval`, transition to lease-releasing `awaiting_approval` until `gateApproved` arrives (re-`plan` without counting retries if 900s `planToken` expires); `apply` with key `apply:{tenantId}:{revision}` and `onBehalfOf` approving owner | Outcome `applied` or `already_applied`; role/level/transition rules, full membership sync and full drift fingerprint verified under one permission-reconciliation fence before apply reports success; export hash recorded | Contract 5.6 and section 7 (`PROV-T39`) |
| 8 | `sync_members` | Last applied `syncVersion` | verify the full `sync_members` receipt from Step 7 using its store-issued monotonic `syncVersion`; if missing or stale, reconcile within the Step 7 fence before any success is reported (`ADR-0039`; external-store move blocked on Q-210 on PR #129), enforcing no `scope_conflict` and disabled zero-role users | Counts match; ADR-0039 `RM` checks pass; on failure site stays non-routable (`PROV-T15`, `PROV-T39`) | Contract 5.9 (`stale_sync_version` on replay with another key) |
| 9 | `baseline_permissions` | Baseline stored? | Compute and check full `ADR-0039` drift fingerprint across all engine users (managed + built-in/automatic) and unmapped/mapped DocTypes | Expected equals actual; baseline stored | Pure function |
| 10 | `register_route` | Route exists & invisibility probe passed? | Register internal/disabled gateway route (`PLT-024`), run **gateway-path invisibility probe** (`PLT-024`, `ERP-020`: zero engine markers in paths, headers, cookies, error bodies; `PROV-T32`), then bind public host on pass only | Invisibility probe passes; public route active; foreign tenant token refused | Upsert of an absolute value |
| 11 | `ready` | Lifecycle state | Hand over to PLT-004 (`trial` or `active`); emit `tenant.state_changed` | State recorded | Same state is a no-op |

E-invoice unit onboarding (CMP-007) is not a provisioning step. It needs an owner's OTP and runs later, on demand.

Step 2 reserves S05/S08/S21 metadata only. Step 3 generates their values locally inside the site-init container and writes through a tenant/workflow-bound create-only identity with no store reads or policy administration. A crash with existing active secrets uses a separate short-lived read/use identity for the same workflow (no create, rotate, delete or policy rights); the steady-state adapter holds neither S06 nor S08. Recovery never regenerates or replaces an existing active secret blindly.

Step 7 includes full sync and fingerprint verification before apply reports success; Steps 8–9 verify its receipt and baseline. All remain fenced and non-routable on failure. A fresh plan after approval expiry must revalidate approvals against the exact revision/hash; changed material input requires fresh human approval. ADR-0005 requires team review before build and again before live, regardless of whether the adapter plan is gated.

## 3. State machine
- Active step: `pending` -> `running` -> `done`; `running` -> `failed_retryable` -> `running` (backoff, max 5 attempts); `failed_retryable` -> `blocked` after 5 attempts; any state -> `blocked` on non-retryable error (e.g., `pending_destruction` secret, `site_exists_different_target`, drift mismatch).
- Parked wait states (release worker lease while waiting):
  - `awaiting_approval`: Step 7 waiting on `needs_gate_approval`; wakes on `gateApproved` and re-runs `plan` cleanly if `planToken` expired (`>900s`) without consuming retries.
  - `waiting_grace` / `waiting_recovery_window`: Deprovisioning multi-day waits (`data-retention.md` D-1, D-5) with `resumeAt`; worker releases lease and a scheduler resumes when `now >= resumeAt` and no legal hold exists.
- Workflow: `running` while active steps advance; `blocked` when a step blocks; human `resume` sets blocked step to `pending`; human `cancel` sets `cancelling`, runs compensation (section 4), then `cancelled`; all steps `done` sets `done`.
- Lease: a worker takes a lease with a monotonic fencing token only for active execution (never held across multi-day waits or gate approvals). Every state mutation carries the token, and stale writes are refused.

## 4. Failure matrix
| Failure | Handling |
|---|---|
| Crash after a secret is created, before it is recorded | Re-run observes secret metadata; adopts **only** if `state == "active"` and `metadata.workflowId == currentWorkflowId`; `pending_destruction` or foreign `workflowId` blocks (`PROV-T31`) |
| Crash inside Step 3 after MariaDB DB or `sites/<tenant>` created, before `adapter_sites` / app install finishes | Step 3 observes raw DB + filesystem residue, verifies target match, runs `init_adapter_state` and finishes install idempotently—never wedging on absent `adapter_sites` (`PROV-T33`) |
| Crash after site completes, before workflow record updates | `site_status` matches target; adopted cleanly |
| Concurrent signup with same canonical/homograph slug (`tenantId` A vs B) | Control-plane DB unique index on canonical slug allows one winner and rejects the other at `reserve` (`PROV-T34`) |
| Site exists with a different target | `blocked`; human decides |
| `provision_site` deadline passes | Retry with the same key returns `in_progress` or final status |
| Hardening setting or Step 10 gateway invisibility probe fails | `blocked`; public host route is **never** bound without both passing (`PROV-T32`) |
| Initial apply paused at `gated` longer than 900s `planToken` TTL | Parks in `awaiting_approval` (lease released); resume re-plans cleanly with no retry penalty (`PROV-T39`) |
| Initial apply `rejected` or `compensated` | `blocked` with outcome; resume needs a new approved revision |
| Initial apply `recovery_required` | `blocked`; adapter site blocked; human repair |
| Assignment store unavailable during the full sync inside Step 7 | Step 7 compensates or enters `recovery_required`, retaining the permission fence until verified recovery; never reports `applied`; Steps 8–10 remain incomplete (`PROV-T39`) |
| Drift baseline mismatch | `blocked`; security signal, not retried blindly |
| Secret store unavailable | Fail closed; retry; then `blocked` (`SEC2-037`) |
| Region capacity exhausted | `blocked` before any resource is created |
| Cancel before `register_route` (under legal-hold lock) | Reverse compensation: remove disabled/internal route if any, delete partial/empty site & DB, schedule workflow secrets for destruction, **permanently tombstone slug** (`PROV-T34`), mark `cancelled` (`PROV-T36`) |
| Cancel after `ready` | Not allowed; use deprovisioning |

## 5. Deprovisioning steps
Deleting a live (non-trial) tenant requires recorded owner deletion request + independent second staff approval bound to tenant, action hash, revision and expiry (`PROV-015`). Before **every** destructive external call (Steps 5, 6, 7, and pre-route `cancel`), the worker executes an atomic control-plane DB transaction (`SELECT ... FOR UPDATE` + fencing token against active legal holds); hold creation and destructive dispatch serialize on the same per-tenant lock. Persist hold requests immediately; never reject or silently discard a requested hold. Re-check pending/active holds and the current fencing token for each target immediately at dispatch, not just at step entry. A target-side executor must reject stale fences and duplicate operation ids; if the store cannot enforce these, use a single guarded executor. Hold acknowledgement occurs only after any already-dispatched call is resolved, recording its outcome; no later call dispatches once a hold is pending. Unknown outcomes block further destruction for reconciliation. A DB check followed by an unlocked external call is insufficient.

| # | Step | Gate | Idempotent & DB-loss safe because |
|---|---|---|---|
| 1 | `close_access` | Lifecycle says suspend or delete (dual approval for live deletion) | Remove route, bump sessions, **engage per-tenant agent kill switch (`ALP-035`), durably disable agent engine users and reject new triggers/model calls, drain or refuse in-flight work before step completion; drop queued triggers (`ALP-025`), pause connector jobs (`DSC-010`), halt e-invoice submissions (`CMP-007`)** — all absolute |
| 2 | `final_export` | Not for trials that never went live (data-retention section 7) | Export manifest hash recorded; re-run reuses it |
| 3 | `grace_wait` | Parked `waiting_grace` (`resumeAt` = start + D-1, lease released); legal hold stops here and all later steps | Timer from recorded start |
| 4 | `disable_principals` | No hold | Disable shadow, agent, and support engine users (absolute) |
| 5 | `delete_site` | Atomic legal-hold lock + fencing token immediately before external calls | Deletes **all** stores per `data-retention.md` section 7 step 5: live site, tenant DB (also dropping `ADR-0041` `adapter_*` tables), object/file store & brand asset prefixes, search indexes, caches, per-tenant memory, chat transcripts, embeddings, AI gateway prompt/output logs, and tenant Blueprint/event artifacts. Retries rely strictly on control-plane state + store probes (never deleted tenant DB); absent target = success |
| 6 | `destroy_secrets` | Atomic legal-hold lock + fencing token | Destroys `S05`, `S08`, `S09`, `S21`, and ZATCA `Z1`–`Z5` (never exported); then parks in `waiting_recovery_window` (`resumeAt`, lease released) for recovery window (data-retention D-5, SEC-002 D-3) |
| 7 | `crypto_shred` | Atomic legal-hold lock after recovery window | Destroys per-tenant `S10b` DEKs & backup DEKs only (never shared regional `S10a` KEK); already destroyed = success |
| 8 | `verify_and_certify` | All above `done` | Probes every external/AI/search/storage system directly for `tenantId` absence (no tenant DB dependency), records permanently tombstoned slug, issues certificate once (`DAT-007`) |

## 6. Audit
Every step transition writes an internal audit record in the control-plane regional DB: `auditId`, `workflowId`, `tenantId`, actor (service or staff id, plus dual approvers for live delete), step, input hash, outcome, error code, timings, fencing token. Never contains a secret or customer-visible engine name. The **immutable deletion tombstone and statutory evidence subset** (offboarding approval hashes, legal hold history, export manifest hash, certificate `DAT-007` verification hash) is retained for the longest statutory market period (`data-retention.md` section 6), while operational trace logs and ephemeral workflow noise purge per operational retention. Events: `tenant.state_changed`, `data.exported`, `data.deleted`; `engine.site_provisioned` waits on the events contract ADR.

## 7. Requirements
| ID | Requirement |
|---|---|
| PROV-001 | Only control-plane staff tooling and a rate-limited signup flow backed by a verified identity can start provisioning; `tenantId` is platform-generated & never reused, and region, pack, and Blueprint revision come from platform state (`PROV-T35`) |
| PROV-002 | Workflow state is durable in the control-plane regional DB (`S22`) before the first external action |
| PROV-003 | Every step observes before acting (including partial DB/filesystem state in Step 3) and verifies after |
| PROV-004 | Idempotency keys depend only on tenant, step, Blueprint revision and `syncVersion`, never on attempt numbers |
| PROV-005 | Identifiers and secret paths are pure functions of the never-reused `tenantId`; cancelled/deprovisioned slugs are permanently tombstoned (`PROV-T34`) |
| PROV-006 | Secrets are created put-if-absent via `SecretStore` with `{workflowId, state}` metadata and an active owning workflow; `pending_destruction` or foreign `workflowId` blocks adoption (`PROV-T31`); `scripts/provision_tenant_site.py` container argv gaps must be eliminated before production |
| PROV-007 | One worker per tenant at a time via lease & fencing token during active steps; `awaiting_approval` and multi-day waits release the lease |
| PROV-008 | Public host routing (Step 10) never activates until Steps 1–9 are `done` AND a gateway-path invisibility probe (`PLT-024`, `ERP-020`) passes (`PROV-T32`) |
| PROV-009 | The initial apply runs on behalf of the approving owner, never an agent on production |
| PROV-010 | Cancellation compensates only before `register_route`; after `ready` there is no automatic rollback |
| PROV-011 | Deprovisioning halts agents/triggers/connectors/e-invoices in Step 1 (`close_access`), purges all non-engine AI/search/cache stores in Step 5, and executes an atomic DB legal-hold lock (`SELECT ... FOR UPDATE` + fencing token) immediately before every destructive external call (`PROV-T37`, `PROV-T38`) |
| PROV-012 | Secrets and e-invoice keys are destroyed, never exported; `crypto_shred` destroys `S10b` tenant/backup DEKs only, never `S10a` regional KEK |
| PROV-013 | Every transition is audited; no secret in any audit record, event or error; `DAT-007` tombstone evidence retained per statutory schedule |
| PROV-014 | Customer-visible messages from provisioning use i18n and name neither the engine nor internal identifiers |
| PROV-015 | Deleting a live (non-trial) tenant requires recorded tenant-owner deletion request plus second staff approval |

## 8. Tests
| ID | Case | Expected |
|---|---|---|
| PROV-T01 | Run the full workflow twice for the same request | One site, one set of secrets; second run all `done` without acting |
| PROV-T02 | Kill the worker after each step's act, before its record; resume | Exactly one of each resource; workflow completes |
| PROV-T03 | Kill after `create_secrets` act (same `workflowId`, `state: active`) | Secrets adopted, not regenerated (same version ids) |
| PROV-T04 | Same tenant, different request hash | `conflict`; nothing created |
| PROV-T05 | Two workers race for one tenant | One holds the lease; the other's writes refused by fencing |
| PROV-T06 | Stale worker resumes after lease expiry | Its writes refused |
| PROV-T07 | `provision_site` returns `site_exists_different_target` | `blocked`; no second site |
| PROV-T08 | `provision_site` deadline passes | Retry with the same key; one site |
| PROV-T09 | Secret store down at step 2 | Retries then `blocked`; no site created |
| PROV-T10 | Hardening verification fails | `blocked`; no route |
| PROV-T11 | Customer request tries to reach the site before step 10 | No route; refused |
| PROV-T12 | Initial apply fault at step k (contract ADP-C-071) | `compensated`; workflow `blocked`; no route |
| PROV-T13 | Initial apply `recovery_required` | `blocked`; site blocked |
| PROV-T14 | Initial apply requested with an agent `onBehalfOf` on production | `permission_denied` |
| PROV-T15 | Assignment store unavailable during initial apply/sync | No wider assignment survives; apply compensates or recovery_required; Steps 8–10 incomplete |
| PROV-T16 | Drift baseline mismatch at step 9 | `blocked`; alert |
| PROV-T17 | Cancel at each step before 10 | All created resources removed or scheduled for destruction; `cancelled` |
| PROV-T18 | Cancel after `ready` | Refused |
| PROV-T19 | Resume a blocked workflow after a fix | Continues from the blocked step; earlier steps not re-acted |
| PROV-T20 | Logs, audit and events searched after a run | No secret values, no engine name in customer-visible fields |
| PROV-T21 | Production workflow with an in-memory adapter store | `verify_adapter_state` fails; `blocked` |
| PROV-T22 | Two tenants provisioned in parallel | Different identifiers, secrets and databases; tenant A's token refused at B's route |
| PROV-T23 | Deprovision with a legal hold | Stops at `waiting_grace` (`grace_wait`); Step 1 killed agents/triggers/connectors/e-invoices; nothing deleted |
| PROV-T24 | Deprovision re-run after a crash at `delete_site` (tenant DB already dropped) | Relies on control-plane state + store probes, absent DB/site counted success; continues |
| PROV-T25 | Deprovision of a trial that never went live | No export step; no dual-staff gate required; deletion after trial grace |
| PROV-T26 | After deprovision, look up secrets, site, database, shadow/agent users | None usable; destruction logged |
| PROV-T27 | Restore a backup of a deleted tenant | Refused or deletion log replayed (data-retention section 8) |
| PROV-T28 | Crypto-shred `S10b`, then read a backup (while `S10a` stays intact for live tenants) | Deleted tenant backup unreadable; live tenants unaffected |
| PROV-T29 | Slug that is reserved or a homograph of another tenant | Refused at `reserve` |
| PROV-T30 | Tenant id supplied in a customer request body | Ignored or rejected; platform id used |
| PROV-T31 | Cancel provisioning workflow (secrets enter `pending_destruction`), then re-provision same `tenantId` | Blocked / requires fresh `tenantId`; `pending_destruction` secrets never adopted (`Opus H8`) |
| PROV-T32 | Engine header/path/cookie marker leaks on internal test route before Step 10 | Step 10 gateway invisibility probe fails; public host never bound (`PROV-008`, `Opus H3`) |
| PROV-T33 | Crash inside Step 3 (`create_site`) after MariaDB DB and `sites/<tenant>` created, before `adapter_sites` or app install completes | Retry detects DB/filesystem residue, validates target, runs `init_adapter_state`, finishes site cleanly (`Hydrogen Blocker 2`) |
| PROV-T34 | Two concurrent signups claim the same canonical slug; OR third party claims slug immediately after `cancel`/`deprovision` | DB unique index allows one concurrent winner; cancelled/deprovisioned slug permanently tombstoned (`Hydrogen High 5`, `Opus M9`) |
| PROV-T35 | Unverified signup or signup payload attempting to choose `countryPack`, `region`, or unapproved `blueprintRevision` | Rejected unless verified identity & rate-limit pass; pack/region/Blueprint derived strictly from platform state (`Opus M10`) |
| PROV-T36 | `cancel` invoked mid-`create_secrets` and mid-`create_site` (DB partially/fully created, no route) | No orphaned secret in `active` state, no surviving DB/site directory, slug permanently tombstoned |
| PROV-T37 | Legal hold inserted concurrently while deprovisioning transitions into `delete_site` or `crypto_shred` (plus live delete attempted without dual approval) | If hold serializes before dispatch, zero deletion; if a call already dispatched, record/reconcile its outcome and dispatch nothing further; stale fences refused; live delete without owner + 2nd staff approval rejected (`PROV-011`, `PROV-015`) |
| PROV-T38 | Deprovision `delete_site` + `verify_and_certify` leaving an AI gateway log, chat transcript, embedding, memory entry, search index, cache key, or brand asset | Caught by Step 8 store probes (zero tenant DB dependency); certificate refused until all stores empty (`Hydrogen High 4`) |
| PROV-T40 | Close access with scheduled/queued/in-flight agents, connector jobs and submissions | Kill flag durable, agent engine users disabled, triggers dropped, jobs paused, no further dispatch before close_access completes |
| PROV-T41 | Live delete requested without owner request, without independent staff approval, or with stale action hash | Refused before offboarding; approvals bind tenant, exact action and revision with expiry |
| PROV-T42 | Signup exceeds rate limit; region/Blueprint chosen in body; automatic plan lacks team_reviewed before build/live | Refused; only verified identity and reviewed platform state accepted |
| PROV-T39 | `apply_initial_blueprint` returns `needs_gate_approval` and pauses >900s (`planToken` expires); AND the full membership sync inside Step 7 fails before apply success | Parks in `awaiting_approval` (lease released), re-`plan`s cleanly on resume with zero retry penalty; sync failure prevents Step 7 from reporting applied, compensates or enters recovery_required, and keeps Steps 8–10 incomplete (`Hydrogen High 3`) |

## 9. Decisions needed
1. **D-1** *(Resolved by `c51ebc8`, `#147`)* Provisioning code lives in `services/provisioning/` (`partner` lane in `scripts/lanes.json`), with control-plane DB schema coordination against Eldon's `services/control-plane/`.
2. **D-2** Whether a sandbox (simulation) site is provisioned by the same workflow with `siteClass: sandbox`, and whether it is deleted after go-live.
3. **D-3** Who may press resume and cancel on a blocked workflow while only two founders exist.

Secret metadata may be `reserved` (no value yet), `active`, or `pending_destruction`. Only the owning active workflow can finish its reservation. Read/use adoption is limited to active secrets of that same active workflow; pending destruction always blocks. Store operations and cancellation serialize on the workflow fence.

## 10. Open questions
1. Ephemeral `provisioning-site-init` custody vs extending `contracts/engine-adapter/site.schema.json` with `SecretStore` paths (`site.schema.json` currently has `additionalProperties: false`). Both require eliminating `scripts/provision_tenant_site.py` container password argv flags before production.
2. Placement policy at volume (ERP-002, INF-010).
