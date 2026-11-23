# Session log: erp-016-review-round-2

Date: 2026-11-21
Author: partner
Tool and model: claude-code (Claude Sonnet 5.5)
Plan IDs: ERP-016

## Summary
Fixed the eight findings of the cross-model review of d29cc56 on PR 204: line check for any line sequence, commercial rounding, document discounts, negative discounts, currency precision, unit price display, font validation and the CI filter. Tests were written first (90 failures and 47 errors before, 100 passing after). Compare and refuse only; no printed amount is replaced.

## Files touched
- `apps/engine/change_engine/change_engine/print_formats/document_reconciliation.py` (new): `normalise_document` (once at each entry, tuple accepted, generator, string, mapping or set refused), `check_amounts` (commercial rounding, document discount, per-line allocation, negative discounts, currency precision, unit price rule) and the money formatters.
- `.../print_formats/branded_documents.py`: renderers use the normalised copy and the checked amounts; old line check removed; quote and purchase order totals table gets a Discount row when the engine supplies a document discount and take the currency precision.
- `.../print_formats/document_tokens.py`: each font name (family and every fallback item) validated; a malformed fallback such as `","` fails closed; the stack is rebuilt from the validated names.
- `apps/engine/change_engine/change_engine/tests/test_erp_016_branded_templates.py`: half-even test replaced by the ADR-0033 rule; new classes for input shape, document discount, negative discounts, currency precision, unit price display; font cases.
- `.github/workflows/tests.yml`: `engine` filter also matches `docs/brand/tokens/tokens.json`.
- `docs/open-questions.md`: merge of main only (all main rows kept, Q-479 in order).

## Decisions
- Engine field names (the `sales_invoice_to_zatca_dict` payload does not carry the document discount today): `discount_amount` in `totals` or at the top level (both must agree), per-line `distributed_discount_amount` with the engine's net amount in `line_total` or `line_net_amount`. Rule: sum of line amounts less the part of the document discount not already allocated to lines must equal `total_taxable_amount`.
- Unit price: quotes and purchase orders print it at its supplied precision (up to 6 decimals, never below the currency precision), because the 6 decimal limit keeps real price lists usable. Tax invoices go through the ERP-007 print, which prints two decimals and is not changed here, so a unit price with more decimals than the currency precision is refused there. One principle: a unit price is never printed below the precision the check used.
- Tax invoices accept only a 2-decimal precision (ERP-007 formats every amount with two decimals); a 3-decimal currency is supported on quotes and purchase orders only, and refused (not rounded) on invoices. The four phase-1 markets all use 2-decimal currencies. Follow-up for the ERP-007 owner if a 3-decimal market appears.
- An invoice line with no supplied amount whose computed value needs rounding is refused: ERP-007 prints it half-even, which would differ from the commercial rounding checked here. The engine always supplies `line_net_amount`.
- Not done, outside this PR's paths: the ERP-007 invoice totals table has no Discount row, so a document discount reconciles but is not printed as its own row on invoices. Needs a change in `bilingual_tax_invoice.py`.
- The neutral token mapping is unchanged (open question for Eldon on the PR).

## Tokens or cost
Unknown.

## Next step
Eldon's brand-lane answer on the print tokens; ERP-016 re-review. ERP-007 follow-ups (Discount row on invoices, 3-decimal currencies, footer name) need a plan row.
