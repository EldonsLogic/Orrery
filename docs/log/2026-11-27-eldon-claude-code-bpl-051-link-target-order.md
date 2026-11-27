# Session log: bpl-051-link-target-order

Date: 2026-11-27
Author: eldon
Tool and model: claude-code / opus-5.5
Plan IDs: BPL-051

## Summary
The compiler now adds entities in Link-target order inside phase 4, and quarantines dependants first inside phase 16. This fixes the #381 real-bench failure at step 57, where `sales_order` was added before the `sales_quote` it links to (Q-691, answered by Eldon on #389). A Link cycle among new entities is refused with `CMP-ART-007`.

## Files touched
- services/blueprint/compiler/steps.py: `link_targets`, `order_by_links` (Kahn's algorithm, smallest ready pointer first, cycle members reported), applied after the 9.4 sort in the initial build.
- services/blueprint/compiler/incremental.py: the same reorder for incremental forward and inverse steps.
- services/blueprint/compiler/__init__.py, services/blueprint/README.md: open question 5 note; `CMP-ART-007` documented.
- services/blueprint/tests/compiler/test_cmp_link_order.py: new tests (unit order, ties, self-link, outside links, quarantine order, cycle refusal, fixture order with plan view, incremental forward and inverse, no-Link regression).
- services/blueprint/tests/compiler/test_cmp_golden.py: the ordering check excludes phase 4 from the pointer sort.
- services/blueprint/tests/compiler/fixtures/trading-distribution.expected-artifact.json: phase 4 lines reordered by a separate script written from the rule (not importing the compiler); steps matched, then the new hash recorded (`sha256:e61c1586...` became `sha256:028eba82...`).
- services/blueprint/tests/compiler_snapshots/snapshots/valid--trading-distribution.sandbox.json: regenerated with `UPDATE_SNAPSHOTS=1` (generated; same 24 phase 4 steps in a new order).
- contracts/engine-adapter.md 9.4, contracts/compiled-artifact.schema.json: order text (contract version unchanged).
- docs/decisions/ADR-0075-compiler-link-target-order.md and INDEX.md; docs/open-questions.md Q-691 resolved; docs/PLAN.md BPL-051.

## Decisions
- [ADR-0075](../decisions/ADR-0075-compiler-link-target-order.md). A Link is any field or relation with a `target`, as the adapter reads it. A quarantine cycle is broken by pointer, not refused (quarantine keeps the storage). ADR-0074 was taken by open PR #388.

## Checks
services/blueprint 2442 passed; control-plane 472; operate 733 (1 skipped); operate memory 99; studio 70; contracts/tests 56; engine BPL-008 and BPL-027 fixture tests 15 passed, 10 skipped (run only, partner lane not edited). check_contracts, check_docs, check_plan_independence, check_repo_hygiene OK.

## Tokens or cost
Unknown.

## Next step
Partner: rerun the #381 bench (BPL-046) on this compiler; the adapter refusal for a missing Link target stays with BPL-033. Set BPL-051 done when merged.

## Review fixes (RULES 42 review on #391, verdict CHANGES)
- Medium: an inverse (`restores=True`) now breaks an `entity.add` cycle by pointer instead of refusing, so removing a Link cycle in one revision compiles. Reason: a restore re-activates a stored entity (fake adapter reinserts the retained definition; real adapter keeps the custom type and only unhides a built-in type's fields), so its Link targets already exist; read from `apps/engine` (not edited). A forward add cycle still refuses `CMP-ART-007`. Test: rev 1 adds A and B, rev 2 adds A->B and B->A as `field.add`, rev 3 removes both; compile, apply and rollback on the fake adapter restore the rev 2 export hash. Failed first with `CMP-ART-007` on the restore side, as the review said.
- Low 1: `CMP-ART-007` names only entities on a cycle (strongly connected components of more than one entity); test with an entity bridging two cycles.
- Low 2: `link_targets` counts only fields of type `link` and every relation kind; test with a non-link field carrying `target`.
- ADR-0075 and contract 9.4 reworded to match. Golden hashes and snapshots unchanged (the fixture has no restore cycle and no non-link `target`).
- Checks: services/blueprint 2447 passed; studio 70; control-plane 472; operate 832 (1 skipped); contracts/tests 56; check_contracts, check_docs, check_repo_hygiene OK.
