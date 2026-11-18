# Role and permission mapping

Status: draft
Owner: partner
Approved by: pending (with [ADR-0039](../decisions/ADR-0039-role-and-permission-mapping.md))

Plan ID: ERP-008. Detail for ADR-0039. Nothing here is built. This is internal documentation and may name the engine (ADR-0016). Engine behaviour is UNVERIFIED until the bench tests named here pass on the pinned version set (ERP-001, ERP-024). Engine concepts: https://docs.frappe.io/framework/user/en/basics/users-and-permissions and https://docs.frappe.io/erpnext/perm-levels, accessed 2026-11-18.

## 1. Inputs and outputs
| Input | Source | Trust |
|---|---|---|
| Roles, entities, fields, locations, workflows | Applied Blueprint revision, via the compiled artifact (contract section 9) | Verified by hash and schema; values are data, never code (T24, T26) |
| Entity, field and location names in the engine | Engine mapping (contracts/engine-mapping.md, `roleMapping` and entity maps) | Reviewed, versioned |
| Who holds which role | Tenant assignment store (ADR-0007 item 9), delivered by `sync_members` from control_plane or identity | Authenticated service channel only |
| Baseline grants | Component manifests (reviewed) | Reviewed, versioned |

| Output (per site, all adapter-managed) | Engine object |
|---|---|
| Managed role per Blueprint role and per agent grant | Role, flagged managed in the adapter's own registry |
| Permission rules | Custom permission rules per (managed role, document type, level) |
| Field levels | Field permission level property per mapped field |
| Workflow transition rights | Allowed role on each mapped transition |
| Record scope | User permission rows per shadow user, limited to the document types of the scoped role |
| Assignments | Managed roles on each shadow user, set only by `sync_members` |

## 2. Action table
| Blueprint action | Engine rule flags | Condition |
|---|---|---|
| read | read | always |
| read | report, print | Only after DENY-21 and DENY-22 pass on the bench. Off until then |
| create | create | needs read on the same entity in the Blueprint, else the plan rejects |
| update | write | needs read |
| delete | delete | needs read; never for agent roles |
| submit | submit | needs read; never for agent roles |
| cancel | cancel | needs read; never for agent roles |
| create and cancel | amend | both present |
| export | export | needs read; never for agent roles |
| approve | no document flag; allowed role on the workflow transitions the Blueprint approval rule names | never for agent roles |
| (none) | share, import, set user permissions, email | never granted |

| Blueprint scope | Engine mechanism |
|---|---|
| company | none |
| branch, warehouse, department | User permission per holder on the mapped location record, applicable only to the role's document types |
| own_records | Owner-only flag on the role's rules |
| assigned_records | none verified: plan rejects with `unsupported_value_type` |

| Blueprint flag | Engine effect |
|---|---|
| isAdmin | none (platform right only) |
| canUseChatActions | none (gateway only) |

## 3. Permission levels
For entity E with mapped fields F and roles R that have read on E:
1. For each field f, the signature is `sig(f)` = the sorted list of `(role, mode)` with mode `w` (writable), `r` (read-only) or `h` (hidden). A role's mode comes from its `hiddenFields` and `readOnlyFields`. It is `r` if the role lacks update, and `r` for all roles if the field is `readOnly` or computed.
2. A field whose signature is "every role w, or r where the role lacks update" stays at level 0.
3. Other signatures keep the level they had in the previous layout. New signatures take the lowest free level, 1 to 9. A level whose signature disappears is freed only after its fields have moved.
4. For each role and level: read if the mode is not `h` for those fields; write if the mode is `w`.
5. If more than 9 signatures are needed, the plan rejects with `limit_exceeded` (`limit: permission_levels`).
6. Child-table fields follow the same rule on the child type. Whether the engine applies child-field levels in every view is UNVERIFIED (DENY-23).

The layout is a pure function of (previous layout, target roles, target fields). Same inputs, same bytes (contract principle 4).

## 4. Drift fingerprint
`sha256` over canonical JSON (sorted keys, sorted arrays) of:
- managed roles and their rules;
- rules held by engine automatic roles on mapped types;
- the level of every mapped field;
- transition allowed roles on mapped workflows;
- per shadow user and agent user: enabled flag, managed roles and user permission rows.

The expected value is computed from the applied Blueprint, the mapping, the baseline grants and the assignment store at `syncVersion`. It is compared:
- as a post-condition of every apply that touches roles and of every `sync_members`;
- on a schedule (D-1);
- on demand from the team console.

On mismatch the adapter records the diff internally, alerts, removes extra grants first, then restores missing approved grants, then re-checks. A second mismatch marks the site `recovery_required`.

