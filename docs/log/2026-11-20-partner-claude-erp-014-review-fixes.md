# Session log: erp-014-review-fixes

Date: 2026-11-20
Author: partner
Tool and model: Claude Sonnet 5.5 (Claude Code)
Plan IDs: ERP-014

## Summary
Fixed the cross-model review findings on PR #149 (Gemini and Claude). The three "fix before merge" items are done: the cancel and credit-note check rejects empty or zeroed GL rows, the stock check compares every step with an exact Moving Average oracle (and a forced receipt-at-new-rate, issue, receipt, issue sequence), and the probe reads line and permuted amounts by SQL CAST with the line amount recomputed from the seeded input. Also done: forced VAT cases (.005 boundary across lines, Z-only, E-only, 10% document discount), fail-closed bench env guard, AST check of the probe in the pure layer, deterministic posting times, primary source URLs.

## Files touched
- apps/engine/change_engine/change_engine/tests/test_erp_014_accounting_properties.py: stronger test_2, test_4, test_5; forced inputs; Decimal stock oracle; pure tests for forced cases, env guard and probe AST; docstring sources.
- apps/engine/change_engine/change_engine/tests/erp_014_bench_probe.py: SQL CAST for line and permuted amounts, document discount input, fixed posting times.
- docs/log/2026-11-20-partner-claude-erp-014-review-fixes.md: this log.

## Decisions
- None. Stock step count is `1 + len(stock_moves)` (the opening receipt plus every move, the golden issue is already in `stock_moves`), not `2 + len`.
- Not run against a live bench in this session (no ERP-014 bench up here). The new live assertions were exercised only with synthetic data through the pure layer, including mutations (FIFO values, dropped moves, per-line VAT, wrong line amount, empty and zeroed cancel); Eldon's or a bench run is still needed to confirm them live. The discount check bounds the net total within one cent per line instead of mirroring the engine's discount distribution (UNVERIFIED against the engine).
- Source check: ZATCA guideline (15%) and Federal Decree-Law 8/2017 Art. 3 (5%) PDFs fetched and read 2026-11-20. The ZATCA guideline does not state the 2020-07-01 start date: marked UNVERIFIED. UAE per-row rounding and negative tie-break stay UNVERIFIED.
- Left as follow-up (nits, not blocking under ADR-0035): per-account GL expectations (Debtors, Sales, VAT), 100% discount, negative lines, multi-currency, update_stock returns, large-magnitude float rounding samples.

## Tokens or cost
Unknown.

## Next step
Eldon: confirm round-two review of PR #149 and the accountant question on rounding once per tax row. A follow-up plan row can take the deferred nits.
