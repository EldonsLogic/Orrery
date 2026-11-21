# Role and permission mapping

Status: draft
Owner: partner
Approved by: pending (with [ADR-0039](../decisions/ADR-0039-role-and-permission-mapping.md))

Plan ID: ERP-008. Detail for ADR-0039. Nothing here is built. This is internal documentation and may name the engine (ADR-0016). Engine behaviour is UNVERIFIED until the bench tests named here pass on the pinned version set (ERP-001, ERP-024). Engine concepts: https://docs.frappe.io/framework/user/en/basics/users-and-permissions and https://docs.frappe.io/erpnext/perm-levels, accessed 2026-11-18.

## 1. Inputs and outputs
| Input | Source | Trust |
|---|---|---|
| Roles, entities, fields, locations, workflows | Applied Blueprint revision, via the compiled artifact (contract section 9) | Verified by hash and schema; values are data, never code (T24, T26) |
| Entity, field, location and transition names in the engine | Engine mapping (contracts/engine-mapping.md, `roleMapping` and entity maps) plus entity reviewed mapping of engine draft capability and Blueprint `workflows[].transitions[].kind` (ADR-0037) | Reviewed, versioned |
| Who holds which role | Single authoritative assignment store **outside the engine site** (regional provisioning assignment store, proposed replacement of [ADR-0007](../decisions/ADR-0007-identity.md) item 9 location wording; Q-292 blocks implementation pending founder acceptance), delivered by `sync_members` (follow-up `sync_principals` / extended `sync_members` contract ADR for agents & support) | Authenticated service channel only |
| Baseline grants | Component manifests or engine mapping (D-5); validated strictly read-only, non-C3/C4, never `All`/`Guest` | Reviewed, versioned, structurally linted |

| Output (per site, all adapter-managed) | Engine object |
|---|---|
| Managed role per Blueprint role and per agent/support grant | Role, flagged managed in the adapter's own registry (`role.upsert` reuses disabled managed role on restore) |
| Permission rules | Custom permission rules per (managed role, document type, level) |
| Field levels | Field permission level property per mapped field (and `read_only=1` at level 0 for uniformly read-only/computed fields) |
| Workflow transition rights | Allowed role on each mapped transition |
| Record scope | User permission rows per shadow/agent user, limited to the document types of the scoped role |
| Assignments | Managed roles on each shadow, agent and support user, set only by `sync_members` / `sync_principals` |

## 2. Action table
| Blueprint action | Engine rule flags | Condition |
|---|---|---|
| read | read | always |
| read | report, print | Only after `DENY-21`, `DENY-22` and `DENY-23` pass on the bench. Off until then |
| create | create | needs read on the same entity in the Blueprint, else the plan rejects; masked-entity create gated on `DENY-23` |
| update | write | needs read; masked-entity write gated on `DENY-23`; for agents, restricted to `docstatus == 0` drafts on entities whose reviewed mapping of engine draft capability and Blueprint `workflows[].transitions[].kind` (ADR-0037) permits drafts, and stripped on non-submittable master/settings entities (`DENY-36`) |
| delete | delete | needs read; never for agent roles |
| submit | submit | needs read; never for agent roles |
| cancel | cancel | needs read; never for agent roles |
| create and cancel | amend | both present; never for agent roles (`DENY-40`) |
| export | export | needs read; never for agent roles |
| approve | no document flag; allowed role on the workflow transitions the Blueprint approval rule names | never for agent roles |
| (none) | share, import, set user permissions, email | never granted |

| Blueprint scope | Engine mechanism |
|---|---|
| company | none |
| branch, warehouse, department | User permission per holder on the mapped location record, applicable only to the role's document types. Plan rejects if any granted non-baseline entity lacks a link field for that location type (`DENY-35`) |
| own_records | Owner-only flag (`if_owner`) on the role's rules |
| assigned_records | none verified: plan rejects with `unsupported_value_type` |
| Multiple roles with differing scopes on a shared entity | Forbidden (fails open under engine OR union semantics): rejected at assignment store & `sync_members` (`scope_conflict`; `DENY-34`) |

