# Session log: erp-016-review-round-3

Date: 2026-11-21
Author: partner
Tool and model: claude-code (Claude Sonnet 5.5)
Plan IDs: ERP-016,ERP-030

## Summary
Fixed the four defects of the cross-model re-review of 5ab1ed3 on PR 204 under the partner founder's decision that document-level discounts are out of scope for now: they are refused (fail closed), the renderers print only from the checked snapshot, the print boundary no longer depends on the caller's Decimal context, the currency code fixes the precision, and CSS keywords are refused in the font fallback list. Tests were written first (126 failures and 28 errors before, 127 passing with ERP-007 after). Compare and refuse only; no printed amount is replaced.

## Files touched
- `apps/engine/change_engine/change_engine/print_formats/document_reconciliation.py`: `snapshot_document` (deep, read-once copy; replaces `normalise_document`), `check_amounts` returns the checked `Decimal` totals and lines plus the snapshot with those values; document discounts and per-line allocations refused; allocation reconciliation removed; currency table and precision tie; boolean discount refused; digit and range limit; `in_print_context` fixed Decimal context.
- `.../print_formats/branded_documents.py`: all three public renderers run in the fixed context and print only from `checked.document` and the checked numbers (totals and VAT rate included); the synthesised Discount row is removed.
- `.../print_formats/document_tokens.py`: CSS-wide keywords and `default` refused as a family name; a generic name refused as the quoted primary family.
- `apps/engine/change_engine/change_engine/tests/test_erp_016_branded_templates.py`: round-2 discount allocation tests replaced by refusal tests; new tests for the snapshot, print precision, booleans, currency table, font keywords.
- `docs/PLAN.md`: new row ERP-030 (one row).

## Decisions
- Document discount refusal covers `discount_amount` (top level and `totals`), `additional_discount_amount`, `additional_discount_percentage`, and per line `distributed_discount_amount`, `allocated_discount_amount`, `discount_allocation`. An explicit zero or an empty value is not a discount and is accepted (nothing to print); any other value, an unparsable one or a boolean is refused with a reason naming ERP-030. Line discounts keep `qty x price - discount`, non-negative.
- Quantity: printed exactly as supplied (lossless), not rounded to a coarser value than the check used. Chosen over refusing long quantities because the check already uses the exact quantity. The review's `0.0049` shows as `0.005` only when the caller's Decimal context has a low precision (ERP-007's formatter normalises in the ambient context); the renderers now run in a fixed context (80 digits, half-even to match ERP-007 defaults), so it prints `0.0049` in any caller context. Test under precisions 28, 3 and 1.
- All reconciliation and print arithmetic is independent of the caller's context: explicit contexts in the check, and a fixed local context for the whole render (this also covers ERP-007's own `taxable + vat == grand` check, which broke under `prec=6`). Numbers beyond 30 digits or 1e30 are refused as out of range so the 80 digit context is always exact.
- Currency precision: the default is now the ISO 4217 minor units of the currency; a supplied `currency_precision` must equal it. Table: SAR, AED, EGP, QAR, USD, EUR 2; KWD, BHD, OMR 3. An unknown or missing currency is refused. Maximum precision is now 3 (was 4).
- Snapshot: each nested mapping and list is copied once into plain dicts and lists (a value read once; unsupported value types such as generators, sets and bytes are refused); the check and the print use only that copy. The ERP-007 view is built from the snapshot whose checked numeric fields are Decimals.
- Font: the check rejects `inherit`, `initial`, `unset`, `revert`, `revert-layer`, `default` (any case) anywhere in the stack; generics stay valid in the fallback list.
- Not done here (ERP-030): the payload builder emitting discount fields, a reconciled discount row, the adapter `sales_invoice_to_zatca_dict` sending a net `line_net_amount` that this renderer refuses against a 200.00 gross line, and the ERP-007 cleanup (platform footer label, token-based styles).

## Tokens or cost
Unknown.

## Next step
Cross-model re-review of this round on PR 204 (Eldon's brand-lane answer on the print tokens is still open). ERP-030 for document discounts end to end.
