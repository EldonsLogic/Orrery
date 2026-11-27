# Session log: bpl-045-review-fixes

Date: 2026-11-27
Author: eldon
Tool and model: claude-code (Claude Opus 5.5, worker subagent)
Plan IDs: BPL-045

## Summary
Fixed the partner review of #348 at 0fb152e4 in Eldon's lane: a re-add after a quarantine now reaches the target order, engine-adapter contract bumped to 0.2.0 (minor) for the new MUST with ADP-C-072, options keyed by `value` stated in the contract, option order post-conditions, a schema rule for the inverse `artifactSchema`, and a test for the order refusal. Merged origin/main first (PLAN.md and decisions INDEX conflicts).

## Files touched
- services/blueprint/compiler/incremental.py: `_reaches` treats every forward add as a possible restore, so an add to a kept field or option list carries a derived reorder in both directions (High 1).
- services/blueprint/compiler/steps.py: `order_equals` on every option list an option step touches, keyed by `value` (Low 6).
- contracts/compiled-artifact.schema.json: allOf rules so an embedded inverse has the forward's `artifactSchema` (Low 5).
- contracts/engine-adapter.md, contracts/README.md: 0.2.0 (minor, replaces the unreleased 0.1.4 draft); element keys (options by `value`) in 9.3; the active-key MUST gated on speaking 0.2 (9.4, 4.3); ADP-C-072; changelog (Medium 4, Medium 3).
- services/blueprint/adapter/fake.py: speaks contract 0.1.3 and 0.2.0.
- services/blueprint/tests/adapter/test_adp_plan_preview.py: ADP-C-072. test_adp_envelope.py: ADP-C-004 uses 0.9.0 as the unsupported minor, since 0.2 is now supported.
- services/blueprint/tests/compiler/test_cmp_derived_reorder.py: re-add after quarantine, add/rollback/re-add, option order after apply and rollback, option post-condition, inverse schema mismatch, the refusal with no reorder or membership op (Low 7).
- docs/decisions/ADR-0072-derived-reorder-step.md (Proposed): points 5, 7, 8 amended, point 9 added, alternatives and consequences (BPL-050 handoff, 0.2.0 cost).

## Decisions
- ADR-0072 point 5 amended: every add to a kept ordered list carries a derived reorder, because the compiler cannot see whether the site holds the element quarantined. Rejected: changing the restore rule to append (moves the problem to rollback and changes the partner adapter and ADP-C-049).
- Cost accepted: field and option adds to existing entities become 0.2.0, so the real adapter refuses them until BPL-050 (fail closed instead of a silent wrong order).

## Tokens or cost
Unknown.

## Next step
Partner re-review of #348; BPL-050 (partner, #387) implements the adapter side against contract 0.2.0 and ADP-C-072.

## RULES 42 review fixes (M1, M2, L3 to L6)
- M1: ADR-0072 point 5 and the engine-adapter 0.2.0 changelog say option steps carry `order_equals` even in 0.1.0 artifacts (postConditions, contentHash, artifactId change; "byte for byte" covers steps only).
- M2: engine-adapter.md 4.3 and ADP-C-072 require refusing a mixed contract minor and artifact schema minor. Fake refuses it (`_prechecks`); testkit states 0.2.0 for 0.2.0 artifacts. Test first in ADP-C-072. Note: this refuses 0.2.x requests with 0.1.0 artifacts too.
- L3: `_derived_issues` requires an inverse derived reorder at the same pointer and add or remove kinds in `derivedFrom`. Tests first.
- L4: comment in fake.py `_evaluate` on why dropping the trial is safe. L5: `uniqueItems` on `order` and `previousOrder` (test). L6: compiler `__init__` docstring versions.
- BPL-050 acceptance items added to the PR comment.
