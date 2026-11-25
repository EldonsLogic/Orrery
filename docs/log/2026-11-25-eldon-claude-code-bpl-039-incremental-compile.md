# Session log: bpl-039-incremental-compile

Date: 2026-11-25
Author: eldon
Tool and model: claude-code (Opus-class subagent, one task, no further delegation)
Plan IDs: BPL-039

## Summary
First slice of BPL-039: `compile_blueprint(target, registry, mapping, environment=..., base=<revision>)` now compiles base to target with an embedded inverse (contract 9.6), with no contract change. The initial build path and its snapshots are byte-identical. Slice 2 (Studio uses it to show a real rollback) is not done; BPL-039 stays `doing`.

## Files touched
- `services/blueprint/compiler/incremental.py` (new): diff ops of every kind to steps (9.3), coalescing, `irreversible_reason`, ledger or tax detection for any step kind.
- `services/blueprint/compiler/core.py`: `base=` argument, shared gates, `_compile_change` (forward from `diff`, inverse from `invert(diff)`, both sealed and checked).
- `services/blueprint/compiler/steps.py`: post-conditions use `quarantined` or `disabled` for removals and order checks only for touched entities and workflows (no change for an initial build).
- `services/blueprint/compiler/artifact.py`: `assemble` takes `kind` and `inverse`.
- `services/blueprint/compiler/__init__.py`: open question 12 updated.
- `services/blueprint/tests/compiler/test_cmp_incremental.py` (new): 18 tests.
- `docs/PLAN.md`: BPL-039 `doing`.

## What is built
- Forward artifact: `base` = base revision ref, `diffHash` = sha256 of the canonical bpdiff diff, steps from the diff; inverse: same rules on `invert(diff)`, base and target swapped, base components and base-state post-conditions.
- Non-rollbackable: steps whose inverse cannot restore the prior data get `reversible: false`, so `risk.irreversibleSteps > 0` and the adapter refuses rollback with `rollback_not_possible` / `irreversible_step` (contract 5.7, existing). Stable reason codes from `irreversible_reason(step)`, a pure function of the step: `type_change`, `link_target_change`, `precision_reduction`, `length_reduction`. No schema field was needed.
- Refusals: `CMP-INC-001` different Blueprint, `CMP-INC-002` engine target change, `CMP-INC-003` target revision not after base (equal only if identical), `CMP-ART-001` for diff ops no rule covers.

## Tests
- `services/blueprint/tests`: 2132 passed; `services/studio/tests`: 70 passed.
- New: schema and validator rules for forward and inverse (hash, id, every op once, base/target swap, diffHash), determinism (byte-identical), unchanged Blueprint gives empty steps, post-conditions and skippedOps, irreversible steps flagged (precision, type), fake adapter round trip (initial build, forward apply, rollback restores the base export hash and `site.applied`), fake refuses rollback of an irreversible artifact, each of option.add, option.reorder, field.reorder, role.upsert, report.disable compiles with a matching inverse.

## Decisions
- None needing an ADR: ADR-0058 already expected no contract change. Conservative readings (open points for the contract owner, Eldon):
  1. `*.set_property` and `settings.set` carry one property each and may share a pointer (extends compiler open question 2); a property stops at the first array, which is set whole.
  2. Changes inside a location compile to one `location.upsert` (9.3 names no `location.set_property`).
  3. Refused in slice 1: component `versionRange` changes, changes inside an option, reorders of unordered collections (no step kind, no skippedOps reason), whole child arrays added or removed (an entity's first relation), whole sections.
  4. `field.reorder` / `option.reorder` carry the full target and base key orders. Phase 6 (reorder) runs before phase 15 (quarantine), so in a change that both removes and reorders fields, `order` is not a permutation of the active keys at that moment; the fake's sort would fail on it. Contract 9.4 should say how an adapter treats keys missing from `order`.
  5. Inverse components are the base ranges resolved against today's registry, which can differ from what the base was compiled with.
  6. The inverse of a widening is a narrowing, so an inverse can have `irreversibleSteps > 0`; only the forward value gates rollback.

## Studio slice 2 needs
- Keep the Blueprint revision last applied (the base) next to `last_applied`; bump `meta.revision` on edit; compile with `base=` after the first apply.
- Rollback approvals add `gateApproved` when the inverse plan is gated (5.7); keep a history so `last_applied` moves back to the previous artifact.
- Show `irreversible_reason` per step and the refusal reason when `irreversibleSteps > 0`; keep the simulated compensation for the initial build.

## Tokens or cost
Unknown.

## Review follow-up notes (slice 1)
- The mapping is checked against both revisions, so a field removal that the mapping lists is refused for now (a later slice). A forward widening can have an inverse with irreversible steps. Relation `cardinality` and `kind` changes are not classified yet (UNVERIFIED, to confirm with the adapter owner).

## Next step
BPL-039 slice 2 (Studio real rollback); then close Q-61 and Q-76.

## Partner review fixes (review at 9d546ae6)
Each fix has a test in `services/blueprint/tests/compiler/test_cmp_incremental.py` that failed before the fix.
1. Field and option order: a reorder `order` now lists exactly the keys active when it runs (target order, then the removed keys still awaiting quarantine), forward and inverse; this supersedes point 4 of the rules above without a contract change. An added or restored element has no position in the step schema and every diff op is used exactly once, so no reorder step can be added without a diff reorder op. Where none exists, the compiler predicts the adapter's order (new element appended, one restored element back at its former index) and refuses with CMP-ART-001 when that misses the target: a prepend, a rename in the middle, or two removals (whose rollback cannot restore the order). Contract follow-up: give `*.add` a position, or allow a derived reorder step.
2. Precision changes are refused at compile time (CMP-ART-001, "precision change not yet supported by the adapter"). **Partner follow-up:** the engine backend applies precision wrongly (`frappe_backend.py` around line 643, partner lane); lift the refusal once the adapter supports it.
3. Secret-like keys in a property pointer (`/default/api_key`) are refused with CMP-ART-002 in the artifact check, so forward and inverse are both covered; `before` and `after` values were already scanned at any depth.
4. The fake adapter matches select options by `value` (lookup, execution, post-conditions).
5. The provenance skip is limited to the declared Blueprint provenance paths (component, entity, workflow, role, approval, report, integration, assistant).
6. No two steps share (kind, pointer): property changes on one subject coalesce into one step at their common property (entity labels: one `/labels` step); two different properties (`required` and `maxLength`) refuse with CMP-ART-001, because a step carries one `property`. `settings.set` is unchanged until BPL-037 settles it.
7. The round trip asserts the target state after the forward apply (field and option order, field properties, labels, locations) over nine edits on two base revisions. The contract's minimal example has no matching engine mapping, so it is not used.
