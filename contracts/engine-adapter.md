# Engine adapter

Version: 0.1.0
Status: draft
Owner: eldon
Plan IDs: BPL-025 (this contract, fake, conformance suite), BPL-026 (compiled artifact), BPL-012 and ERP-012 (real adapter), BPL-007 (apply), BPL-027 (integration)

The neutral interface the platform uses to change and inspect a tenant's engine configuration. Today the seed engine (ADR-0002) sits behind it; any engine that passes section 14 can replace it. The input of every changing operation is a compiled artifact ([compiled-artifact.schema.json](compiled-artifact.schema.json)). Background: [engine-adapter architecture](../docs/architecture/engine-adapter.md), [change engine](../docs/architecture/change-engine.md), ADR-0006, ADR-0007, ADR-0013, ADR-0016.

## 1. Scope
In scope (configuration path): `capabilities`, `provision_site`, `site_status`, `plan`, `preview`, `apply`, `rollback`, `export_config`, `sync_members`, `health`.
Out of scope for 0.1.0 (stay in the architecture doc until a later contract): `execute` and `query` (Tool API runtime), `subscribe` (record events), `snapshot`/`restore`, `upgrade`/`downgrade`, `delete_site`. Branding (compiled to tenant tokens by the platform) and integrations (connectors) never reach the adapter.

## 2. Files
| File | Content |
|---|---|
| `engine-adapter.md` | This document: semantics, rules, conformance |
| `engine-adapter/common.schema.json` | Request envelope, platform context, response envelope, site status, shared types |
| `engine-adapter/error.schema.json` | Error object |
| `engine-adapter/{capabilities,site,plan,preview,apply,rollback,export-config,sync-members,health}.schema.json` | One file per operation, `$defs.request` and `$defs.response` (site: `provisionRequest`, `statusRequest`) |
| `compiled-artifact.schema.json` | Contract for the artifact (BPL-026) |
| `examples/compiled-artifact-*.json` | Samples: add a field, add a workflow state, remove a field (destructive) |

All schemas are JSON Schema draft 2020-12 with `urn:platform:contract:*` ids. Cross-file `$ref`s use those ids; validators load all files into one registry.

## 3. Principles
1. **Neutral.** Inputs and outputs speak Blueprint terms (entity, field, workflow, role). No engine type, object, table, column, module or product name crosses this interface.
2. **Tenant from context only.** The tenant is `context.tenantId`, stamped by the internal gateway. No `input` schema has a tenant, user or role field; the artifact carries none.
3. **Fail closed.** Unknown version, unknown step kind, integrity failure, lookup error, missing approval: refuse, change nothing, record an audit id.
4. **Deterministic.** Same site state + same request gives the same plan, preview and export bytes.
5. **No data loss.** Removal is quarantine (hidden, not required, data kept). No operation drops stored data in 0.1.0.
6. **Atomic per artifact.** Every step and post-condition succeeds, or the site ends on the base revision, or the site is marked `recovery_required` and blocked (5.6).

## 4. Call model
### 4.1 Envelope
Request: `{"context": {...}, "input": {...}}`. Response: `{"ok": true, "result": {...}, "auditId": "aud_...", "replayed": false}` or `{"ok": false, "error": {...}, "auditId": "aud_..."}`. Transport is not fixed (internal HTTP or RPC on the private network); the JSON shapes are.

`context` (common.schema.json): `contractVersion`, `requestId` (ULID), `correlationId`, `tenantId`, `caller.service`, `caller.onBehalfOf` (`kind` user, agent, support or system; `id`; `roleIds`; `supportGrantId` when support), `deadlineMs`.

### 4.2 Authorisation
The adapter authenticates the calling **service** (mutual TLS or signed service token; mechanism is an open question, 16.3) and checks it against this table. `onBehalfOf.roleIds` are resolved by the gateway from the tenant's assignment store (ADR-0007 item 9) and are recorded for audit only; configuration operations never authorise on them and never accept roles from `input`.

| Operation | Allowed `caller.service` | `onBehalfOf` rule |
|---|---|---|
| `capabilities` | any listed service | any |
| `health` | control_plane, observability, operate_gateway | any |
| `site_status`, `export_config`, `plan`, `preview` | control_plane, compiler, simulator | any |
| `provision_site` | control_plane | system or user |
| `apply`, `rollback` | control_plane | production site: user, or support with `supportGrantId`; never agent, never null. Sandbox site: also system or agent |
| `sync_members` | control_plane, identity | system or user |

A refused call returns `permission_denied`, changes nothing and emits `permission.denied`.

### 4.3 Version negotiation
- `context.contractVersion` must match a value in `capabilities().contractVersions` on major and minor while the major is 0 (minor bumps may break, contracts README rule 1); patch may differ. Else `unsupported_contract_version` with `details.supported`.
- `artifact.artifactSchema` must be in `artifactSchemaVersions`. Else `unsupported_contract_version`.
- `artifact.engineTarget.adapter` must equal `adapterId`; `versionSet` must be in `versionSets` and equal the site's version set. Else `unsupported_engine_target`.
- A step kind the adapter lists as `unsupported` (or does not list) makes `plan` reject; `apply` returns `unsupported_step_kind`.

