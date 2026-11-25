# Session log: bpl-032-purchasing-doctypes

Date: 2026-11-22
Author: partner
Tool and model: claude-code (Claude Sonnet 5.5)
Plan IDs: BPL-032

## Summary
After BPL-034 (PR #247, contract 0.2.0) the adapter maps the nine purchasing and price-list entities, so role grants on them plan and apply instead of being refused as unmapped built-ins; built-ins outside the mapping are still refused. BPL-032 stays `doing` (live-bench confirmation is open).

## Files touched
- apps/engine/change_engine/change_engine/adapter/mapping.py: nine pairs added to `ENTITY_TO_DOCTYPE`: supplier=Supplier, price_list=Price List, price_list_item=Item Price, purchase_order=Purchase Order, purchase_order_line=Purchase Order Item, purchase_receipt=Purchase Receipt, purchase_receipt_line=Purchase Receipt Item, purchase_invoice=Purchase Invoice, purchase_invoice_line=Purchase Invoice Item. All nine names equal `contracts/examples/engine-mapping-purchasing.json` (no difference found). No other adapter code changed: the grant allowlist, `can_grant_own_doctype` and `_grant_doctype` in `engine.py` and `frappe_backend.py` read `ENTITY_TO_DOCTYPE`, and no separate list of unmapped built-ins exists. `_judge` in `engine.py` is untouched (PR #280).
- apps/engine/change_engine/change_engine/tests/test_bpl_032_purchasing_mapping.py: new offline tests (pairs equal the contract file, reviewed and not protected, `grant_plan_reason`, apply on the simulated engine incl. submit only on submittable documents and a missing table failing closed, plan on the in-memory and the offline engine adapters, a still-unmapped built-in blocked). Written first: 12 of 14 failed before the mapping change.
- apps/engine/change_engine/change_engine/tests/test_bpl_027_fixture_real_adapter.py: removed the `BPL027_PURCHASING_MAPPED` gating, `UNMAPPED_BUILTIN_ENTITIES`, `without_unmapped_builtin_grants` and `test_03b`; `test_02` and `test_03` now run whenever a bench exists; `test_01b` now asserts that the full fixture plans (gated, none blocked) and that a role granting Payment Entry (still unmapped) is blocked with `protected_subject`; offline `test_06c` and `test_06d` updated the same way. Bench tests still skip without a bench.
- apps/engine/change_engine/change_engine/tests/test_sec_022_bpl_032_roles.py and test_sec_022_review_followups_2.py: three existing tests used `supplier` and `price_list` as their example of an unmapped built-in; they now use `stock_entry`, `payment_entry` and `data_import`. This is outside the brief's path list but is forced by the mapping change; the assertions are unchanged.
- .github/workflows/tests.yml: the new module added to the SEC-022 and BPL-032 step.

## Decisions
- None new. Follows ADR-0055 (purchasing engine mapping) and ADR-0051 item 3 (grant allowlist = reviewed mapping).

## Tokens or cost
Not measured.

## Next step
BPL-032: run the BPL-027 bench tests (README, section "BPL-027 integration test") to confirm the engine-side names on a real site (Item Price, the three item child tables and the purchase documents' submit and permission behaviour are UNVERIFIED); then close the row.
