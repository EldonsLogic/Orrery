# Session log: erp-007-bilingual-tax-invoice

Date: 2026-11-17
Author: partner
Tool and model: antigravity (gemini-4-hydrogen)
Plan IDs: ERP-007

## Summary
Implemented the bilingual Arabic/English RTL tax invoice HTML/PDF print format (`ERP-007`) in `change_engine.print_formats`, supporting both strict ZATCA Phase 1 (`zatca_sa`) with embedded 5-tag TLV QR clear zone and country-neutral (`neutral`) golden-path rendering, wired into Frappe Jinja hooks and verified on the live bench with WeasyPrint and wkhtmltopdf.

## Files touched
- `apps/engine/change_engine/change_engine/print_formats/__init__.py`: Export bilingual tax invoice renderer, QR SVG helper, branding validator, Sales Invoice mapper, and Print Format installer.
- `apps/engine/change_engine/change_engine/print_formats/qr_svg.py`: Self-contained QR matrix & SVG generator using `pyqrcode` in the Frappe bench (with pure-Python ISO/IEC 18004 Byte-mode fallback for dependency-free unit tests/CI) and mandatory `>= 4` module quiet zone.
- `apps/engine/change_engine/change_engine/print_formats/bilingual_tax_invoice.py`: Bilingual RTL HTML/PDF renderer (`zatca_sa` via `change_engine.compliance.generate_phase1_invoice` and `neutral` without ZATCA coupling), ADR-0031 fail-closed totals enforcement, XSS escaping, WCAG AA 4.5:1 branding & raster-logo guardrails, ERPNext `Sales Invoice` mapper (including negative return credit-note magnitude mapping), and idempotent Frappe `Print Format` installer.
- `apps/engine/change_engine/change_engine/hooks.py`: Register `render_frappe_sales_invoice_html` in Frappe `jinja["methods"]`.
- `apps/engine/change_engine/change_engine/tests/test_erp_007_bilingual_tax_invoice.py`: Unit & integration tests covering ZATCA standard/simplified/credit/debit notes, neutral mode independence, QR TLV round-trip, branding/XSS guardrails, Sales Invoice mapping, hooks/Print Format installation, and live PDF generation.
- `.github/workflows/ci.yml`: Run `test_erp_007_bilingual_tax_invoice.py` in CI.
- `docs/PLAN.md`: Mark `ERP-007` `done`.

## Decisions
- Followed `ADR-0026` and `docs/specs/golden-path-trading-sale.md` section 8 by lazy-importing `change_engine.compliance` only in `zatca_sa` mode so `neutral` mode stays completely decoupled from country-specific compliance code.
- Followed `ADR-0031` by never recomputing tax or invoice totals in the print formatter; engine totals are validated for consistency and rendered verbatim.
- Verification: `uv run` pytest suite passed (`71 passed, 1 skipped, 26 subtests passed`), live bench `platform-erp001-20261111b-engine-1` ran all 15 `test_erp_007_bilingual_tax_invoice` tests (including WeasyPrint PDF 32,749 bytes ZATCA / 19,546 bytes neutral, wkhtmltopdf PDF 50,352 bytes, live Frappe Jinja hook + Print Format install/cleanup) and generated PDF was visually inspected.

## Tokens or cost
Unknown (session in Antigravity / T3 Code).

## Next step
Check if PR #96 (`BPL-007`) has merged to unblock `BPL-008`, or continue through the next G1 `partner` items (`ERP-002`, `SEC-004`, `CE-SEC-005`).