| Blueprint flag | Engine effect |
|---|---|
| isAdmin | none (platform right only, `DENY-41`) |
| canUseChatActions | none (gateway only, `DENY-41`) |

## 3. Permission levels
For entity E with mapped fields F and roles R that have read on E:
1. For each field f, the signature is `sig(f)` = the sorted list of `(role, mode)` with mode `w` (writable), `r` (read-only) or `h` (hidden). A role's mode comes from its `hiddenFields` and `readOnlyFields`. It is `r` if the role lacks update, and `r` for all roles if the field is Blueprint `readOnly` or computed (which is marked `read_only=1` on the DocField).
2. A field whose signature is uniform across all read-capable roles—every role `w`, or `r` where the role lacks `update`, or `r` for all roles because the field is `readOnly` or computed—stays at level 0 so uniformly read-only/computed fields do not consume permlevels 1 to 9.
3. Other signatures keep the level they had in the previous layout. New signatures take the lowest free level, 1 to 9. A level whose signature disappears is freed only after its fields have moved.
4. For each role and level: read if the mode is not `h` for those fields; write if the mode is `w`.
5. If more than 9 signatures are needed, the plan rejects with `limit_exceeded` (`limit: permission_levels`).
6. Child-table fields follow the same rule on the child type. Whether the engine applies child-field levels across parent forms, REST `insert`/`PUT`, mandatory (`reqd`) hidden fields, and reports is UNVERIFIED until `DENY-23` and `DENY-38` pass on the bench (gating `RM-018`).

The layout is a pure function of (previous layout, target roles, target fields). Same inputs, same bytes (contract principle 4).

## 4. Drift fingerprint
`sha256` over canonical JSON (sorted keys, sorted arrays) of:
- all managed roles and their rules;
- all custom permission rules on mapped document types, plus all permissions held by built-in/automatic roles (`All`, `Guest`, `Desk User`, `Website Manager`) across mapped AND unmapped business, audit, system, file and ledger types (`Version`, `Comment`, `Communication`, `Activity Log`, `Notification Log`, `File`, `ToDo`, `User`, `Prepared Report`, `Data Import`, `GL Entry`, `Stock Ledger Entry`) outside an explicit reviewed allowlist;
- the level of every mapped field;
- transition allowed roles on mapped workflows;
- the complete user inventory, enabled flags and **every** role on every user (shadow, agent, support, unmanaged, including disabled users) (managed AND built-in/automatic), plus user permission rows;
- reviewed baseline grants (structurally checked: read-only only, no C3/C4 fields, never `All`/`Guest`).

The expected value is computed from the applied Blueprint, the mapping, the baseline grants and the external assignment store at `syncVersion`. It is compared:
- as a post-condition of every `sync_members` and of every role-touching `apply` (which clears affected user caches, invokes `sync_members` with a new store-issued monotonic `syncVersion`, and checks the full fingerprint before reporting `applied`);
- on a schedule (D-1);
- on demand from the team console.

On mismatch the adapter records the diff internally, alerts, strips any non-managed roles from engine users / disables unmanaged enabled users / removes extra grants first, then restores missing approved rules from the Blueprint layout, then re-checks. Restoring an already-approved Blueprint layout is reconciliation rather than a new permission grant under [ADR-0027](../decisions/ADR-0027-human-floor-action-policy-and-agent-authority.md). A second consecutive mismatch marks the site `recovery_required`.

