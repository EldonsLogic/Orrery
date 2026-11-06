# Build states

Version: 0.1.0
Status: draft
Owner: eldon

The lifecycle of a client build, from first conversation to a live tenant. The control plane (Part 5) owns the state; every transition is an event ([events.md](events.md)) and is audited. `meta.buildState` in the [Blueprint](blueprint.schema.json) mirrors it.

```
draft -> owner_approved -> team_reviewed -> built_in_sandbox -> simulated -> live
                           (HUMAN GATE)
```

## Transitions

| From | To | Triggered by | Preconditions | Result |
|---|---|---|---|---|
| (none) | draft | Discovery (AI) | Owner started a chat or uploaded sources | Blueprint revision 1 created; provenance recorded |
| draft | draft | AI or owner | Owner edits or AI refines | New revision; validator must pass before it is saved as approvable |
| draft | owner_approved | Owner (role with isAdmin) | Validator passes; owner has seen the plain-language summary, the quote and the open gaps | Revision frozen; quote accepted |
| owner_approved | team_reviewed | Team reviewer (human) | Review checklist complete: compliance profile, rigid components, new component requests, data mapping, permissions, branding assets | HUMAN GATE. Only a named internal reviewer can pass it. Reviewer id stored |
| owner_approved | draft | Team reviewer or owner | Reviewer rejects or owner reopens | Back to editing; new revision; approvals reset |
| team_reviewed | built_in_sandbox | Compiler + engine adapter (automatic) | All referenced components certified at the required level and compatible with the pinned engine set | Sandbox tenant provisioned and configured; no real data |
| built_in_sandbox | simulated | Simulator (automatic), confirmed by team reviewer | Replay of the owner's real or sample month completes; reconciliation checks pass; failures triaged | Simulation report attached; owner reviews it |
| simulated | live | Team reviewer starts cutover, owner confirms | Owner signs off on the simulation; opening balances approved; backups verified; compliance onboarding done (for example ZATCA onboarding) | Production tenant active; entitlements applied; metering on |
| any | draft (new revision) | Owner via chat (change request) | Tenant is live | Change goes through the Blueprint path: diff, simulate, approve, apply. See "Changes after go-live" |

Skipping a state is not possible. The control plane rejects any transition whose preconditions are not recorded.

## Who may do what

| Actor | Allowed |
|---|---|
| AI agents | Create and edit drafts, request transitions, run builds in sandbox, run simulations. Never approve, never pass the human gate, never go live |
| Owner / admin role | draft to owner_approved, reopen to draft, confirm cutover |
| Team reviewer | owner_approved to team_reviewed (the gate), reject, start cutover |
| Control plane | Enforce preconditions, record events, provision environments |

The gate may loosen per plan tier later (for example no human review for template-only builds with only certified components). That is an ADR-level change; until then every first-client build needs the gate (ADR-0005 in [docs/decisions/](../docs/decisions/)).

## Rollback rules
1. **Before live:** any state may return to `draft`. Sandbox tenants are destroyed; nothing is retained except the Blueprint revisions and the audit trail.
2. **After live:** a change creates a new Blueprint revision and goes through diff, simulation against the tenant's own history, approval, apply. Apply is atomic per change set and every change set has a stored inverse (the "undo plan").
3. **Data-destructive inverses** (dropping a field that holds data) are never automatic: the change engine quarantines the field (soft delete), keeps data for a retention window, and only a human can purge it.
4. **Failed apply:** the engine adapter reports failure, the change set is rolled back with its inverse, the tenant stays on the previous revision, an `blueprint.apply_failed` event is raised and the team is notified.
5. **Engine upgrades** follow canary rules in [engine-adapter.md](../docs/architecture/engine-adapter.md) and do not change `buildState`.
6. **Ledger-affecting data** (posted documents) is never rolled back by Blueprint rollback. Corrections are new documents (credit notes, reversals), as the engine requires.

## Changes after go-live
Rigid-zone parameters (anything marked `affectsLedgerOrTax`) always need team review, even after the gate loosens. Configurable-zone changes can be owner-approved and applied automatically once the change engine's policy allows it.

## Tenant lifecycle (separate from build states)
Trial, active, suspended, exported, deleted. Owned by Part 5; see [platform spec](../docs/specs/05-platform.md).

## Events emitted
`build.state_changed` on every transition, plus `build.review_passed`, `build.review_rejected`, `build.sandbox_ready`, `build.simulation_completed`, `build.cutover_started`, `build.live`. Schemas in [events.md](events.md).
