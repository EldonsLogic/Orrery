# Session log: erp-011-review-fixes

Date: 2026-11-19
Author: partner
Tool and model: antigravity / gemini-4-neon
Plan IDs: ERP-011, ERP-028

## Summary
Completed an independent cross-model review of PR #192 (`e268793`, authored by codex / gpt-6.1-sol) against Frappe 15.126.0 / ERPNext 15.124.5 source and fixed three fail-closed field-permission gaps (Sales Team child fields, Pricing Rule Item Code child field on insert, and Selling Settings default price-list field).

## Files touched
- `components/sales/trading/trading.py`: added child-field permlevel checks in `set_sales_team` (`Sales Team`: `sales_person`, `allocated_percentage`, `commission_rate`), child-field permlevel support in `_create` / `create_volume_discount` (`Pricing Rule Item Code`: `item_code`), and `selling_price_list` field-permission check in `create_price_list` (`Selling Settings`).
- `components/sales/trading/tests/test_trading.py`: added 10 failing-first boundary tests covering hidden `Sales Team` child fields (6), hidden `Pricing Rule Item Code.item_code` (2), and hidden `Selling Settings.selling_price_list` (2).
- `docs/log/2026-11-19-partner-antigravity-erp-011-review-fixes.md`: append-only review and fix record.

## Decisions
- Source inspection of Frappe `Document.validate_higher_perm_levels` (15.126.0) confirmed two fail-closed gaps on `e268793`: (1) on existing-document updates such as `Sales Order.save()`, Frappe resets restricted child fields (`permlevel > 0`) silently instead of raising `PermissionError`; (2) on new-document inserts (`is_new() == True`) such as `Pricing Rule`, Frappe returns before checking child-table permlevels. Both paths now fail closed with `TRD-FIELD`.
- `PriceList.on_update` can write `Selling Settings.selling_price_list` when no default selling list is set; `create_price_list` now checks field-level read/write access on `selling_price_list` in addition to `Selling Settings` write permission.
- ADR-0031 traceability note: `manifest.json` conservatively sets `touchesLedgerOrTax: true`, though the pack executes no ledger, tax, e-invoice, or payroll arithmetic. Original task brief for ERP-011 was to implement and verify the native trading configuration pack (`Price List`, `Item Price`, `Pricing Rule`, `Customer Credit Limit`, `Sales Person`, `Sales Team`) within the partner lane without claiming unwired tenant activation (`ERP-028`) or production certification. Required line-by-line review by the other founder (`EldonsLogic`), accountant review, and native Arabic/RTL review remain outstanding before merge or promotion.

## Verification
- TDD red before code change: 10 new tests failed, 54 existing tests passed.
- TDD green after code change: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=components/sales/trading pytest components/sales/trading/tests -q` -> **64 passed**.
- Factory sandbox: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=services/blueprint python -m factory check components/sales/trading --run-tests --trusted-source` -> `ok: true`, `levelReached: tested`, `analysis.blocked: false`, 0 issues, 64 blocking tests passed.
- Blueprint suites: `pytest services/blueprint/tests/registry services/blueprint/tests/factory -q` -> **196 passed**.
- Rollback-only native proof `tests/bench_trading.py:run(engine)` on the pinned synthetic container (`erp001.localhost`, Frappe 15.126.0 / ERPNext 15.124.5): all 5 proofs passed (`native price list and item price`, `native scoped volume discount`, `native credit upsert without bypass`, `native commission attribution with no GL posting`, `real engine permission denial`), with rollback verified.
- Repo checks: `check_docs.py`, `check_repo_hygiene.py`, `scan_secrets.py`, `check_plan_independence.py`, `check_pr_trail.py`, `check_lanes.py` all pass.

## Tokens or cost
Not measured.

## Next step
Await CI on PR #192 and the other founder's (`EldonsLogic`) line-by-line review of ERP-011 (`touchesLedgerOrTax: true`, Tier 3), then proceed to `ERP-028` for runtime lifecycle wiring, fixture ID reconciliation, and CI test invocation.
