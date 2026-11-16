# Session log: adr-0034-reviewed-reviewer

Date: 2026-11-15
Author: eldon
Tool and model: claude-code / sonnet-5.5
Plan IDs: BPL-014

## Summary
Q-19 first step: a component at `reviewed` or above must name a reviewer in `reviewedBy`, and a ledger or tax component may wait for review at `tested` (proposed in ADR-0034). BPL-014 stays doing: the test harness part is not started.

## Files touched
- contracts/component.manifest.schema.json: `reviewedBy` (min 1) required from `reviewed`; ledger or tax floor is now `tested`
- services/blueprint/tests/registry/test_registry_admission.py: two new tests (419 Blueprint tests pass)
- docs/decisions/ADR-0034-reviewed-level-needs-a-named-reviewer.md and INDEX.md: new, Proposed
- docs/architecture/component-library.md: certification note updated
- docs/PLAN.md, docs/STATUS.md: BPL-014 set to doing

## Decisions
- ADR-0034 (Proposed). Contract change: needs the partner's recorded review and a security review.

## Tokens or cost
Not measured.

## Next step
Partner reviews ADR-0034. Then move the #43 manifest from `reviewed` to `tested` (partner lane) and add the author-not-reviewer check. BPL-014 remainder: the certification test harness.
