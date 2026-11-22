# Session log: erp-016-branded-document-templates

Date: 2026-11-19
Author: partner
Tool and model: claude-code / claude-sonnet-5-5
Plan IDs: ERP-016

## Summary
Built the tenant-branded bilingual tax invoice, quotation and purchase order HTML templates with the compliance layout locked (ADR-0014). ERP-016 stays `doing` until merge; ERP-007 output is byte-identical (checked against the previous module on both modes, with and without branding).

## Files touched
- `apps/engine/change_engine/change_engine/print_formats/bilingual_tax_invoice.py`: extracted the validation and fragment building of `render_tax_invoice_html` into `prepare_tax_invoice_view` (no output change).
- `.../print_formats/brand_assets.py`: logo validation and sanitising (PNG, JPEG rebuilt without metadata; SVG through an allow-list walker; size, dimension, polyglot, DOCTYPE and `use` loop checks).
- `.../print_formats/brand_tokens.py`: branding resolution (primary 4.5:1 and accent 3:1 on the print surfaces, auto-adjust or reject, display name rules, unknown fields rejected, Powered-by entitlement `branding.removePoweredBy`).
- `.../print_formats/document_layout.py`: locked stylesheet, page shell and `verify_locked_layout` / `assert_locked_layout`.
- `.../print_formats/document_labels.py`: new bilingual labels, all marked unreviewed.
- `.../print_formats/branded_documents.py`: `render_branded_tax_invoice_html`, `render_branded_quote_html`, `render_branded_purchase_order_html`.
- `.../print_formats/__init__.py`: exports.
- `.../tests/test_erp_016_branded_templates.py`: 61 unit and adversarial tests.
- `.github/workflows/tests.yml`: new CI step for the ERP-016 tests (shared path, needs Eldon's review).
- `docs/PLAN.md`: ERP-016 set to `doing`.

## Decisions
- Branding reaches the page only as `:root{--brand-primary;--brand-accent}`. The rest of the stylesheet is a constant that reads colour through `var(--...)`; the verifier requires the page stylesheet to equal that constant, so a tenant or a stored template cannot hide, move or restyle a locked region. Unknown branding fields (custom CSS, layout, fonts, status colours) are rejected, not ignored.
- Colour adjustment darkens the tenant colour toward black by at most 45%; anything lighter, and near-grey colours, are rejected. This follows the product doc examples (an amber is adjusted; yellow, neon and white are rejected). The founders' open decision on the light-shift limit (`docs/brand/12-tenant-theming.md`, Open) still stands; the limit is one constant.
- The accent colour is used only for one decorative rule (graphics, never text), within 3:1 on the print surfaces. The product doc says the accent is not used on invoices in v1; this is a small deviation, easy to remove.
- Logos are embedded with `<img>` only, as a platform-rebuilt data URI, never as inline SVG. The upload pipeline (BRD-007, SEC-006: malware scan, sandboxed decoder, EXIF orientation, storage) is not part of this row; this module is the last line of defence at render time.
- Quote and purchase order totals are only rendered after checking taxable + VAT = grand total (ADR-0031). Neither is a tax document, so neither carries a QR.
- The HTML5 doctype `<!DOCTYPE html>` is kept; the engine-marker test removes it before searching for engine names.
- New Arabic copy (quote, purchase order, terms, delivery, status labels) is UNREVIEWED under ADR-0033 and listed in `UNREVIEWED_ARABIC_LABELS`. A native speaker must review it before customer use.
- No ADR: no contract, auth or tenancy change. The compliance lock is the ADR-0014 consequence; security review by a different model is requested in the PR.

## Verification
- Red first: the new test module failed on import before any implementation existed; then 61 tests pass with the system `python3` (unittest) and `-W error::DeprecationWarning`.
- Mutation checks (temporary, restored): disabling the SVG attribute filter, the stylesheet equality check or the entitlement check each makes tests fail.
- ERP-007 suite: 15 tests pass (1 skipped as before).
- Not verified: rendering in a real PDF engine or browser (no PDF step in this row), Arabic wording by a native speaker, the ZATCA clear-zone figure beyond the existing 4 module and 4.5 mm rules from ERP-007.

## Tokens or cost
Unknown.

## Next step
Cross-model security review of the layout lock and asset sanitiser; WEB-009 (settings for tenant-branded documents) and ERP-017, ERP-019, ERP-025 build on these functions. Set ERP-016 to `done` only after merge.