## 5. Operations
| Operation | Input (beyond context) | Result | Side effects | Idempotent |
|---|---|---|---|---|
| `capabilities()` | none | adapter id and version, contract and artifact versions, version sets, step kinds with support level, limits, exported properties, features | none | yes (pure) |
| `provision_site` | `idempotencyKey`, `engineTarget`, `countryPack`, `siteClass`, `blueprintId` | site status | creates one empty site | yes (key, and same params) |
| `site_status()` | none | site status | none | yes (pure) |
| `plan` | `artifact` | `planToken`, `siteConfigHash`, `verdict`, per-step disposition, storage counts, `evidenceRef` | audit record only | yes (pure on state) |
| `preview` | `artifact`, `includeExport` | `verdict`, `predictedExportHash`, optional `predictedExport`, `delta` | audit record only | yes (pure on state) |
| `apply` | `idempotencyKey`, `artifact`, `planToken`, `approvals` | outcome (5.6) | changes configuration | yes (key + artifact) |
| `rollback` | `idempotencyKey`, `forwardArtifact`, `reason`, `approvals` | outcome, `operation: rollback` | applies the stored inverse | yes (key) |
| `export_config()` | none | `exportHash`, `export`, `retained` | none | yes (pure) |
| `sync_members` | `idempotencyKey`, `mode`, `syncVersion`, `members` | counts | creates, updates, disables shadow users | yes (key, syncVersion) |
| `health()` | none | status, checks | none | yes |

### 5.1 capabilities
Lists every kind of the artifact `stepKind` enum, sorted, with `supported`, `gated` (plan always asks for gate approval) or `unsupported`. `exportedProperties` names, per subject kind, the Blueprint properties the adapter persists and exports; the fake and the real adapter declare the same lists for one contract version (16.6). Test-only fault hooks (15.1) are never listed and never present in production builds.

### 5.2 provision_site and site_status
`provision_site` creates one isolated site for the context tenant (ADR-0006) on the requested version set, with the country pack, bound to one `blueprintId`. Same key: stored result, `replayed: true`. New key, same parameters, site exists: current status, no second site. Different `engineTarget` or `blueprintId`: `site_exists_different_target`. Site states: `absent`, `provisioning`, `ready`, `applying`, `recovery_required`, `failed`. `applied` is the last artifact applied or rolled back to, with the revision the site matches. No hostnames, database names or engine identifiers are returned. Tenant lifecycle (trial, active, suspended) is the control plane's, not the adapter's.

### 5.3 plan
Checks, in order: schema, integrity (8.3), versions (4.3), `blueprint.id` equals the site's (`blueprint_mismatch`), `blueprint.base` equals `site.applied.revision` (both null for an initial build; else `base_revision_mismatch`), site not `recovery_required`. Then evaluates each step against the live site and the adapter's guardrails and gives a disposition:

| Disposition | Meaning |
|---|---|
| `ok` | Can run with no human gate |
| `already_applied` | Target state already present for this step (only after a compensated or interrupted run) |
| `gated` | Can run only with a recorded gate approval |
| `blocked` | Cannot run (guardrail, conflict) |
| `unsupported` | Kind not supported by this adapter |

Verdict: `rejected` if any step is blocked or unsupported; else `needs_gate_approval` if any is gated; else `auto_approved`.

Gate rules (aligned with the existing DDL plan gate): a step with `ddlImpact` other than `none` is `ok` only if the adapter proves it is one additive, nullable, non-unique, unindexed storage addition of a supported value type; any other storage change is `gated` (`storage_not_additive`, `multi_statement`, `unique_or_index`) or `blocked`. `semantic` steps are always at least gated. The adapter's `ddlImpact` per step is never lower than the artifact's. Raw storage statements are kept internally under `evidenceRef` for reviewers with engine access and are never returned.

`planToken` binds tenant, artifact `contentHash`, `siteConfigHash` (export hash at plan time) and adapter version, and expires after `planTokenTtlSeconds`.

### 5.4 Plan reason codes
`protected_subject` (guardrail: ledger, tax, audit, security or identity objects), `unsupported_step_kind`, `unsupported_value_type`, `storage_not_additive`, `multi_statement`, `unique_or_index`, `subject_exists`, `subject_missing`, `subject_in_use` (for example a role still assigned), `state_in_use` (records sit in a workflow state being removed), `definition_conflict` (restore of a quarantined element with a different definition), `recovery_required`, `limit_exceeded`.

### 5.5 preview
Same checks as `plan`. Returns the export the site would have after a successful apply (`predictedExportHash`, `predictedExport` when asked) and a `delta` of neutral changes (`add`, `replace`, `remove`, `reorder`, `quarantine`, `restore`, `disable`, `enable`) sorted by pointer. Built for the owner-facing explanation: everything in it is neutral. No side effects. When `features.previewPredictsExport` is true (required of the fake; the real adapter states it), the hash must equal the `exportHash` after apply.

### 5.6 apply
Six audited stages, in this order (names map to the existing change engine, section 13):

