# Tenant provisioning

Status: draft
Owner: partner
Approved by: pending (with [ADR-0040](../decisions/ADR-0040-tenant-provisioning-service.md))

Plan ID: PLT-003. Detail for ADR-0040. Nothing here is built. Internal documentation; it may name the engine (ADR-0016). Depends on ADR-0038 (secrets), ADR-0039 (role mapping) and ADR-0041 (durable adapter state), all in open PRs at the time of writing.

## 1. Workflow record (control-plane database, tenant's region)
| Field | Rule |
|---|---|
| `workflowId` | ULID |
| `tenantId` | Platform-generated; unique per active provisioning workflow |
| `kind` | `provision` or `deprovision` |
| `requestHash` | sha256 of the canonical request; a second request for the same tenant with another hash is `conflict` |
| `request` | region, country pack, engine version set, site class (sandbox or production), Blueprint id and approved revision, owner membership ref |
| `placement` | bench pool and database server, written once in `reserve` |
| `secretIds` | ids and versions from `SecretStore`, never values |
| `steps[]` | `{name, state, attempts, lastErrorCode, startedAt, finishedAt, idempotencyKey, evidenceRef}` |
| `state` | `running`, `blocked`, `cancelling`, `cancelled`, `done` |
| `lease` | worker id, expiry, fencing token (monotonic) |

## 2. Provisioning steps
| # | Step | Observe first | Act | Post-condition | Idempotency |
|---|---|---|---|---|---|
| 1 | `reserve` | Record has placement? | Choose pool and server by capacity in the region; reserve the slug (reserved-word and homograph checks, T51) | Placement and slug persisted | Placement never re-chosen |
| 2 | `create_secrets` | Metadata exists at each fixed path? | Put-if-absent: database credential (S05), Administrator password (S08), impersonation credential (S09), data key (S10) | All four exist; ids recorded | Fixed paths from tenant id (SEC2-043) |
| 3 | `create_site` | Adapter `site_status` | `provision_site` with key `prov:{tenantId}`; secrets passed through the store reference, never argv (ERP-003 mechanics) | `ready`, same target | Contract 5.2; `site_exists_different_target` blocks |
| 4 | `harden_site` | Read the settings | Customer login off, engine email off, developer mode off, Administrator login off | Settings verified; invisibility probe (no engine markers on the routed host is QA-016 later) | Setting writes are absolute values |
| 5 | `init_adapter_state` | Store present? | Create the ADR-0041 store in the tenant database | Store reachable; in-memory store refused in production | Create-if-absent |
| 6 | `verify_site` | n/a | `health`, `capabilities`, installed app list | All pass | Read-only |
| 7 | `apply_initial_blueprint` | `site_status.applied` equals target revision? | `plan`, then gate approval if `gated`, then `apply` with key `apply:{tenantId}:{revision}` and `onBehalfOf` the approving owner | Outcome `applied` or `already_applied`; export hash recorded | Contract 5.6 and section 7 |
| 8 | `sync_members` | Last applied `syncVersion` | `sync_members` full mode, version 1 (or next), owner and invited members with roles from the assignment store | Counts match; ADR-0039 RM checks | Contract 5.9 (`stale_sync_version` on replay with another key) |
| 9 | `baseline_permissions` | Baseline stored? | Compute the expected and actual drift fingerprint (ADR-0039 section 4) | They match; baseline stored | Pure function |
| 10 | `register_route` | Route exists and points to this site? | Add route host to site in the gateway (PLT-024) | Route resolves; a token for another tenant is refused | Upsert of an absolute value |
| 11 | `ready` | Lifecycle state | Hand over to PLT-004 (`trial` or `active`); emit `tenant.state_changed` | State recorded | Same state is a no-op |

E-invoice unit onboarding (CMP-007) is not a provisioning step. It needs an owner's OTP and runs later, on demand.

## 3. State machine
- Step: `pending` to `running` to `done`; `running` to `failed_retryable` to `running` (backoff); `failed_retryable` to `blocked` after 5 attempts in one run; any state to `blocked` on a non-retryable error.
- Workflow: `running` while steps advance; `blocked` when a step blocks; a human `resume` sets the blocked step to `pending`; a human `cancel` sets `cancelling`, then compensation (section 4), then `cancelled`; all steps `done` sets `done`.
- Lease: a worker takes the lease with a new fencing token. Every write carries the token, and a lower token is refused. An expired lease can be taken by another worker, which re-observes the current step.

## 4. Failure matrix
| Failure | Handling |
|---|---|
| Crash after a secret is created, before it is recorded | Re-run finds the secret at its fixed path and adopts it (SEC2-T30) |
| Crash after the site is created, before it is recorded | `site_status` shows it with the same target; adopted |
| Site exists with a different target | `blocked`; human decides |
| `provision_site` deadline passes | Retry with the same key returns `in_progress` or the final status (contract section 7) |
| Hardening setting fails to verify | Retry; then `blocked`. The route is never registered without it |
| Initial apply `rejected` or `compensated` | `blocked` with the outcome; resume needs a new approved revision (new key) |
| Initial apply `recovery_required` | `blocked`; adapter site is blocked too; human repair |
| Assignment store unavailable during sync | Retry; deny by default (no member gets a role) |
| Drift baseline mismatch | `blocked`; it is a security signal, not retried blindly |
| Secret store unavailable | Fail closed; retry; then `blocked` (SEC2-037) |
| Region capacity exhausted | `blocked` before any resource is created |
| Cancel before `register_route` | Compensate in reverse: route removed, empty site and database deleted, secrets scheduled for destruction, `cancelled` |
| Cancel after `ready` | Not allowed; use deprovisioning |

