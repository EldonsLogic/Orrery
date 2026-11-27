# Session log: crm-blueprint-review-fixes

Date: 2026-11-27
Author: eldon
Tool and model: claude-code / opus-5.5
Plan IDs: BPL-052,BPL-060,BPL-061,BPL-062

## Summary
Fixed the partner's #395 review at 187d948e (3 Medium, 5 Low) on the BPL-052 CRM Blueprint contract: shared-concept rule, destructive bpdiff rules for CRM changes, owed work as blocked G2 plan rows, and a test pinning the compiler's refusal of `modules`.

## Files touched
- contracts/blueprint.schema.json: `x-module-shared-concepts` (crm.customer, crm.campaign), `modules` minProperties 1, Modules rule says which component implements a concept and that two concepts never share an entity; CRM description names framework records.
- contracts/blueprint-modules.md: "Implemented by" column, won and lost through the engine flows (Quotation, Replied mapped to no stage, Closed excluded; UNVERIFIED), framework records wording.
- contracts/tests/test_blueprint_modules.py, contracts/examples/invalid/blueprint-modules-crm-cases.json: shared-concept, one-entity-per-concept and empty-modules tests.
- services/blueprint/diff/bpdiff/classify.py, diff/README.md rule 6, tests/diff/test_bpdiff_classify.py: removing a stage, lead source or lost reason, rebinding or removing a concept binding, changing a stage kind and swapping the module component are `destructive`.
- services/blueprint/tests/compiler/test_cmp_modules_refused.py: initial, added and changed `modules` give CMP-ART-001.
- services/blueprint/README.md: step 2 wording.
- docs/PLAN.md: BPL-060 (validator), BPL-061 (compiler), BPL-062 (mapping contract), all eldon G2 blocked; BPL-056 lists the partner-lane scope from the review; BPL-052 notes GOV-078 is still doing.
- docs/decisions/ADR-0079 (Proposed): shared concepts, owed rows, "one key" holds once BPL-060 to BPL-062 land.
- docs/open-questions.md: Q-700 and Q-701 updated.

## Decisions
- BPL-056 does not list BPL-060 to BPL-062 in Depends: `check_plan_independence.py` (ADR-0025) refuses any same-gate dependency on the other founder's row, in both directions. The row text says it is not certified before them.

## Tokens or cost
Unknown.

## Next step
Partner re-review of #395; then the #396 review fixes and merge up through #397 and #398.