| Stage | Does | Failure gives |
|---|---|---|
| `acquire` | Take the site lock (one apply or rollback per site); bind `idempotencyKey` to the canonical input hash | `concurrent_change` (retryable), `idempotency_conflict`, or the stored outcome on replay |
| `inspect` | Re-run every plan check; verify `planToken` (same artifact, same tenant, not expired, current export hash equals `siteConfigHash`); check `approvals` | `plan_token_invalid`, `plan_rejected`, `approval_missing`, `base_revision_mismatch`, `recovery_required` |
| `prepare` | Persist the durable intent (operation id, artifact hash, plan evidence, approvals) and its audit record before any change | `failed_clean` |
| `execute` | Run steps in `seq` order | go to `compensate` |
| `reconcile` | Read back the configuration, verify every post-condition | go to `compensate` with `postcondition_failed` |
| `finalize` | Persist the outcome, update `site.applied`, emit events, release the lock | `recovery_required` if the outcome cannot be persisted |
| `compensate` | Only on failure after `execute` began: undo executed steps in reverse order with the matching steps of the stored inverse (same pointer) | `recovery_required` if any compensation fails |

Approvals: `changeApproved` always; `gateApproved` when the verdict is `needs_gate_approval`; `teamReviewed` when `risk.requiresTeamReview`. The adapter checks presence and format and records them; their truth is the control plane's (15.3).

Outcome `status`:
| Status | Meaning | Site after |
|---|---|---|
| `in_progress` | Returned to a retry with the same key while running | locked |
| `applied` | All steps and post-conditions passed | target revision |
| `already_applied` | Site already holds this artifact (different key) | unchanged |
| `rejected` | Refused in `acquire` or `inspect`; nothing changed | base revision |
| `failed_clean` | Failed in `prepare`; nothing changed | base revision |
| `compensated` | Failed during `execute` or `reconcile`; executed steps undone | base revision, active export identical to before |
| `recovery_required` | Partial state could not be undone or the outcome could not be persisted | blocked for apply and rollback until a human resolves it |

Atomicity is compensation, not one database transaction: storage changes commit implicitly in the seed engine (UNVERIFIED for any other engine), so the adapter must journal each executed step in the `prepare` record and its own audit store. `compensated` means the active export hash equals the pre-apply hash; quarantined leftovers from compensated additions appear only in `retained`.

Restore rule: an add step (`*.add`, `*.upsert`, `*.enable`) whose subject is quarantined or disabled with an identical definition restores it with its data; with a different definition the step is `blocked` (`definition_conflict`).

### 5.7 rollback
Input is the **forward** artifact; the adapter uses its embedded `inverse`. Checks: integrity of both; `forwardArtifact.artifactId` equals `site.applied.artifactId` (else `rollback_not_possible`, `reasonCode` `not_latest`); `inverse` not null (`no_inverse`); `risk.irreversibleSteps` is 0 (`irreversible_step`). Then it runs `plan` and the six stages of `apply` on the inverse internally. A rollback whose inverse plan needs the gate requires `approvals.gateApproved`. Destructive inverse steps are quarantine (build-states rollback rule 3). Ledger-affecting records are never rolled back (build-states rule 6); the adapter refuses inverse steps on protected subjects like any other step. Rolling back an initial build is not an adapter operation: the sandbox is destroyed (build-states rule 1).

### 5.8 export_config
Returns the active configuration in Blueprint shape (`export`), its `exportHash`, and `retained` (quarantined or disabled elements, by pointer, not hashed). Rules:
- Canonical JSON as bpdiff: sorted keys, separators `,` and `:`, UTF-8, no ASCII escaping, no NaN. `exportHash` = `sha256:` + hex of those bytes of `export`.
- Elements hold only `capabilities().exportedProperties` for their kind. No timestamps, engine-generated ids, record counts, secrets, hostnames or user data.
- Arrays of elements sorted by `id`, except order-significant collections, which keep Blueprint order: entity fields, select options, workflow states, approval steps, report metrics (bpdiff `orderSignificant`).
- Two sites holding the same configuration produce identical bytes. Apply then rollback gives the pre-apply bytes (G1 acceptance, spec 02).

### 5.9 sync_members
Reconciles shadow engine users with the tenant's memberships (ADR-0007 items 4, 9, 11, 13). `memberRef` is an opaque per-tenant id, never an email, phone or global person id. `full` mode disables every shadow user not listed; `delta` touches only listed members. `syncVersion` is monotonic per tenant; a version not above the last applied gives `stale_sync_version` (a replay with the same key returns the stored result). Every `roleId` must be an active role in the applied configuration, else `unknown_role` and nothing changes (all or nothing per call). Shadow users have no password, API key or email delivery and cannot sign in; the schema has no field for any of these. Removing a member disables, never deletes, the shadow user (tenant records keep the display name for audit). Called on every assignment change and after every apply that changes roles (ADR-0007 item 9).

### 5.10 health
With a tenant context: that site's checks. With `tenantId: "platform"`: adapter and shared-pool checks. No tenant data.

## 6. Errors
Error object: error.schema.json. `code` is stable; `messageKey` is `errors.adapter.<code>`; there is no free-text message. `details` may hold only `stepSeq`, `pointer`, `postConditionId`, `reasonCode`, `fields`, `limit`, `allowed`, `actual`, `supported`. Engine messages, object names, SQL, file paths and stack traces go to the adapter's internal log under the same `auditId`, never into a response.

