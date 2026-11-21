# Session log: cmp-005-review-fixes

Date: 2026-11-20
Author: partner
Tool and model: claude-code / sonnet-5.5
Plan IDs: CMP-005

## Summary
Fixed every finding from the 2026-11-19 cross-model review of Tier 3 PR #155 (Hijri dates), with a regression test per finding. Merged `origin/main` without rewriting history. Hijri stays a secondary display that can never block the legal invoice or a business document save.

## Files touched
- `apps/engine/change_engine/change_engine/print_formats/bilingual_tax_invoice.py`: the optional Hijri row is built inside a guard; a missing converter or an issue date outside 1924-08-01..2077-11-16 omits the row, logs a warning with the error code only, and renders the legal invoice (Gregorian date, totals, QR) unchanged (finding 1). The mandatory Gregorian issue date stays fail-closed and always prints in Western digits; digit localisation applies only to the Hijri line, and an unsupported `numberSystem` or calendar/profile setting still fails closed (finding 4).
- `apps/engine/change_engine/change_engine/i18n/hijri_fields.py`: out-of-range source dates (for example `valid_till=2099-12-31`) leave the companion empty and log doctype and field name only, never the value, so those documents stay saveable. Malformed values and a missing converter still reject; inside the engine they become a Frappe `ValidationError` carrying the catalogue text (Arabic or English by session language) instead of a raw `ValueError` (finding 2). `derive_companions` follows the same rule.
- `apps/engine/change_engine/change_engine/i18n/hijri.py`: an explicit `hijriDisplay.enabled` (true or false) now decides alone, so a profile that disables the display wins over locale `primary`/`secondaryDisplay` (finding 3).
- `apps/engine/change_engine/change_engine/tests/test_cmp_005_hijri_dates.py`: regressions for findings 1 to 7. Timestamps (`datetime`, `YYYY-MM-DDTHH:MM:SS`) are rejected on purpose end to end through `sales_invoice_to_zatca_dict` and `render_frappe_sales_invoice_html`; a Frappe Date field loads as `date` and REST payloads as ISO strings, both accepted and tested (finding 5). Non-trading DocTypes and documents without installed companions are untouched (finding 7).
- `docs/PLAN.md`: CMP-005 moved from `done` to `doing` (finding 6).
- this log.

## Verification
- Python 3.12, isolated environment, hijridate 2.6.0: `PYTHONPATH=apps/engine/change_engine:. python -m unittest change_engine.tests.test_cmp_005_calendar change_engine.tests.test_cmp_005_hijri_dates change_engine.tests.test_erp_007_bilingual_tax_invoice`: 46 tests pass (2 skipped, optional PDF backends).
- Whole engine test directory (live MariaDB file excluded, no database available): 210 passed, 17 skipped, 111 subtests passed. The companion tests pin `frappe` to absent because other suites leave a mock `frappe` module in `sys.modules`.
- Repo gates are run through `finish_session.py`.

## Residual risk (still open on PR #155)
- Table accuracy against the official Umm al-Qura calendar is UNVERIFIED (CMP-022 records the library choice, not the accuracy check); Hijri is on by default for Saudi invoices. CMP-005 stays `doing` until that is verified or the founders accept the risk in writing.
- No live bench or MariaDB run: `before_update_after_submit` against Frappe's "not allowed to change after submit" check for the `allow_on_submit` companions, and the hook and field install path, are unverified end to end.
- Arabic copy is `unreviewed` (ADR-0033). Tier 3: founder line-by-line review (ADR-0031) and independent compliance review are still pending. Whether Eastern Arabic digits are acceptable on the legal Gregorian date is moot now (Western digits only).
- Finding 8 (606 added lines, three logs for one PR) is process only; logs are append-only, so none were merged or removed.

## Decisions
- Hijri failures degrade the display, never the legal document or a business save; settings errors and a malformed Gregorian date still fail closed. No ADR needed: this applies ADR-0015 as written.

## Tokens or cost
Unknown.

## Next step
Eldon and the compliance reviewer re-review PR #155; then CMP-022 accuracy verification and a real bench run, after which CMP-005 can move to `done`.
