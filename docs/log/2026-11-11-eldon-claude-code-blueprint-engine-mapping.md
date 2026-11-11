# Session log: blueprint-engine-mapping

Date: 2026-11-11
Author: eldon
Tool and model: claude-code / sonnet-5.5
Plan IDs: BPL-029

## Summary
Drafted the Blueprint-to-engine mapping contract (schema, golden path example, tests) so the partner's real-engine proof can build against an agreed interface.

## Files touched
- contracts/engine-mapping.schema.json, contracts/engine-mapping.md, contracts/examples/engine-mapping-golden-path.json: draft contract 0.1.0 and the golden path mapping (customer, item with price, sales order, delivery, sales invoice; roles with field masks; six operations)
- services/blueprint/tests/test_engine_mapping.py: 14 checks (schema, Blueprint consistency, role grants, human floor on ledger effects, computed formulas reproduce 150.00 and 135.00)
- docs/decisions/ADR-0030 and INDEX.md: Proposed
- contracts/README.md, docs/PLAN.md: table row, BPL-029 now doing

## Decisions
- ADR-0030 (Proposed, approval pending).

## Tokens or cost
Not measured.

## Next step
Partner confirms the engine-side names and field masks on the bench (ERP-021, ERP-022) and the mapping moves from draft to verified. Every engine-side name is UNVERIFIED. Not covered: payments, purchasing, tax, returns. Verified here: schema and the full Blueprint test suite pass locally (417 tests).