## 5. Fail-closed requirements
| ID | Requirement |
|---|---|
| RM-001 | No role, scope, user or tenant is read from `input`, the artifact, a model output or an event; only `sync_members` (or follow-up `sync_principals`) sets assignments from the external assignment store (CE-SEC-001) |
| RM-002 | Any failed lookup (assignment store, mapping, engine read, cache) denies; no default role, no stale cache past D-2, no fallback to System Manager, Administrator or any built-in role (CE-SEC-002) |
| RM-003 | Unmapped entity, field, action, location or scope rejects the role step at plan |
| RM-004 | No built-in engine role is ever granted, edited or assigned by the adapter |
| RM-005 | Automatic/built-in engine roles (`All`, `Guest`, `Desk User`, `Website Manager`) hold zero permissions on mapped types AND on unmapped business/audit/system/file/ledger DocTypes outside an explicit reviewed minimal allowlist; checked before `ready` and in every drift check |
| RM-006 | Unknown role in an assignment: `unknown_role`, no member changes (contract 5.9) |
| RM-007 | A member with no active role has a disabled shadow user |
| RM-008 | A disabled Blueprint role has no rules and no holders, and its record is kept (`role.upsert` reuses it on re-enable) |
| RM-009 | Removing a role that is still assigned is refused (`subject_in_use`) |
| RM-010 | The engine permission cache is cleared for affected users before the apply reports success |
| RM-011 | Drift strips non-managed roles/unmanaged enabled users and removes extra grants before restoring approved layout; repeated drift sets `recovery_required` |
| RM-012 | `recovery_required` makes the gateway refuse tenant calls except platform status reads |
| RM-013 | Agent engine users have no password, API key or email, cannot sign in, carry one managed role per grant, receive `create`/`write` only on `docstatus == 0` drafts of draft-capable entities (non-submittable master/settings create and write stripped), disable synchronously on revoke/expire/kill (`ALP-022`), fail closed when kill flag is unreachable (`ALP-036`), and use principal-kind-bound `S09` credentials |
| RM-014 | No agent call runs as a human shadow user; engine bounds the grant only while the gateway enforces on-behalf-of intersection (residual risk documented) |
| RM-015 | Multiple roles on one member with different scopes on a shared entity (`own_records` + `branch`, `branch-A` + `branch-B`) are forbidden and rejected at assignment store & `sync_members` (`scope_conflict`) |
| RM-016 | `isAdmin` produces no engine permission |
| RM-017 | Share, import, set user permissions and email are never granted |
| RM-018 | Report, print, and masked-entity `create`/`write` stay gated until `DENY-21`, `DENY-22`, `DENY-23`, and `DENY-38` pass on the bench |
| RM-019 | A role with `branch`, `warehouse` or `department` scope rejects at plan if any granted non-baseline entity lacks a mapped link field for that location type (`DENY-35`) |
| RM-020 | A role-touching `apply` never reports `applied` until permission cache clear, full `sync_members` at a newly allocated store-issued `syncVersion`, and full drift fingerprint post-condition succeed; failure compensates or enters `recovery_required` (`DENY-43`) |
| RM-021 | Baseline reference-data grants must pass structural validation: `read`-only, no C3/C4 fields, never `All`/`Guest` (`DENY-45`) |
| RM-022 | Gateway error mapping (`PLT-024`) strips managed engine role names so engine identifiers never surface to callers (`ADR-0016`, `DENY-46`) |

## 6. Denied-case tests the implementation must ship
Each runs against the fake adapter and the real adapter on a bench. "Denied" means: no effect, an audit record and the contract's refusal event. Probes use the harness `action_probe` and an extended probe per entity, action and field (the harness extension needs a contract ADR, Eldon's lane).

