# Session log: bpl-035-golden-path-mapping-gaps

Date: 2026-11-21
Author: eldon
Tool and model: claude-code
Plan IDs: BPL-035

## Summary
Brought the golden-path engine mapping example (0.1.0 to 0.2.0) up to the purchasing example's rules: 36 unmapped fields listed with reasons, `sales_invoice.outstanding_amount` (and `paid_amount`) moved to unmapped until payments are mapped, and a bench check for the discount path (rate versus price_list_rate) noted on both `unit_price` fields. No engine field names changed.

## Files touched
- contracts/examples/engine-mapping-golden-path.json: unmapped list, version, notes, outstanding_amount unmapped
- docs/PLAN.md: BPL-035 row
- docs/decisions/ADR-0056-golden-path-mapping-gaps.md and INDEX.md: decision record
- test_engine_mapping.py deliberately not edited (BPL-034 edits it). The two BPL-034 checks (unmapped completeness; Blueprint-computed fields carry engine authority) were run against this example with a scratch script outside the repo and pass. Once BPL-034 merges, widen those two tests from PURCHASING to every example (one-line change).

## Decisions
- ADR-0056 (Proposed).

## Tokens or cost
Small.

## Next step
After BPL-034 merges, widen its two tests to all examples. ERP-022 bench: record the discount-path result (BPL-035).
