# Session log: manufacturing-blueprint

Date: 2026-11-27
Author: eldon
Tool and model: claude-code / opus-5.5
Plan IDs: BPL-054

## Summary
Blueprint 0.7.0 adds `modules.manufacturing` under ADR-0079 (Proposed): item, BOM, work order, job card, operation, workstation, routing and subcontracting concepts; operations, job cards, material transfer mode, batches from work order; warehouses as inventory touch points. No costing, valuation or posting field exists, and the rigid-zone boundaries are named in the contract doc. Stacked on bpl-053-boards-blueprint.

## Files touched
- contracts/blueprint.schema.json: 0.7.0; `manufacturingModule`; one x-validator-rule (warehouse kinds, stock-class transitions, human floor, rigid zone).
- contracts/blueprint-modules.md: manufacturing section, metrics, changelog; contracts/README.md: version.
- contracts/examples/blueprint-modules-minimal.json: two warehouses, item and eight manufacturing entities, a production dashboard, `modules.manufacturing`.
- contracts/examples/invalid/blueprint-modules-manufacturing-cases.json: 13 negative cases (including valuation, cost-basis and account keys refused).
- docs/open-questions.md (Q-702), docs/PLAN.md (BPL-054 doing), docs/CHANGELOG.md.

## Checks
- BOM, Work Order, Job Card, Routing, Operation, Workstation, Subcontracting Order and Receipt, and Manufacturing Settings (backflush basis), read from the pinned ERPNext v15.124.5 source; UNVERIFIED until a bench run.
- No bpdiff change: the module adds no keyed array.

## Decisions
- None new; Q-702 asks the partner to confirm that cost and backflush basis stay component defaults.

## Tokens or cost
Unknown.

## Next step
BPL-055 (marketing, 0.8.0) stacked on this branch.

## Review fixes (#397 RULES 42 review at 9a8661f2)
- Merged bpl-053-boards-blueprint (its #395 and #396 fixes) first; conflicts in the changelog, x-validator-rules and Q-700 to Q-702 rows resolved by keeping both sides.
- M1: `BP-MOD-001` already covers every module-bound entity; tests added for item, bom, work order, job card, workstation and subcontracting fields (valuation_rate, rm_cost_as_per, operating_cost, hour_rate, standardRate, backflush settings); `backflush` joins `x-rigid-zone-terms`.
- M2: warehouse-to-account link stays with the certified component (schema text and blueprint-modules.md); validator `BP-MOD-004`: WIP, finished goods and scrap are warehouse locations and three different ones.
- L3: denylist widened in #395. L4: role changes `access` (from #395); bpdiff classes `modules/manufacturing/warehouses` (and its parents) `compliance`, the strictest non-structural class; README rule 2; tests.
- Open question: Q-702 extended to the bound-entity gap.