## 5. Fail-closed requirements
| ID | Requirement |
|---|---|
| RM-001 | No role, scope, user or tenant is read from `input`, the artifact, a model output or an event; only `sync_members` sets assignments (CE-SEC-001) |
| RM-002 | Any failed lookup (assignment store, mapping, engine read, cache) denies; no default role, no stale cache past D-2, no fallback to System Manager, Administrator or any built-in role (CE-SEC-002) |
| RM-003 | Unmapped entity, field, action, location or scope rejects the role step at plan |
| RM-004 | No built-in engine role is ever granted, edited or assigned by the adapter |
| RM-005 | Automatic engine roles hold no permission on mapped types; checked before `ready` and in every drift check |
| RM-006 | Unknown role in an assignment: `unknown_role`, no member changes (contract 5.9) |
| RM-007 | A member with no active role has a disabled shadow user |
| RM-008 | A disabled Blueprint role has no rules and no holders, and its record is kept |
| RM-009 | Removing a role that is still assigned is refused (`subject_in_use`) |
| RM-010 | The engine permission cache is cleared for affected users before the apply reports success |
| RM-011 | Drift removes extra grants before restoring missing ones; a repeated drift sets `recovery_required` |
| RM-012 | `recovery_required` makes the gateway refuse tenant calls except platform status reads |
| RM-013 | Agent users have no password, API key or email, cannot sign in, and never hold submit, cancel, approve, delete or export |
| RM-014 | No agent call runs as a human shadow user |
| RM-015 | Multiple roles with different scopes on one type: the narrower scope applies on that type |
| RM-016 | `isAdmin` produces no engine permission |
| RM-017 | Share, import, set user permissions and email are never granted |
| RM-018 | Report and print stay off until DENY-21 and DENY-22 pass on the bench |

## 6. Denied-case tests the implementation must ship
Each runs against the fake adapter and the real adapter on a bench. "Denied" means: no effect, an audit record and the contract's refusal event. Probes use the harness `action_probe` and an extended probe per entity, action and field (the harness extension needs a contract ADR, Eldon's lane).

| ID | Case | Expected |
|---|---|---|
| DENY-01 | `sync_members` input carries an extra `roles` or `isAdmin` key | `invalid_request`, no change |
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
| DENY-23 | Hidden child-table field via parent form, report and API | Absent |
| DENY-24 | Ten distinct field signatures on one entity | Plan rejects (`limit_exceeded`) |
| DENY-25 | Remove a role still assigned | `subject_in_use`; nothing changes |
| DENY-26 | Narrow a role while a user's session is cached | Next call denied (cache cleared, RM-010) |
| DENY-27 | Staff adds a rule to a managed role directly in the engine | Drift detected; extra rule removed; alert |
| DENY-28 | Staff grants System Manager to a shadow user directly | Drift detected; removed; alert |
| DENY-29 | Fault during role reconciliation | Compensated to before-layout; fingerprint equals pre-apply |
| DENY-30 | Fault during that compensation | `recovery_required`; gateway refuses tenant calls |
| DENY-31 | Agent user signs in, uses an API key or receives email | Not possible |
| DENY-32 | Agent grant includes submit or approve | Stripped; agent submit and approve denied |
| DENY-33 | Agent call attempts to run as its owner's shadow user | Refused by the adapter |
| DENY-34 | Member with branch-A sales and company-wide read-only roles reads branch-B orders | Denied on orders (narrower scope wins); allowed on types only the read-only role grants |

Allowed-case controls (so denies are not vacuous): the owner role can do every action the Blueprint lists; a sales role can create an order in its branch; an accountant sees `credit_limit`.

## 7. Decisions needed
1. **D-1** Drift check schedule (proposed hourly per site plus every apply and sync).
2. **D-2** Maximum age of any cached role or permission set (proposed 0 at the gateway; the engine's cache is cleared on change).
3. **D-3** Whether `assigned_records` gets an engine mechanism (a reviewed permission-query component) or stays gateway-only.
4. **D-4** Whether one member may hold roles with different scopes at all, or the assignment screen refuses it (simpler and stricter).
5. **D-5** Whether reference-data baseline grants live in component manifests (contracts lane) or in the engine mapping.

## 8. Open questions
1. ALP section 3.1 says the agent gets "a separate shadow user"; the brief for this row says "no shadow users". This design reads both as: an agent never uses a human's shadow user, and has its own engine principal that cannot sign in. Founders confirm.
2. Per-member scope values (a sales rep for branch A, another for branch B, same role) are not in Blueprint schema v0; today that needs two roles. A schema change is Eldon's lane.