| Code | When | Retryable |
|---|---|---|
| `invalid_request` | Schema failure of context or input, unknown key | no |
| `unsupported_contract_version` | 4.3 | no |
| `unsupported_engine_target` | 4.3 | no |
| `unsupported_step_kind` | apply with a kind the adapter does not support | no |
| `permission_denied` | 4.2 | no |
| `approval_missing` | a required approval reference absent | no |
| `tenant_not_found` | no site record for the context tenant | no |
| `site_not_ready` | site absent, provisioning or failed | yes, later |
| `site_exists_different_target` | provision with other parameters | no |
| `artifact_integrity_failed` | hash or id mismatch, signature failure (when enabled) | no |
| `artifact_not_found` | rollback with an artifact the site never applied | no |
| `blueprint_mismatch` | artifact Blueprint id differs from the site's | no |
| `base_revision_mismatch` | site not on the artifact's base revision | no (recompile) |
| `plan_rejected` | verdict rejected | no |
| `plan_token_invalid` | missing, foreign, expired or stale token | yes, after a new plan |
| `concurrent_change` | site lock held | yes, `retryAfterMs` |
| `idempotency_conflict` | key reused with other input | no |
| `recovery_required` | site blocked by an unresolved partial change | no |
| `postcondition_failed` | a post-condition failed (in outcome, status compensated) | no |
| `rollback_not_possible` | 5.7 | no |
| `stale_sync_version` | 5.9 | no |
| `unknown_role` | 5.9 | no |
| `limit_exceeded` | section 11 | no |
| `timeout` | deadline passed before a result; retry with the same key | yes |
| `engine_unavailable` | engine down or overloaded | yes |
| `internal_error` | adapter bug | maybe |

Errors before `acquire` (validation, authorisation, versions, integrity, limits) use the `ok: false` envelope. Once an operation record exists, `apply` and `rollback` return `ok: true` with an outcome whose `error` explains a non-success status.

## 7. Idempotency, timeouts, retries
- Keys are scoped `(tenant, operation, key)` and bound to the sha256 of the canonical `input`. Same key, same input: stored result, `replayed: true`, no new effect, no new event. Same key, other input: `idempotency_conflict`. Retention at least 30 days (`idempotencyRetentionSeconds`).
- `plan`, `preview`, `export_config`, `site_status`, `capabilities`, `health` are read-only and need no key.
- Default deadlines (UNVERIFIED until the 50-tenant spike, ERP-002): capabilities, health, site_status 5 s; export_config, sync_members 60 s; plan, preview 60 s; apply, rollback 600 s; provision_site 1800 s. Callers pass the budget in `deadlineMs`.
- When the deadline passes mid-operation the adapter finishes or compensates the current artifact; it never stops between steps leaving a partial state. The caller retries with the same key and receives `in_progress` or the final outcome; the operation never runs twice.
- Retry only on `retryable: true`, exponential backoff from 1 s, at most 5 attempts, honouring `retryAfterMs`.

## 8. Audit and events
### 8.1 Audit
Every call, success or failure, writes an internal audit record with `auditId`, `requestId`, `correlationId`, tenant, caller service, `onBehalfOf`, operation, input hash, artifact id, outcome or error code, stage timings. Plan evidence and engine diagnostics are stored under the same id, internal only.

### 8.2 Events (contract 4 names only)
The adapter is the only producer of these; the control plane must not emit them again. It hands them to the platform producer, which stamps `tenant_id`, `sequence` and `actor` (events.md section 1 rules). `data` follows `blueprint_event` in the event registry.

| Trigger | Type | `data` |
|---|---|---|
| apply ends `applied` | `blueprint.applied` | `change_id` = artifactId, `revision` = target revision |
| apply ends `rejected`, `failed_clean`, `compensated` or `recovery_required` | `blueprint.apply_failed` | `change_id`, `revision` = target revision, `error_code` |
| rollback ends `applied` | `blueprint.rolled_back` | `change_id` = forward artifactId, `revision` = base revision |
| rollback fails | `blueprint.apply_failed` | `change_id` = inverse artifactId, `error_code` |
| any call refused by 4.2 | `permission.denied` | per registry |

`already_applied`, replays, plan, preview, export, status, capabilities and health emit no event. Role assignment events (`role.assigned`, `role.revoked`) belong to the membership store, not to `sync_members`.

## 9. Compiled artifact rules (BPL-026)
### 9.1 Identity and integrity
`integrity.contentHash` = sha256 of the canonical JSON (5.8 rules) of the artifact without `artifactId` and `integrity`; the embedded inverse is hashed as it stands. `artifactId` = `art_` + the first 32 hex characters. `integrity.signature` is null in 0.1.0; it is the extension point for ed25519 signing of `contentHash` by the compiler (needs an ADR, key custody open, 16.8). Adapters verify the hash on every call that takes an artifact.

### 9.2 Hashes from the Blueprint diff
`blueprint.base.hash` and `blueprint.target.hash` are bpdiff `blueprint_hash()` values (sha256 of the canonical whole revision). `diffHash` is the sha256 of the canonical bpdiff diff object (forward) or of `invert(diff)` (inverse). `risk.counts`, `total`, `maxImpact`, `touchesCompliance`, `touchesAccess` are copied from the diff's `risk`; `needsDdlPlanGate` is the diff value or any step with `ddlImpact` other than `none`.

