# Session log: erp-016-review-round-5

Date: 2026-11-21
Author: partner
Tool and model: claude-code / Opus 5.5
Plan IDs: ERP-016

## Summary
Round 5 on PR 204 (head f8feffe before) answers the cross-model re-review of f8feffe. The branded documents now follow the pinned engine's discount semantics. A line that omits its `discount` key still prints its allocation. A "Grand Total" (VAT-inclusive) discount now prints instead of being refused, and so does a "Net Total" one. A per-unit item discount is no longer subtracted twice. In ZATCA tax invoice mode an allocated invoice discount is also shown on a labelled informational row, and Q-520 asks a compliance reviewer to confirm that layout. Tests came first: 66 failures and 28 errors before the fix; all 150 ERP-016 tests pass after. Compare and refuse only: no printed amount is replaced.

## Engine semantics modelled (source)
ERPNext `erpnext/controllers/taxes_and_totals.py` at e5cde8c4b9e3f7f567a92ca3e65fd411402b89ce. That is the repo's pin: ERPNext v15.124.5 per `apps/engine/README.md`, `docs/architecture/engine-version-policy.md` and `infra/dev/docker/README.md`. Source: https://github.com/frappe/erpnext/blob/e5cde8c4b9e3f7f567a92ca3e65fd411402b89ce/erpnext/controllers/taxes_and_totals.py, accessed 2026-11-21. Line numbers below are from that file. The re-review's ~838-918 range points at the same functions a few lines off.
- L193-268 `calculate_item_values`. The item `discount_amount` is per unit (`price_list_rate - rate`, or `rate_with_margin - rate`; L216 leaves it unrounded). `rate` is already net of it, and `amount = rate x qty` (L261). `net_amount` starts as `amount`.
- L858-865 `set_discount_amount`. `discount_amount = additional_discount_percentage` of the pre-discount total that `apply_discount_on` names (`grand_total` or `net_total`).
- L903-959 `apply_discount_amount`. A discount without `apply_discount_on` is refused (L906). Each line gets `distributed_discount_amount = discount_amount x net_amount / total_for_discount_amount`, and its `net_amount` is reduced by that, with a rounding carry so the net total is exact. The taxes are then recomputed on the discounted nets.
- L961-1002 `get_total_for_discount_amount`. "Net Total" spreads over the net total. "Grand Total" spreads over the grand total less actual-amount taxes, so the discount includes VAT: on 200.00 + 15%, 10% gives 23.00, of which 20.00 is on the line and 3.00 is VAT no longer charged.
- L771-785 `calculate_totals`: grand total = net total + taxes. L86-90 and L913-915: a cash or non-trade discount comes off the grand total only and is not spread onto the lines.

## Files touched
- `apps/engine/change_engine/change_engine/print_formats/document_reconciliation.py`
  - `apply_discount_on` ("Grand Total" or "Net Total", top level or totals, both must agree) is required with a document discount.
  - Grand Total: the line amounts must equal taxable, with no remainder, and the allocations must equal discount x lines-before-discount / (grand total + discount), within one minor unit.
  - Net Total: the round-4 check, unchanged.
  - `additional_discount_percentage` is now accepted. It must give the discount from that same total, within one minor unit.
  - `is_cash_or_non_trade_discount` is refused.
  - Taxable + VAT = grand is checked. On tax invoices that check stays with ERP-007's validator so its error type is unchanged.
  - The snapshot always writes the line `discount` as line discount + allocation.
  - `CheckedAmounts.allocated` is new.
- `.../print_formats/branded_documents.py`: in `zatca_sa` mode, an allocated discount adds an informational totals row (not subtracted).
- `.../print_formats/document_labels.py`: new `invoice_discount_included` label. Its Arabic is unreviewed (ADR-0033).
- `.../print_formats/bilingual_tax_invoice.py`:
  - `prepare_tax_invoice_view` gets an optional `included_discount_row` (totals rows only).
  - `sales_invoice_to_zatca_dict` prints the posted rate with line `discount` "0.00", because the item discount is already in the rate.
  - The adapter passes `apply_discount_on` (and a cash-discount flag) beside `discount_amount`.
  - The `show_hijri` block is untouched.