| ID | Case | Expected |
|---|---|---|
| DENY-01 | `sync_members` input carries an extra `roles`, `isAdmin`, or `canUseChatActions` key | `invalid_request`, no change |
| DENY-02 | Artifact or `input` names a user or role to assign | Rejected; assignments unchanged |
| DENY-03 | `onBehalfOf.roleIds` lists the owner role for a sales user's call | Result identical to without it (ADP-C-012) |
| DENY-04 | Assignment store unreachable during sync | Sync fails; no shadow user gains a role |
| DENY-05 | Engine role read raises an error during a permission check | Denied; never System Manager or Administrator |
| DENY-06 | Mapping lacks an entity a role grants | Plan rejects the role step |
| DENY-07 | Mapping lacks a field in `hiddenFields` | Plan rejects; no rule written |
| DENY-08 | Blueprint action not in the action table (future enum value) | Plan rejects |
| DENY-09 | Role with `assigned_records` scope | Plan rejects (`unsupported_value_type`) |
| DENY-10 | Branch scope naming a location that is not applied | Plan rejects (`subject_missing`) |
| DENY-11 | Unknown role id in `sync_members` | `unknown_role`; no member changed |
| DENY-12 | Member with zero roles | Shadow user disabled; action probe denied |
| DENY-13 | Shadow user holding no managed role reads each mapped type | Denied for all (automatic roles carry nothing) |
| DENY-14 | Sales role with `credit_limit` hidden reads a customer via form, list, report and API | Field absent everywhere |
| DENY-15 | Role with `readOnlyFields` writes that field | Denied; value unchanged |
| DENY-16 | Branch-A user reads, lists and links a branch-B record | Not found / denied |
| DENY-17 | own_records user reads another user's record | Denied |
| DENY-18 | Role with read only tries create, write, delete, submit, cancel, export | Each denied |
| DENY-19 | Role without approve fires the approval transition | Denied |
| DENY-20 | Any managed role tries share, import, set user permissions, email | Denied |
| DENY-21 | Hidden field via print and print preview | Absent (gates RM-018) |
| DENY-22 | Out-of-scope record via report view and export | Absent (gates RM-018) |
| DENY-23 | Hidden child-table field via parent form, report and API | Absent (gates RM-018 alongside DENY-21 and DENY-22) |
| DENY-24 | Ten distinct role-varying field signatures on one entity (uniform `readOnly`/computed fields excluded at level 0) | Plan rejects (`limit_exceeded`) |
| DENY-25 | Remove a role still assigned | `subject_in_use`; nothing changes |
| DENY-26 | Narrow a role while a user's session is cached | Next call denied (cache cleared, RM-010) |
| DENY-27 | Staff adds a rule to a managed role directly in the engine | Drift detected; extra rule removed; alert |
| DENY-28 | Staff grants System Manager to a shadow user directly | Drift detected; non-managed role stripped first; alert |
| DENY-29 | Fault during role reconciliation | Compensated to before-layout; fingerprint equals pre-apply |
| DENY-30 | Fault during that compensation | `recovery_required`; gateway refuses tenant calls |
| DENY-31 | Agent user signs in, uses an API key or receives email | Not possible |
| DENY-32 | Agent grant includes submit or approve | Stripped; agent submit and approve denied |
| DENY-33 | Agent call attempts to run as its owner's shadow user or use human-bound `S09` credential | Refused by the adapter |
| DENY-34 | Member assigned conflicting scopes on a shared entity (`own_records` + `branch`, or `branch-A` + `branch-B`); vs non-conflicting roles on disjoint entities (branch-A sales + company-wide read-only on separate DocType) | Shared-entity mixed scope rejected (`scope_conflict`); disjoint scopes enforced per entity without widening |
| DENY-35 | Branch-scoped role grants a non-baseline entity with no mapped `branch` field | Rejected at plan (`RM-019`) |
| DENY-36 | Agent attempts direct `create` or `write` on non-submittable master or settings entity (Supplier bank details, Customer, Item, price list) | Denied (only `docstatus == 0` drafts on draft-capable entities allowed) |
| DENY-37 | Normal shadow user or automatic role probes unmapped audit/system/file/ledger DocTypes (`Version`, `Comment`, `File`, `Communication`, `Prepared Report`, `User`, `GL Entry`) | Denied; automatic permissions stripped before `ready` and by drift (`RM-005`) |
| DENY-38 | Caller injects `hiddenFields` or `readOnlyFields` (including child-table fields and `reqd` hidden fields) via `insert` or REST `PUT` | Rejected or stripped; field unaltered on stored record (gates RM-018) |
| DENY-39 | `branch-A` user invokes autocomplete (`search_link` / `validate_link`) targeting `branch-B` `Customer` or `Employee` | Out-of-scope records absent; existence not leaked |
| DENY-40 | Role has `create` without `cancel` (tries `amend`), or has `amend` flags without `update`/`submit` | Amend refused unless both `create` and `cancel`; absent update/submit still denied |
| DENY-41 | Member with `isAdmin: true` and minimal Blueprint role tries admin/system actions in engine | Zero extra engine rights granted (`RM-016`) |
| DENY-42 | Revoked, expired, or killed agent calls adapter, or kill-flag store unreachable during agent call | Agent user disabled synchronously; adapter fails closed (`ALP-022`, `ALP-036`) |
| DENY-43 | Fault in `sync_members` immediately after a role-touching `apply` narrows role scope | `apply` compensates back to pre-apply layout (or `recovery_required`); never reports `applied` (`RM-020`) |
| DENY-44 | Unmanaged enabled engine user created directly in site, or extra built-in role attached | Caught by drift fingerprint; unmanaged user disabled and role stripped first (`RM-011`) |
| DENY-45 | Baseline grant proposal with `write`/`create`/`export`, C3/C4 field, or `All`/`Guest` role | Rejected by structural lint/validation (`RM-021`) |
| DENY-47 | Agent attempts create or write on submitted/cancelled document, or create Supplier, Item or price list directly | Denied; no live master or document mutation; pending-change draft only |
| DENY-48 | Member with canUseChatActions false invokes a chat action; repeat human-scope/agent-grant TC-13 mismatch | Gateway refuses; engine alone bounds agent grant only, residual dependency recorded |
| DENY-46 | Engine permission error mentioning a managed engine role name passes through gateway (`PLT-024`) | Managed role name stripped from customer-visible error (`RM-022`, `ADR-0016`) |

