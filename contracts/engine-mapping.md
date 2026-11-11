# Blueprint-to-engine mapping contract

Status: draft
Owner: eldon
Version: 0.1.0

The contract that says how a Blueprint becomes documents, fields, roles and actions in the pinned engine. It is the interface between the Blueprint side (this lane) and the real-engine proof (ERP-021, ERP-022). Schema: [engine-mapping.schema.json](engine-mapping.schema.json). Example: [examples/engine-mapping-golden-path.json](examples/engine-mapping-golden-path.json). Decision: ADR-0030 (Proposed). Scenario it serves: [../docs/specs/golden-path-trading-sale.md](../docs/specs/golden-path-trading-sale.md).

## What a mapping contains
- **Entities and fields:** each Blueprint entity maps to one engine document type with a kind (master, document, child), whether it is submittable, and what posting it causes (`none`, `stock`, `gl`, `stock_and_gl`). Each field maps to an engine field and type; a link names the engine document it links to; a value that lives on another engine document (for example a selling price on a price row) uses `via`.
- **Computed fields:** the engine is the authority. A computed field states its inputs, the aggregation over child lines, the rounding and what triggers recalculation, so a total can be traced to its lines. The platform never recomputes it; the expressions only document the contract and check golden numbers in tests.
- **Roles:** each Blueprint role maps to a role the adapter creates and owns (never a built-in engine role). A grant lists actions per entity and may mask fields (for example item cost hidden from sales). Grants may not exceed what the Blueprint role allows.
- **Operations:** each action the golden path needs (create, submit, make a delivery from an order, make an invoice from a delivery, post) names the engine's supported document operation, the idempotency key parts, preconditions, and whether the human floor applies (ADR-0027). No operation writes ledger entries directly.

## Rules
1. A mapping starts as `draft` and becomes `verified` only after a recorded bench run on the pinned engine passes the real-adapter checks (ERP-021, ERP-022). Until then every engine-side name is UNVERIFIED.
2. Every mapped entity, field, type and role must exist in the Blueprint file named in `blueprintRef`; `services/blueprint/tests/test_engine_mapping.py` checks this in CI.
3. A submit that causes a ledger effect carries `humanFloor: true`.
4. The mapping never names the engine product; engine names are document and field names only.
5. Changes to a verified mapping need a new version and a bench run. Version numbers follow [README.md](README.md) rule 1.

## Not covered yet
Payments, purchasing, returns, tax, price lists beyond the item price, connectors and country packs. They get their own mappings as the paths are agreed.
