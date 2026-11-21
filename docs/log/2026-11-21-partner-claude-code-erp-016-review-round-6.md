# Session log: erp-016-review-round-6

Date: 2026-11-21
Author: partner
Tool and model: claude-code (Claude Opus 5.5, implementation sub-agent)
Plan IDs: ERP-016,ERP-030

## Summary
Fixed items 2-7 of Eldon's cross-model review of PR #204 (submitted 13:15, head 50897f8). The tests came first: 168 tests ran, with 11 failures and 39 errors (the new tests, plus the existing tests that used the renamed ZATCA kind). After the fixes all 168 pass. Merged `origin/main` first (one conflict in `docs/open-questions.md`, kept both sides). Item 1 was already fixed in round 5.

| Item | Fix | Where | Tests |
|---|---|---|---|
| 2 Medium | The package now carries a token snapshot, `print_formats/brand_tokens_snapshot.json`. It holds only the 7 light colours and the body font the layout reads. The loader takes `BRAND_TOKENS_PATH` if set (and never falls back from it), then the repo `tokens.json`, then the snapshot. | `document_tokens.py` (`SNAPSHOT_PATH`, `snapshot_of`, `write_snapshot`, `_token_source`) | `TestPackagedTokenSnapshot` (fails on drift, contents only, bench render without the repo file gives the same output byte for byte, no fallback from an operator path, repo file wins); the existing missing-file test now also removes the snapshot |
| 3 Medium, UNVERIFIED | Neutral mode refuses a UAE supplier (`AE`, `ARE` or "United Arab Emirates", top level or in the address) or an `AED` invoice. It raises `UaeTaxInvoiceModeUnavailable`, code `uae_tax_invoice_mode_unavailable`. Q-523 is added (it was free on main). | `branded_documents.py` (`_is_uae_invoice`) | `TestNeutralModeIsNeverAUaeTaxInvoice` |
| 4 Low | Every quote and PO line must have a `vat_rate`: a missing, `None` or blank value is refused. The printer no longer falls back to 0. | `branded_documents.py` (`_check_lines`, `_lines_region`) | `TestCommercialLinesNeedAVatRate` |
| 5 Low, UNVERIFIED | `tax_invoice_zatca_sa` is split into `_standard` and `_simplified`. In ZATCA mode the `issue_time` label is required. A standard (B2B) invoice must also show the buyer VAT number and buyer address labels. The renderer picks the kind from the ZATCA result (new `TaxInvoiceView.invoice_type`) and refuses any other type. | `document_layout.py` (`_tax_spec`), `branded_documents.py`, `bilingual_tax_invoice.py` (one view field, Hijri block untouched) | `TestStricterZatcaVerifier`; existing tests now use the new kind name |
| 6 Low | All labels go through `label_pair`. When `CHANGE_ENGINE_ENV` is not `dev` or `test` (an unset value counts as production), any unreviewed Arabic label raises `UnreviewedArabicLabelError`, code `unreviewed_arabic_label`. The test module runs with `CHANGE_ENGINE_ENV=test`. | `document_labels.py`, `branded_documents.py` | `TestUnreviewedArabicGuard` (unset, production, staging, development: refused; dev, test: render; an invoice with only reviewed labels renders in production) |
| 7 Low | The ERP-030 row now also covers ERP-007's own line rows (discount and allocation) and moving the document labels to the i18n catalogue. The labels are not moved in this PR. | `docs/PLAN.md` | n/a |

Regenerate the token snapshot after any change to `docs/brand/tokens/tokens.json`. From the repository root, run:
`PYTHONPATH=apps/engine/change_engine python3 -c "from change_engine.print_formats.document_tokens import write_snapshot; write_snapshot()"`
The drift test prints the same command. Never hand-edit the snapshot or the source tokens (ADR-0014).

## Files touched
- `apps/engine/change_engine/change_engine/print_formats/document_tokens.py`: added the snapshot fallback and `write_snapshot`.
- `apps/engine/change_engine/change_engine/print_formats/brand_tokens_snapshot.json`: new, generated.
- `apps/engine/change_engine/change_engine/print_formats/branded_documents.py`: added the UAE refusal, the required `vat_rate`, the ZATCA kind by invoice type, and labels read through `label_pair`.
- `apps/engine/change_engine/change_engine/print_formats/document_labels.py`: added `label_pair` and `UnreviewedArabicLabelError`.
- `apps/engine/change_engine/change_engine/print_formats/document_layout.py`: the verifier now checks the issue time, and the buyer VAT number and address on standard invoices; two ZATCA kinds.
- `apps/engine/change_engine/change_engine/print_formats/bilingual_tax_invoice.py`: added `TaxInvoiceView.invoice_type`.
- `apps/engine/change_engine/change_engine/print_formats/__init__.py`: exports the two new errors.
- `apps/engine/change_engine/change_engine/tests/test_erp_016_branded_templates.py`: round 6 tests, the test environment and the kind rename.
- `docs/PLAN.md` (ERP-030 row), `docs/open-questions.md` (Q-523).

## Decisions
- None new. The refusals follow ADR-0031 and ADR-0033 (fail closed). No ADR is edited.
- Behaviour change to note in review: a standard ZATCA invoice whose buyer has no VAT number is now refused by the verifier. The ZATCA component accepts that case, so it is UNVERIFIED whether a non-registered B2B buyer is allowed. The compliance reviewer should confirm.
- Behaviour change: outside dev and test every quote and PO is refused, and so is any tax invoice that prints the "Powered by" footer or the discount information row. Until the Arabic is reviewed (ADR-0033), no customer-facing path prints them. The `CHANGE_ENGINE_ENV` value `development` is refused, matching ERP-027 `OFFLINE_SIMULATOR_ENVS`.

## Tokens or cost
Unknown.

## Next step
- ERP-016: run a smoke render on the bench. No bench was available in this session, so the snapshot path is checked only by the unit test that hides the repo file. The bench also needs `CHANGE_ENGINE_ENV=dev`, or the Arabic guard refuses; `infra/dev/docker/*` belongs to INF-015 and was not touched.
- Q-523: a UAE tax invoice mode (partner, with CMP-011).
- ERP-030: implement the widened row.
