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

## Review fixes (partner review on #391 at 4fb365aa, verdict CHANGES: 1 High, 3 Medium, 2 Low)
- Merged origin/main (bfeecea3). The only conflict was the Q-691 row: kept main's text and added the ADR-0075 and BPL-051 link. Low 6: the row now says the inverse is a reverse-edge sort with pointer ties.
- High: relations are soft edges, kept in pointer order unless they close a cycle, and never split or refuse anything. Hard edges are `link` fields only. Tests: `sales_quote` with its child relation plus a Link back from `sales_quote_line` compiles; `price_list_item` linking `price_list` compiles. With the built-in list switched off, the golden hash stays `sha256:028eba82...` (the 4fb365aa value, pinned by a test).
- Medium 2: no compiler-side source lists every built-in type, because one compile gets one engine mapping and each mapping covers only part of them. Added `contracts/engine-builtin-entities.json` 0.1.0, copied from the adapter's `ENTITY_TO_DOCTYPE` (main at 1f029d18, read only). A link into a listed entity adds no edge. A test checks that the list covers both example mappings. Q-722 asks the partner to own the list or expose it. Tests: `customer` and a new `segment` linking each other compile; `item` and `sales_quote_line` compile (the old refusal test was changed).
- Medium 3: a hard cycle is split. While one remains, the cycle's Link field with the smallest pointer moves to a phase 5 `field.add`, plus a phase 6 `field.reorder` when appending it breaks the Blueprint field order. The new steps repeat the `entity.add`'s `sourceOps`. The split always succeeds, so `CMP-ART-007` is removed (none is left for any case). Restores and quarantines are still broken by pointer. The fake adapter's plan now judges each step against the site as the earlier steps leave it (contract 5.3, 0.1.4). Without that, the split `field.add` was blocked as `subject_missing` at plan time, and the new test failed that way first. Test: an initial compile with no base and a cycle succeeds, applies on the fake, passes every post-condition, and keeps the field order. The incremental cycle test now expects the split. Real adapter: `engine.py` `_judge` still judges against the live site, so it refuses a split cycle as `subject_missing` (fail closed). That is asked in Q-722; `apps/engine` was not edited.
- Medium 4: engine adapter contract 0.1.4 with a Changes entry (5.3, 9.3, 9.4). `artifactSchema` stays 0.1.0, and the schema `x-validator-rules` text is aligned (sourceOps exception, order wording). The README table now says 0.1.4 (it said 0.1.2) and lists the new file. The fake's `CONTRACT_VERSIONS` is 0.1.4. ADR-0075 was rewritten in place (unmerged); the false sentence "only reorders steps the engine could not apply before" is gone.
- Low 5: tests for a relation-induced cycle (the Link wins, nothing is split), a relations-only cycle, a built-in cycle (`customer` and `item` with mutual Links compile in pointer order), and one split per cycle by smallest pointer (the bridge case).
- Golden hash: `sha256:028eba82...` became `sha256:e211deb7...`. Links into built-in types no longer add order, so for example `delivery_note` now sorts before `sales_order` by pointer. The same 24 phase 4 steps move. The expected file was reordered by a separate script written from the rule (no compiler import); its order matched the compiler's. The snapshot was regenerated with `UPDATE_SNAPSHOTS=1`. Adapter golden export hashes are unchanged.
- Checks: services/blueprint 2456 passed; studio 70; control-plane 491; operate 733 (1 skipped); operate memory 99; contracts/tests 61; engine BPL-008, BPL-012, BPL-027 and BPL-031 tests 66 passed, 10 skipped (run only). check_contracts, check_docs, check_plan_independence, check_repo_hygiene and check_lanes OK.
