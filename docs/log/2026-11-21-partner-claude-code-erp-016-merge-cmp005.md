# Session log: erp-016-merge-cmp005

Date: 2026-11-21
Author: partner
Tool and model: claude-code (Claude Opus 5.5)
Plan IDs: ERP-016

## Summary
Merged main (with CMP-005 Hijri print settings) into the ERP-016 branch and let the locked branded
layout accept the CMP-005 Hijri date cell, so a branded ZATCA invoice with Hijri enabled renders.

## Merge resolution (commit 06031da, previous session)
- Merge of the branch head db85852 with main 96e2fa9. Hand-resolved files:
  `.github/workflows/tests.yml`, `print_formats/bilingual_tax_invoice.py`,
  `print_formats/branded_documents.py`, `docs/PLAN.md`, `docs/open-questions.md`; both sides kept.
- `render_branded_tax_invoice_html` gained `locale`, `compliance_profile` and `country_default`
  (default `False`) and passes them to `prepare_tax_invoice_view`.
- Blocker found then: with Hijri enabled the branded ZATCA invoice raised `LockedLayoutViolation`,
  because CMP-005 prints the cell as `<bdi dir="rtl" lang="ar">` and `<bdi dir="ltr" lang="en">`
  and the ERP-016 verifier allowed only `dir="ltr"` on `<bdi>` and `lang` only on `<html>`.

## Files touched
- `apps/engine/change_engine/change_engine/print_formats/document_layout.py`: locked CSS adds
  `bdi[dir="rtl"] { direction: rtl; }`; the verifier finds the single Hijri row (Arabic label,
  `td.meta-value`, English label, inside the header region's `meta-table`) and, on tax invoice
  kinds only, allows its direct `<bdi>` children of exactly the forms `dir="rtl" lang="ar"` and
  `dir="ltr" lang="en"`, the first of each. Every other `dir` or `lang` override, these forms
  anywhere else, a look-alike row outside the header and a duplicated Hijri row stay refused.
- `apps/engine/change_engine/change_engine/tests/test_erp_016_branded_templates.py`: new
  `TestHijriCellInLockedLayout` (6 tests: standard and simplified with Hijri on, no row without
  settings, 10 tampered variants inside the cell, 4 injections outside it, duplicated row, CSS rule).
- this log.

## Decisions
- Founder decision (partner): loosen the ERP-016 verifier and locked CSS for exactly the CMP-005
  Hijri cell rather than change CMP-005's markup.
- Founder decision (partner): the branded tax invoice keeps the Hijri row OFF unless tenant
  settings enable it (`country_default=False`), matching the engine print path until CMP-023.

## Checks
- CMP-005, ERP-007 and ERP-016 unittest suites: 221 tests OK (2 skipped). ZATCA Phase 1 component
  and engine wrapper tests OK. `scripts/tests` 22 passed. Workflow YAML parses.
- ERP-007 equivalence: `render_tax_invoice_html` output hashes match main in 9 cases (standard,
  simplified, neutral; Hijri default, on, off, Eastern Arabic digits, `country_default=False`).
- check_docs (0 errors, 0 warnings), check_repo_hygiene, scan_secrets (0 hits),
  check_plan_independence and check_lanes (`--actor partner`, base = merge-base with main): OK.

## Tokens or cost
Unknown.

## Next step
ERP-016: cross-model review of the merge and this verifier change on PR #204 (Tier 3).