### 9.3 From diff ops to steps
Every diff op appears exactly once: in one step's `sourceOps` or in `skippedOps`. Coalescing: ops under a workflow (states, transitions, guards) become one `workflow.upsert` with the whole target workflow; under a role (permissions, scope) one `role.upsert`; under an approval (steps, conditions) one `approval.upsert`; under a report (metrics, filters) one `report.upsert`; component parameter changes become `component.configure`. `add` of an element: `*.add`, `*.upsert` or `*.enable`. `remove` of an entity, field, option or relation: `*.quarantine`; of a binding, location, component, role, workflow, approval or report: `*.disable`. `replace` inside an entity, field, relation or binding: `*.set_property` with `property`, `before`, `after`; under company, compliance or `i18n.defaultLocale`: `settings.set`. `reorder` of fields or options: `field.reorder`, `option.reorder` with the full key order. Skipped: `meta/*`, `branding`, `integrations`, `i18n.glossary`, `provenance`. A step's `impact` is the highest impact of its source ops (bpdiff order).

`params.definition` is the Blueprint node copied verbatim (target revision for add, upsert, enable; base revision for quarantine and disable, so the inverse can restore it). It is untrusted tenant data: adapters pass values as parameters and never build code, queries or templates from it (threats T24, T26, T27).

### 9.4 Ordering
Steps are sorted by phase, then pointer (Unicode code point order), then kind; `seq` is 1..n. Phases: 1 `settings.set`; 2 `component.enable`, `component.configure`; 3 `location.upsert`; 4 `entity.add`; 5 `field.add`, `relation.add`, `option.add`, `binding.add`; 6 `*.set_property`, `field.reorder`, `option.reorder`; 7 `role.upsert`; 8 `workflow.upsert`; 9 `approval.upsert`; 10 `report.upsert`; 11 `report.disable`; 12 `approval.disable`; 13 `workflow.disable`; 14 `role.disable`; 15 `binding.disable`, `option.quarantine`, `relation.quarantine`, `field.quarantine`; 16 `entity.quarantine`; 17 `location.disable`; 18 `component.disable`. Additions run before the things that use them; removals run after their users are gone. `components` sort by id, `skippedOps` by pointer, `postConditions` by id.

### 9.5 Storage impact and reversibility
`ddlImpact`: `none` (metadata only), `additive` (new nullable storage: `entity.add` always, `field.add`, `relation.add`), `semantic` (type, uniqueness, precision, length or required changes on stored values). There is no destructive value: removal is quarantine with `ddlImpact: none`. `reversible: false` marks a step whose inverse cannot restore the exact prior state (for example a precision reduction); rollback refuses artifacts with such steps and a human handles them.

### 9.6 Inverse
Compiled by the same rules from `invert(diff)` with `kind: inverse`, base and target swapped, `inverse: null`, components of the base revision, post-conditions of the base state. A forward artifact with a base must carry its inverse. An initial build (base null) has none.

### 9.7 Post-conditions
Checks against the adapter's own export after `reconcile`: `exists`, `quarantined`, `disabled`, `property_equals`, `count_equals` (active elements), `order_equals` (active keys in order). The compiler emits at least one per step subject.

### 9.8 Content rules
No secrets anywhere (schema denies secret-like keys in `params` and `definition`; the deep check is an `x-validator-rule`). No engine-specific names in steps. No tenant id. Canonical size of the whole artifact at most 1 MiB, at most 500 steps, `params` depth at most 32.

## 10. Proposed additions (not in force; need an ADR on contracts/events.md)
| Proposal | Why |
|---|---|
| Event `blueprint.gate_approved` (data: change_id, plan evidence ref) | `approvals.gateApproved` needs an event id to point at; until it exists the control plane records the gate decision as a `blueprint.change_approved` with the same `change_id` |
| Event `blueprint.apply_started` | Audit trail shows the start of a long apply, not only its end |
| Event `blueprint.recovery_required` | Distinct alert for a blocked site; today it is `blueprint.apply_failed` with `error_code` `recovery_required` |
| Event `engine.site_provisioned` (tenant-scoped) | `tenant.state_changed` is lifecycle, not provisioning |
| Event `engine.members_synced` (data: syncVersion and counts, no names) | Evidence that shadow users match memberships (ADR-0007 drift is a security bug) |
| Blueprint diff schema promoted to `contracts/` | `diffHash` and `risk` depend on a draft (services/blueprint/diff) |
| Component manifest `packageHash` | `components[].packageHash` is optional until then |

## 11. Limits
| Limit | Value |
|---|---|
| Request body, canonical bytes | 2 MiB (`maxRequestBytes`) |
| Artifact, canonical bytes (inverse included) | 1 MiB |
| Steps per artifact | 500 (an adapter may declare fewer per kind with `maxPerArtifact`) |
| Post-conditions per artifact | 1000 |
| Components per artifact | 200 |
| Members per `sync_members` call | 1000 |
| Plan token lifetime | adapter-declared; 900 s proposed |
| Concurrent apply or rollback per site | 1 |
| Idempotency retention | at least 30 days |
Exceeding one gives `limit_exceeded` with `limit`, `allowed`, `actual`; nothing changes.

## 12. Engine invisibility (ADR-0016)
- No response, error, event, export, preview or delta contains an engine name, engine object or table name, storage statement, file path, stack trace or engine-generated id. `adapterId` and `engineTarget` are internal: the gateway strips them from anything customer-facing.
- Customer-facing text is built only from neutral fields (`delta`, error `messageKey`, Blueprint labels) by our services.
- Plan evidence with storage statements is internal (`evidenceRef`), for engineers with engine access.

