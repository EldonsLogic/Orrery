# ADR-0055: Purchasing and price-list engine mapping

Status: Proposed
Owner: eldon
Approved by: pending (partner review; the partner confirms the engine-side names on the bench)

## Context
The trading fixture Blueprint's roles grant supplier, price list and purchase documents, but the engine-mapping contract (ADR-0030, version 0.1.0) covered only the sales golden path. The SEC-022 adapter allowlist (PR #235) grants roles only on entities the contract maps, so BPL-027 `test_03` cannot apply the fixture to a real engine. Contract changes need an ADR ([../../contracts/README.md](../../contracts/README.md) rule 2).

## Decision
- Bump the engine-mapping contract to 0.2.0 (additive; the schema structure does not change). Add a separate example, `contracts/examples/engine-mapping-purchasing.json`, over the same fixture Blueprint: supplier, price list, price-list line, purchase order, purchase receipt and purchase invoice, each with its lines where the engine has them (plan row BPL-034).
- Ledger effects: purchase order `none`; purchase receipt `stock_and_gl` (the golden path uses perpetual inventory, as the delivery note does); purchase invoice `gl`. Every submit with a ledger effect carries `humanFloor: true` (ADR-0027).
- A price-list line maps to a master document (the engine stores item prices as separate documents, not a child table).
- Role grants copy the fixture Blueprint exactly; fields with no engine counterpart are listed as unmapped with a reason.
- The mapping stays `draft` and every engine-side name is UNVERIFIED until a recorded bench run. The adapter allowlist (`mapping.py`, partner lane) is updated separately to read these entities.

## Alternatives rejected
- Hold #235 until purchasing was proven on the bench: blocks the security fix on scope that was never part of it.
- Extend the golden-path example in place: mixes a verified-path candidate with an unproven one and makes the sales example harder to review.
- Let the adapter allow built-in purchase documents without a contract mapping: breaks the rule that the allowlist follows reviewed mappings.

## Consequences
- After the partner adds these entities to the adapter allowlist, BPL-027 `test_03` can be unflagged.
- Payments, returns, tax and country packs still need their own mappings.

## Supersedes
None.