## 5. Deprovisioning steps
| # | Step | Gate | Idempotent because |
|---|---|---|---|
| 1 | `close_access` | Lifecycle says suspend or delete | Route removal and session-version bump are absolute |
| 2 | `final_export` | Not for trials that never went live (data-retention section 7) | Export manifest hash recorded; re-run reuses it |
| 3 | `grace_wait` | data-retention D-1; legal hold stops here and at every later step | Timer from a recorded start |
| 4 | `disable_principals` | No hold | Disable is absolute |
| 5 | `delete_site` | No hold | Absent site is success |
| 6 | `destroy_secrets` | No hold; recovery window (data-retention D-5, SEC-002 D-3) | Already destroyed is success |
| 7 | `crypto_shred` | After the recovery window | Destroyed key is success |
| 8 | `verify_and_certify` | All above `done` | Verification re-reads every store; certificate issued once (DAT-007) |

## 6. Audit
Every step transition writes an internal audit record: `auditId`, workflow id, tenant, actor (service or staff id), step, input hash, outcome, error code, timings, fencing token. It never contains a secret or a hostname in customer-visible output. Events: `tenant.state_changed` on lifecycle hand-over and in deprovisioning; `data.exported` and `data.deleted` from the export and deletion rows; `engine.site_provisioned` only once the events contract adds it.

## 7. Requirements
| ID | Requirement |
|---|---|
| PROV-001 | Only control-plane staff tooling and the signup flow can start a workflow; the tenant id is platform-generated |
| PROV-002 | Workflow state is durable in the control-plane database in the tenant's region before the first external action |
| PROV-003 | Every step observes before acting and verifies after |
| PROV-004 | Idempotency keys depend only on tenant, step, Blueprint revision and sync version, never on an attempt number |
| PROV-005 | Identifiers and secret paths are pure functions of the tenant id |
| PROV-006 | Secrets are created put-if-absent through `SecretStore`; no value is stored in the workflow record or logs |
| PROV-007 | One worker per tenant at a time, enforced by lease and fencing token |
| PROV-008 | No route exists until steps 1 to 9 are `done` |
| PROV-009 | The initial apply runs on behalf of the approving owner, never an agent |
| PROV-010 | Cancellation compensates only before `register_route`; after `ready` there is no automatic rollback |
| PROV-011 | Deprovisioning never deletes while a legal hold exists |
| PROV-012 | Secrets and e-invoice keys are destroyed, never exported |
| PROV-013 | Every transition is audited; no secret in any audit record, event or error |
| PROV-014 | Customer-visible messages from provisioning use i18n and name neither the engine nor internal identifiers |

## 8. Tests
| ID | Case | Expected |
|---|---|---|
| PROV-T01 | Run the full workflow twice for the same request | One site, one set of secrets; second run all `done` without acting |
| PROV-T02 | Kill the worker after each step's act, before its record; resume | Exactly one of each resource; workflow completes |
| PROV-T03 | Kill after `create_secrets` act | Secrets adopted, not regenerated (same version ids) |
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
| PROV-T15 | Assignment store unavailable at step 8 | No member has a role; retry then `blocked` |
| PROV-T16 | Drift baseline mismatch at step 9 | `blocked`; alert |
| PROV-T17 | Cancel at each step before 10 | All created resources removed or scheduled for destruction; `cancelled` |
| PROV-T18 | Cancel after `ready` | Refused |
| PROV-T19 | Resume a blocked workflow after a fix | Continues from the blocked step; earlier steps not re-acted |
| PROV-T20 | Logs, audit and events searched after a run | No secret values, no engine name in customer-visible fields |
| PROV-T21 | Production workflow with an in-memory adapter store | `init_adapter_state` fails; `blocked` |
| PROV-T22 | Two tenants provisioned in parallel | Different identifiers, secrets and databases; tenant A's token refused at B's route |
| PROV-T23 | Deprovision with a legal hold | Stops at `grace_wait`; nothing deleted |
| PROV-T24 | Deprovision re-run after a crash at `delete_site` | Absent site counted as success; continues |
| PROV-T25 | Deprovision of a trial that never went live | No export step; deletion after the trial grace |
| PROV-T26 | After deprovision, look up secrets, site, database, shadow users | None usable; destruction logged |
| PROV-T27 | Restore a backup of a deleted tenant | Refused or deletion log replayed (data-retention section 8) |
| PROV-T28 | Crypto-shred, then read a backup | Unreadable |
| PROV-T29 | Slug that is reserved or a homograph of another tenant | Refused at `reserve` |
| PROV-T30 | Tenant id supplied in a customer request body | Ignored or rejected; platform id used |

## 9. Decisions needed
1. **D-1** Where the service code lives. `services/control-plane/` is in Eldon's lane (scripts/lanes.json) while PLT-003 is the partner's. Options: a partner-owned `services/provisioning/` (lane change), or move PLT-003 to Eldon.
2. **D-2** Whether a sandbox (simulation) site is provisioned by the same workflow with `siteClass: sandbox`, and whether it is deleted after go-live.
3. **D-3** Who may press resume and cancel on a blocked workflow while only two founders exist.

## 10. Open questions
1. How the adapter keeps `provision_site` idempotency before the tenant database exists (ADR-0041 to answer). This design is safe either way because identifiers are deterministic and `site_status` is observed first.
2. Placement policy at volume (ERP-002, INF-010).