## 13. Mapping to the existing change engine
| Contract | Existing code (apps/engine/change_engine/change_engine) | Gap for BPL-007 and BPL-012 |
|---|---|---|
| Stages acquire, inspect, prepare, execute, reconcile, finalize | `guarded_apply/schema_reconciler.py` stages ACQUIRE, INSPECT, PREPARE, APPLY, RECONCILE, FINALIZE | Exists per single unit (one field); must run per artifact under one lock with a step journal; add `compensate` |
| Outcome statuses | APPLIED, REJECTED, FAILED_CLEAN, RECOVERY_REQUIRED, REVISION_CONFLICT (to `rejected` with `base_revision_mismatch`) | add `compensated`, `already_applied`, `in_progress` |
| Plan gate | `ddl_plan_gate.py`: approves only one additive column statement | Becomes per-step `ok`; anything else `gated` (was "queue for controlled admin deployment") |
| Guardrails | `safety_guardrails.py` (protected doctypes, fields, allowed properties, additive field subset) | Map to `protected_subject`, `unsupported_value_type`, `unique_or_index` |
| Idempotency | key + canonical payload hash, `IdempotencyConflictError` | Scope to tenant and operation; 30-day retention |
| `field.add`, `field.set_property`, `field.quarantine` | custom field deploy, property-setter engine, soft quarantine in `rollback_engine.py` | Restore rule (5.6) is new |
| `workflow.upsert`, `workflow.disable` | `workflow_engine.py` (validated state machine, baseline snapshot) | Input from Blueprint node, not the prototype format |
| `report.upsert`, `report.disable` | `report_engine.py` | Same |
| `role.upsert`, `role.disable`, `approval.*`, `entity.*`, `relation.*`, `option.*`, `binding.*`, `location.*`, `component.*`, `settings.set` | none; role and permission objects are on the guardrail locked list | Report `unsupported` in capabilities until built (ERP-008 for roles); runtime policies persist per site first (CE-SEC-003) |
| `sync_members` | none | New (ERP-008, ADR-0007) |
| `export_config`, `preview` predicted export | `schema_extractor.py` (compact schema only) | New |
Existing role-based checks inside the module (`AUTHORIZED_ROLLBACK_ROLES`, governance roles) are engine-side defence in depth; they do not replace 4.2.

## 14. Conformance
Any adapter (the fake in `services/blueprint/adapter`, the real one in `apps/engine`) must pass every item. "No effect" means: `export_config` hash, `retained`, `site_status` and the event log are unchanged. The suite uses the three sample artifacts plus fixtures it derives from them, and the harness hooks in 15.1.

Envelope, security, invisibility
- ADP-C-001 Every response of every operation validates against that operation's schema (ok or error branch).
- ADP-C-002 An `input` with any key the schema does not define (for example `tenantId`, `roleIds`, `caller`, `password`) gives `invalid_request` with `details.fields`, no effect.
- ADP-C-003 A missing or invalid `context` gives `invalid_request`, no effect.
- ADP-C-004 A `contractVersion` with another major.minor gives `unsupported_contract_version` with `details.supported`, no effect.
- ADP-C-005 Every error has `messageKey` = `errors.adapter.<code>` and only the allowed `details` keys; `retryable` matches section 6.
- ADP-C-006 No serialised response, error, event or export in the whole suite matches the denylist: `(?i)frappe|erpnext`, `Traceback`, `(?i)\b(alter|drop|create)\s+table\b`, `(?i)\bselect\s.+\bfrom\b`, `\.py\b`, `/home/`, `/var/`, plus markers the adapter's owner adds. The values of `adapterId` and `engineTarget.adapter` are excluded from the scan (internal ids, section 12).
- ADP-C-007 After any operation in tenant A, `export_config`, `retained` and `site_status` of tenant B are unchanged.
- ADP-C-008 Rollback in tenant B with an artifact applied only in A fails (`artifact_not_found`, `blueprint_mismatch` or `rollback_not_possible`), no effect.
- ADP-C-009 Any operation except `capabilities`, `health` (platform) and `provision_site` for a tenant without a site gives `tenant_not_found` or `site_not_ready`.
- ADP-C-010 Each operation called by a service not allowed in 4.2 gives `permission_denied`, no effect, and one `permission.denied` event.
- ADP-C-011 `apply` or `rollback` on a production site with `onBehalfOf` null or of kind agent gives `permission_denied`; support without `supportGrantId` gives `invalid_request`.
- ADP-C-012 Changing `onBehalfOf.roleIds` alone never changes the result of a configuration operation.

Capabilities and site
- ADP-C-013 `capabilities` lists every artifact step kind exactly once, sorted, and two calls return byte-identical results.
- ADP-C-014 `provision_site` on an absent site reaches `ready` with the requested `engineTarget`, `siteClass`, `blueprintId` and `applied: null`.
- ADP-C-015 `provision_site` replay with the same key returns `replayed: true`; a new key with the same parameters creates no second site.
- ADP-C-016 `provision_site` with another `engineTarget` or `blueprintId` for an existing site gives `site_exists_different_target`.
- ADP-C-017 `plan`, `preview`, `apply`, `export_config` on a `provisioning` or `failed` site give `site_not_ready`.