- `.../tests/test_erp_016_branded_templates.py`: four new classes that parse the printed HTML and sum it. Round-4 helpers set `apply_discount_on: "Net Total"`. The `additional_discount_percentage` refusal case is removed, because it is now supported and checked.
- `docs/open-questions.md`: Q-520.

## Before and after (f8feffe, then this round)
1. Omitted `discount` key, allocation 20.00. Before: printed `2 x 100.00 - 0.00 = 180.00`. After: `2 x 100.00 - 20.00 = 180.00`, plus the info row 20.00.
2. Grand Total 10% (23.00, allocation 20.00, 180.00 / 27.00 / 207.00). Before: refused ("... 3.00 = 177.00 != 180.00"). After: prints 180.00 / 27.00 / 207.00 in ERP-007 and both branded modes. The Net Total variant (20.00) matches.
3. Per-unit item discount (qty 2, list 100.00, rate 90.00, item discount 10.00, allocation 18.00, net 162.00) through the real adapter. Before: refused (expected 152.00). After: `2 x 90.00 - 18.00 = 162.00`, with 162.00 / 24.30 / 186.30 in all four renders.
4. ZATCA mode, allocated discount. Before: shown in the line column only. After: also on "Invoice discount (included in line amounts)", and the printed sums still hold.

## Decisions
- Item discount mapping: print the posted `rate` with no separate line discount. It is the ZATCA item net price (BT-146, the price after the item price discount), and the line net amount is quantity x net price less line allowances (here, the allocation). The other option, `price_list_rate` with `discount_amount x qty`, was rejected: the engine leaves `discount_amount` unrounded (L216) and adds margins (`rate_with_margin`), so that pair need not add up on the currency grid. Whether the gross price (BT-148) and price discount (BT-147) must also be printed is part of Q-520.
- `apply_discount_on` is required rather than defaulted, because the engine itself refuses a discount without it. Defaulting to either value would refuse valid data of the other kind with a misleading message.
- The info row shows the allocated part (20.00), not the VAT-inclusive engine discount (23.00). Only the allocated part is "included in line amounts". It appears in ZATCA mode for standard and simplified invoices, because the cited §§7.6 and 8.2 cover both.
- One-minor-unit tolerance on the Grand Total quotient and the percentage. It is deterministic: the engine rounds the recomputed tax per row, so grand total + discount can differ from its pre-discount grand total by a cent. The posted amounts are only compared, never replaced.

## Checks
- ERP-016: 150 passed.
- ERP-007: 14 passed, 1 skipped (as before).
- ERP-007 undiscounted output: byte-identical to origin/main for all 11 renders in its suite (hash comparison, scratch script outside the repo).
- ZATCA Phase 1: engine 3 passed; component discover OK.
- pytest `scripts/tests`: 22 passed.
- `check_docs`: 0 errors, 0 warnings. `check_repo_hygiene`: OK. `scan_secrets`: 0 hits. `check_plan_independence`: OK. `check_lanes --actor partner`: OK.

## Not done
- ERP-007's own line rows still print the line `discount` key, not the allocation. With an allocated discount the ERP-007 line reads `2 x 100.00 - 0.00 = 180.00`; the totals are right. Its line code is outside this round's allowed paths. Follow-up: widen ERP-030 (ERP-007 renderer cleanup) to cover it, or add a row. `docs/PLAN.md` was not edited this round; ERP-030 currently says document discounts are done in ERP-016.
- The ZATCA layout is UNVERIFIED (Q-520). Arabic labels are unreviewed (ADR-0033), so the documents stay unwired to customers.

## Tokens or cost
Unknown.

## Next step
Cross-model re-review of this round on PR 204 (ERP-016). Compliance reviewer on Q-520.
