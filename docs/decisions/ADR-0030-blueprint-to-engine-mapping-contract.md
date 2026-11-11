# ADR-0030: Blueprint-to-engine mapping contract

Status: Proposed
Owner: eldon
Approved by: pending (partner review; the partner confirms the engine-side names on the bench)

## Context
Phase 0 and Phase 1A need one agreed way to say how a Blueprint becomes documents, fields, roles and actions in the pinned engine, tested with the real adapter and not only a fake ([../architecture/phased-delivery-and-lanes.md](../architecture/phased-delivery-and-lanes.md), [../specs/golden-path-trading-sale.md](../specs/golden-path-trading-sale.md)). The partner asked for an explicit, versioned mapping and a contract for computed fields and child-line dependencies. Contract changes need an ADR ([../../contracts/README.md](../../contracts/README.md) rule 2).

## Decision
- Add a draft contract, `contracts/engine-mapping.schema.json` (version 0.1.0), with the example `contracts/examples/engine-mapping-golden-path.json` for the golden path (customer, item with price, sales order, delivery, sales invoice).
- The Blueprint side owns the schema and the fixtures (BPL-029, an interface row at gate G0). The engine side proves it on the bench (ERP-021, ERP-022): names, types, roles and operations are UNVERIFIED until then, and a mapping is `verified` only after a recorded bench run.
- The engine stays the authority for computed values. The contract records inputs, aggregation over lines, rounding and recalculation triggers so a total can be traced; the platform never recomputes it.
- Roles map to adapter-owned roles with field masks; grants never exceed the Blueprint role. Operations carry idempotency key parts, preconditions and the human floor flag (ADR-0027, ADR-0028).
- CI checks the mapping against the fixture Blueprint and the golden numbers.

## Alternatives rejected
- Leave the mapping inside adapter code: hides the interface, so neither side can review or test it independently.
- Make the platform recompute totals to check the engine: a second calculation authority (RULES 21).

## Consequences
- ERP-021 and ERP-022 build against this interface; BPL-030 uses it for builder reproduction.
- More paths (payments, purchasing, tax) get their own mappings later; the schema may change while the major version is 0.

## Supersedes
None.