Artifact checks (plan, preview, apply, rollback)
- ADP-C-018 One byte changed in any hashed part of the artifact gives `artifact_integrity_failed`; so does an `artifactId` that does not match the hash.
- ADP-C-019 A schema-invalid artifact gives `invalid_request`.
- ADP-C-020 An unknown `artifactSchema` gives `unsupported_contract_version`.
- ADP-C-021 `engineTarget.adapter` not equal to `adapterId`, or a `versionSet` not supported or not the site's, gives `unsupported_engine_target`.
- ADP-C-022 `blueprint.id` not the site's gives `blueprint_mismatch`.
- ADP-C-023 `blueprint.base` not equal to `site.applied.revision` gives `base_revision_mismatch`.
- ADP-C-024 An artifact over a section 11 limit gives `limit_exceeded` with `limit`, `allowed`, `actual`.

Plan and preview
- ADP-C-025 `plan` and `preview` have no effect, and repeated calls return identical `verdict`, `steps`, `storage`, `siteConfigHash`, `predictedExportHash` and `delta`.
- ADP-C-026 `plan.steps` has one entry per artifact step in `seq` order; each `ddlImpact` is not lower than the artifact's.
- ADP-C-027 The verdict follows 5.3 exactly from the dispositions.
- ADP-C-028 A step kind listed `unsupported` gives disposition `unsupported` and verdict `rejected`; `gated` kinds give at least `gated`.
- ADP-C-029 A `semantic` step is never `ok`; an `additive` step is `ok` only for a single nullable, non-unique, unindexed addition.
- ADP-C-030 A step on a protected subject (adapter fixture list, at least one ledger and one identity object) is `blocked` with `protected_subject`.
- ADP-C-031 A site in `recovery_required` gives verdict `rejected` with `recovery_required`.
- ADP-C-032 With `features.previewPredictsExport` true, `exportHash` after a successful apply equals `predictedExportHash` from before it (the fake must set the feature true).
- ADP-C-033 `preview.delta` contains only neutral change kinds and pointers.

Apply
- ADP-C-034 `apply` with a missing, foreign-artifact, foreign-tenant or expired `planToken` gives `plan_token_invalid`, no effect.
- ADP-C-035 `apply` after the configuration changed since `plan` (another artifact applied) gives `plan_token_invalid`, no effect.
- ADP-C-036 `apply` for a `needs_gate_approval` plan without `gateApproved`, or with `requiresTeamReview` and no `teamReviewed`, gives `approval_missing`, no effect.
- ADP-C-037 `apply` for a `rejected` plan gives `plan_rejected` with `stepSeq` and `reasonCode`, no effect.
- ADP-C-038 Applying each sample in order (add field, remove field; add workflow state) gives `applied`, every step `applied`, every post-condition passed, `site.applied` = artifact and target revision, `exportHash` equal to a fresh `export_config`.
- ADP-C-039 Replay with the same key and input returns the stored outcome with `replayed: true`, no second effect, no second event.
- ADP-C-040 The same key with different input gives `idempotency_conflict`, no effect.
- ADP-C-041 A new key for an artifact the site already holds gives `already_applied`, no effect, no event.
- ADP-C-042 Two concurrent applies on one site: exactly one runs; the other gets `concurrent_change` with `retryAfterMs`.
- ADP-C-043 Fault at step k: steps before k are `compensated`, status `compensated`, `site.applied` unchanged, export hash equal to before, one `blueprint.apply_failed`.
- ADP-C-044 Fault in a post-condition: status `compensated`, error `postcondition_failed` with `postConditionId`.
- ADP-C-045 Fault during compensation: status `recovery_required`; site state `recovery_required`; later `apply` and `rollback` give `recovery_required`.
- ADP-C-046 Fault in `prepare`: status `failed_clean`, no effect except the audit record and one `blueprint.apply_failed`.
- ADP-C-047 Deadline expiry during `execute`: no partial state; a retry with the same key returns `in_progress` or the final outcome; steps never run twice.
- ADP-C-048 After the remove-field sample, the field is not in `export`, is in `retained` as `quarantined`, and a value written to it before is readable after restore.
- ADP-C-049 Re-adding a quarantined field with the same definition restores it with its data; with a different definition, plan gives `blocked` with `definition_conflict`.
- ADP-C-050 No operation in the suite removes stored data (fake: asserted directly; real adapter: plan evidence contains no drop statement).

Rollback
- ADP-C-051 Rollback of the latest applied artifact gives `applied` with `operation: rollback`, `site.applied.revision` = forward base, and an `exportHash` byte-identical to the one before the forward apply.
- ADP-C-052 Rollback of an artifact that is not the latest applied gives `rollback_not_possible` (`not_latest`), no effect.
- ADP-C-053 Rollback of an artifact with `inverse: null` or `irreversibleSteps` above 0 gives `rollback_not_possible`.
- ADP-C-054 A forward artifact whose embedded inverse was altered gives `artifact_integrity_failed`.
- ADP-C-055 Rollback replay and key conflict behave as ADP-C-039 and ADP-C-040.
- ADP-C-056 A successful rollback emits one `blueprint.rolled_back` with `change_id` = forward artifact id and `revision` = base revision.

Export
- ADP-C-057 Two `export_config` calls return byte-identical canonical `export`; `exportHash` = sha256 of those bytes.
- ADP-C-058 Two fresh sites that receive the same artifacts in the same order have equal `exportHash`.
- ADP-C-059 `export` holds only `exportedProperties` per kind, no timestamps or engine-generated ids, element arrays sorted by id except the order-significant collections in 5.8.
- ADP-C-060 For the sample sequence, the real adapter's `exportHash` after each step equals the fake's (required at BPL-027, reported from BPL-012).

