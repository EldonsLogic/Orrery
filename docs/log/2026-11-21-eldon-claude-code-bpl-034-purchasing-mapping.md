# Session log: bpl-034-purchasing-mapping

Date: 2026-11-21
Author: eldon
Tool and model: claude-code (Opus-class)
Plan IDs: BPL-034

## Summary
Added a draft purchasing and price-list mapping (supplier, price list and its lines, purchase order, receipt, supplier invoice, with roles and operations) as a second example over the trading fixture Blueprint, so the SEC-022 grant allowlist and BPL-027 test_03 have a reviewed contract to read. Mapping only; no ledger logic.

## Files touched
- contracts/examples/engine-mapping-purchasing.json: new draft mapping (all engine-side names UNVERIFIED, status draft, bench run none).
- contracts/engine-mapping.md, contracts/engine-mapping.schema.json: version 0.2.0 (minor, additive; schema structure unchanged), purchasing section, "Not covered yet" updated.
- services/blueprint/tests/test_engine_mapping.py: generic checks now run over every `engine-mapping-*.json`; purchasing tests for coverage, ledger effects, human floor, unmapped fields and line totals.
- docs/PLAN.md: BPL-034 row.

## Decisions
- Separate example file rather than growing the golden-path one; one entity is mapped in only one example (tested).
- Purchase receipt is `stock_and_gl`, not `stock`: the golden path sets perpetual inventory, the same reason the delivery note is `stock_and_gl`. UNVERIFIED until the bench run.
- Blueprint `price_list_item` (a child) maps to the engine's separate item price document as a master, since the engine has no price-list child table. UNVERIFIED.
- No new ADR: the schema structure is unchanged and ADR-0030 (Proposed) already plans per-path mappings ("They get their own mappings as the paths are agreed"). If the reviewer reads contracts/README.md rule 2 as needing one for a minor bump, add a short ADR that supersedes nothing and links this diff.

## Tokens or cost
Unknown.

## Next step
- contracts/README.md table still says engine-mapping 0.1.0 and lists only the golden-path example: update to 0.2.0 and add the purchasing example (outside this session's allowed paths).
- Partner lane: the adapter's entity table (`adapter/mapping.py`, PR #235) must add these entities from this contract before BPL-027 test_03 can apply live; bench-verify the names (ERP-021/ERP-022 style run).
