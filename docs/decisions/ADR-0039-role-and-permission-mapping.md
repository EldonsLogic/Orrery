# ADR-0039: Blueprint roles map to adapter-owned engine roles, field levels and record scopes by a fixed table; anything unmapped or unresolved is denied

Status: Proposed
Owner: partner
Approved by: pending (cross-model review, then both founders; security review required by RULES 42 because this touches authorisation)

Plan ID: ERP-008. Design only; no code until this is reviewed and accepted. Detail (mapping tables, permission-level algorithm, drift fingerprint, the 34 denied-case tests DENY-01 to DENY-34) is in [../architecture/role-and-permission-mapping.md](../architecture/role-and-permission-mapping.md). References ADR-0038 (SEC-002), which is in an open PR at the time of writing.

## Context
- A Blueprint role (contracts/blueprint.schema.json `role`) has `function`, one `scope` (company, branch, warehouse, department, own_records, assigned_records), `permissions` per entity (actions read, create, update, delete, submit, cancel, approve, export, with `hiddenFields` and `readOnlyFields`), `canUseChatActions` and `isAdmin`.
- The engine expresses access as roles, permission rules per document type and permission level, field permission levels, record-level user permissions, and role profiles (https://docs.frappe.io/framework/user/en/basics/users-and-permissions, accessed 2026-11-18; behaviour on our pinned version UNVERIFIED until the bench tests in the detail doc pass).
- Rules already settled:
  - Roles never come from the caller (CE-SEC-001).
  - Role lookup fails closed and never falls back to System Manager (CE-SEC-002).
  - Shadow engine users carry the member's Blueprint roles, and drift is a security bug (ADR-0007 items 4, 9, 11).
  - Roles map to adapter-owned roles, never built-in engine roles (contracts/engine-mapping.md).
  - The adapter never authorises on `onBehalfOf.roleIds` and accepts no role from `input` (contracts/engine-adapter.md 4.2, ADP-C-002, ADP-C-012).
  - `role.upsert` and `role.disable` are `unsupported` until ERP-008 (contract section 13).
  - Agents are their own principals and never use a human's session or shadow user (ALP-001).
- The gateway (OPR-004) is the first check on every tool call. The engine-side mapping is the second, independent check, and it is what makes "the chat can never do more than the user could in the engine's own UI" true (Tool API section 4).

## Decision
1. **One managed engine role per Blueprint role**, named deterministically from the role id with a reserved prefix and marked as adapter-managed. The adapter creates, changes and disables only managed roles. It never grants, edits or assigns a built-in engine role (System Manager, Administrator, or any other shipped role). The roles the engine attaches to every user automatically get no permission on any mapped document type: the site is checked for this before it is marked ready and on every drift check.
2. **Actions map by a fixed table** (detail section 2): read gives read; create gives create; update gives write; delete gives delete; submit gives submit; cancel gives cancel; export gives export. `approve` is never a document permission: it becomes the role's right to the matching workflow transitions. Report and print come with read only if the bench tests show they respect field levels and record scope; until then they stay off. Share, import, set-user-permissions and email are never granted. Amend is granted only with both create and cancel.
3. **Fields: hidden and read-only become permission levels, computed deterministically.** For each entity, fields are grouped by their signature (per role: writable, read-only or hidden). Fields every role treats the same stay at level 0. Every other signature gets its own level 1 to 9. Level numbers are kept for signatures that already have one, and new signatures take the lowest free level, so the layout depends only on the previous layout and the target Blueprint. More signatures than levels rejects the plan (`limit_exceeded`). A Blueprint `readOnly` field and every computed field is read-only for all roles.
4. **Record scope:**
   - `company` adds no restriction.
   - `branch`, `warehouse` and `department` become record-level user permissions on each holder's shadow user. Each points to the mapped location records and applies only to the document types that role grants.
   - `own_records` becomes the owner-only flag on that role's rules.
   - `assigned_records` has no engine equivalent we have verified, so a role with it is rejected at plan (`unsupported_value_type`). The gateway still enforces it for chat; the engine side denies, it does not widen.
   - When one member holds two roles whose scopes differ on the same document type, the narrower scope wins on that type and the assignment screen warns (WEB-010).
5. **Role profiles are not used for enforcement.** Engine roles are assigned to each shadow user directly by `sync_members`. Whether profile changes propagate to users differs between sources and versions (UNVERIFIED), and a bundle that may lag is a drift path.
6. **`isAdmin` and `canUseChatActions` are platform rights, not engine rights.** `isAdmin` maps to nothing in the engine and never to a system or administrator role. `canUseChatActions: false` is enforced by the gateway only.
7. **Fail closed everywhere** (requirement list in the detail doc section 5):
   - No role, scope or user from any request body, model output, artifact or event.
   - An unmapped entity, field, action, location or scope rejects the role step at plan. Nothing is mapped to the "nearest" permission.
   - Any engine permission on a managed or automatic role that the mapping does not produce is drift, and it is removed.
   - An unknown role in an assignment gives `unknown_role` and changes no member.
   - A failed lookup at any stage (assignment store, mapping, engine read) denies. There is no default role, no cached role set past its maximum age, and no fallback to any administrator, system or guest-with-rights role.
   - A member with no active role has a disabled shadow user.
   - A permission change that cannot be compensated leaves the site `recovery_required`, and the gateway refuses every tenant call except reads of platform status until a human resolves it.
8. **Blueprint change.**
   - Role ops arrive as `role.upsert` and `role.disable` (contract 9.3). The adapter applies all role steps of one artifact as one permission reconciliation per affected entity. It journals the before-layout and restores it on compensation. The external contract does not change.
   - Removing a role still assigned is refused (`subject_in_use`). A disabled role keeps its record for audit with all rules removed.
   - After every apply that touches roles, the engine's permission cache is cleared for the affected users and a full `sync_members` runs (ADR-0007 item 9).
   - A post-condition checks the drift fingerprint.
9. **Drift detection.** A canonical fingerprint covers managed roles, automatic roles on mapped types, field levels, workflow transition roles, shadow-user role assignments and user permissions. The expected value is computed from the applied Blueprint, the mapping and the assignment store's `syncVersion`, and is compared after every apply and sync, on a schedule and on demand. On mismatch the adapter alerts, reconciles to the expected state (extra grants removed first) and records it. A new event `engine.permission_drift` is proposed; it is not in force until the events contract ADR adds it (contract section 10 lists `engine.members_synced` the same way).
10. **Agents get their own engine principal, never a human's.**
    - Per ALP section 3.1, each agent has a separate engine user in its own namespace: no password, no API key, no email, never able to sign in.
    - It carries one managed role per agent grant (ALP OQ-2, the stricter option). That role is the agent-eligible Blueprint role intersected with the grant. Submit, cancel, approve, delete and export are always stripped (agents draft only, ALP-028).
    - No agent ever acts as a human's shadow user or as the on-behalf-of user.
    - The engine bounds the agent to its grant. The intersection with the on-behalf-of user's current permissions is enforced by the gateway (ALP-005, ALP-006) and re-checked by the adapter (ALP-023). That residual dependency is stated, not hidden.
    - Support principals follow the same pattern per support grant (PLT-019), read-only by default and expiring with the grant.

## Alternatives rejected
- **Map Blueprint roles onto built-in engine roles** (for example a finance role onto the engine's accounts roles): their permissions change with engine upgrades and are wider than the Blueprint says; contradicts contracts/engine-mapping.md.
- **One role profile per member role combination:** propagation is uncertain, and it multiplies objects without adding control.
- **Fail open with a warning when a mapping is missing** (the prototype behaviour CE-SEC-002 removed): turns every gap into silent over-permission.
- **Enforce only at the gateway:** a gateway bug, or any engine path the gateway does not cover, would expose everything. Defence in depth is the point of the shadow user.
- **Run agent calls as the on-behalf-of human's shadow user:** gives the agent everything the human can do in the engine and contradicts ALP-001.
- **Widen implicitly so documents work** (auto-granting read on linked entities): convenient but invisible. The validator should instead flag a link target the role cannot read (BPL-003 lint follow-up), and the result is a deny until the Blueprint grants it. Reference data every document needs (currency, units, the company record) comes only from reviewed per-component baseline grants listed in the mapping. These are read-only and never on C3, C4 or ledger writes.

## Consequences
- Easier: one deterministic table both sides can test; OPR-004, WEB-010 and WEB-011 build on fixed semantics; drift is measurable.
- Harder: field-level masking is limited to 9 extra signatures per entity. `assigned_records` is blocked in the engine until a reviewed mechanism exists. The report, print and automatic-role behaviour must be proven on the bench before they are enabled.
- Must be done: the engine-mapping contract's `roleMapping` (Eldon's lane) may need fields for levels and baseline grants; the implementing PR proposes that by ADR, not by editing the contract here. ERP-008 implementation ships the DENY tests in the detail doc against the fake and the real adapter. OPR-004 must meet the gateway half. PLT-003 (ADR-0040) runs the first `sync_members` and stores the drift baseline.

## Supersedes
none