Members
- ADP-C-061 `full` sync creates active shadow users with exactly the listed roles and disables unlisted ones; counts match.
- ADP-C-062 `delta` sync changes only the listed members.
- ADP-C-063 A `syncVersion` not above the last gives `stale_sync_version`, no change; replay with the same key returns the stored result.
- ADP-C-064 An unknown or inactive role gives `unknown_role` and no member changes.
- ADP-C-065 Shadow users cannot authenticate and receive no email (harness auth probe; fake asserts no credential is stored).
- ADP-C-066 A disabled member's shadow user cannot act (harness action probe).

Events, health, determinism
- ADP-C-067 Each terminal apply or rollback emits exactly the events of 8.2, once; `outcome.eventIds` lists them; no event `data` contains a tenant id.
- ADP-C-068 `health` validates; for a tenant without a site it gives `site_not_ready` or `tenant_not_found`.
- ADP-C-069 Production builds expose no fault hooks: the hooks are absent from `capabilities` and calling them fails.
- ADP-C-070 Every changing call writes exactly one audit record whose `auditId` is the response's; reads also write one.

## 15. How the two sides build in parallel
| | Eldon (compiler side) | Partner (engine side) |
|---|---|---|
| Builds | `services/blueprint/adapter`: in-memory fake adapter implementing every operation, and the conformance suite (pytest), parametrised by an `AdapterHarness` (15.1) | `apps/engine` real adapter (BPL-012, ERP-012) and apply with preview, plan gate and rollback (BPL-007) |
| Proves with | fake passes the whole suite; compiler (BPL-004) output validates and applies on the fake | real adapter passes the same suite against a real bench |
| Joins at | BPL-027: compile the trading fixture and apply it through the real adapter; ADP-C-060 |

### 15.1 Harness
`AdapterHarness`: `call(operation, context, input) -> response`; `fault(stage, step_seq=None, post_condition_id=None, during_compensation=False)` (test builds only); `data_probe(pointer, value)` writes and reads a stored value for quarantine tests; `auth_probe(member_ref)` and `action_probe(member_ref)` for shadow users; `events()` returns emitted events; `reset()`. The suite never imports adapter internals.

### 15.2 The compiler side must not assume
- That the real adapter supports every step kind: read `capabilities` and expect `unsupported`.
- That plan gives `auto_approved`: most storage changes are `gated` on the real engine.
- Timings, or that apply is fast enough to be synchronous.
- That export elements carry properties beyond `exportedProperties`, or that labels round-trip unless listed.
- That the fake's internal state shape means anything; only responses count.

### 15.3 The engine side must not assume
- That an artifact is trustworthy because the control plane sent it: verify hash, schema, versions, base, every time.
- That `approvals` references are checked elsewhere for presence; it must refuse when one is missing. (Their truth is the control plane's.)
- Any tenant, role or user from `input` or from the artifact.
- That `definition` values are safe to place in code, queries, templates or engine object names.
- That the compiler orders or coalesces correctly: re-check the order rules and reject a malformed artifact.
- That rollback is only called after success, or only once.

### 15.4 Both must not assume
That the other side has shipped: each tests only against the contract, the samples and the suite. A contract change is an ADR and a version bump, then both sides update.

## 16. Open questions (not decided here)
1. Service authentication between our services and the adapter (mutual TLS or signed tokens) and who issues the identities. Needs INF and SEC input.
2. Whether `apply` takes a full site backup before `prepare` for production sites, or relies on per-step journals only.
3. Exact `exportedProperties` per kind, and whether all label locales round-trip through the engine (affects ADP-C-032 and ADP-C-060).
4. Gate approval event: add `blueprint.gate_approved` (section 10) or reuse `blueprint.change_approved`.
5. Whether `semantic` changes (for example making a field required with existing empty values) are ever allowed in 0.1.0 or always blocked.
6. Who maintains the protected-subject list neutrally (it is engine-specific today, in `safety_guardrails.py`).
7. Quarantine retention and purge: per tenant or platform default (change-engine open question 2); purge is not an adapter operation yet.
8. Signing keys for `integrity.signature`: who holds them, rotation, and whether the adapter verifies in 0.1.x.
9. Whether `settings.set` for compliance (country, VAT number, currency, fiscal year) is ever applied by this path after go-live, or only at initial build.
10. Engine requirements for shadow users (whether the engine needs an email-like user name) are UNVERIFIED; the adapter must generate internal names that are not personal data.
11. Whether location elements (branches, warehouses) are engine configuration or business records.
12. Whether adapter ids should be neutral (the example Blueprint uses the engine's name as `engineTarget.adapter`); today they are internal and stripped by the gateway.

## 17. Assumptions and unverified points
- Engine behaviour (implicit commits on storage changes, how impersonation and site context work) is UNVERIFIED until ERP-001 and CE-SEC-005.
- The bpdiff diff format is a draft (services/blueprint/diff); `diffHash` and `risk` follow its 0.1.0 output.
- Default deadlines and limits are proposals, UNVERIFIED until ERP-002.
- The approval event ids are recorded, not verified, by the adapter; the control plane is trusted for them over the authenticated service channel.