Allowed-case controls (so denies are not vacuous): the owner role can do every action the Blueprint lists; a sales role can create an order in its branch; an accountant sees `credit_limit`.

## 7. Decisions needed
1. **D-1** Drift check schedule (proposed hourly per site plus every apply and sync).
2. **D-2** Maximum age of any cached role or permission set (proposed 0 at the gateway; the engine's cache is cleared on change).
3. **D-3** Whether `assigned_records` gets an engine mechanism (a reviewed permission-query component) or stays gateway-only.
4. **D-4** *(Resolved)* Forbid one member from holding multiple roles with differing scopes on any shared entity; enforced at the assignment store and `sync_members`.
5. **D-5** Whether reference-data baseline grants live in component manifests (contracts lane) or in the engine mapping (both subject to `RM-021`).

## 8. Open questions
1. *(Resolved for Eldon's review)* `agent-least-privilege.md` §3.1, `ALP-001`, and `OQ-2` are updated in this PR to state that an agent never uses a human shadow engine user and gets a separate draft-only agent engine user carrying one grant-intersected managed role per agent grant (`ADR-0039`).
2. Per-member scope values (a sales rep for branch A, another for branch B, same role) are not in Blueprint schema v0; today that needs two roles. A schema change is Eldon's lane.
3. Follow-up contract ADR (Eldon's lane): extend `sync_members` or add `sync_principals` to carry agent (`ag_*`) and JIT support (`PLT-019`) principals with grant-intersected capability sets and expiry (`S17`), plus `engine.permission_drift` on `contracts/events.md`.

Implementation gates: Q-292 must be resolved before moving assignments outside the engine site. Agent draft capability is reviewed mapping metadata, not a nonexistent manifest `transitionKind` field: ADR-0037 defines Blueprint transition `kind`, which alone does not establish a safe engine draft state. Missing capability proof denies agent writes. Hold a tenant reconciliation fence over apply, full sync and fingerprint verification, blocking tenant business calls; retain it on any failed or unverified compensation.
