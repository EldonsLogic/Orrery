# Session log: cmp-005-review-engine-print-settings

Date: 2026-11-21
Author: partner
Tool and model: antigravity / Gemini 4 Hydrogen
Plan IDs: CMP-005

## Summary
Addressed Items 2 and 3 from the cross-model review of PR #155 (`e702891`): defaulted the Hijri row OFF on the engine print path (`render_frappe_sales_invoice_html`) unless tenant settings that enable it are passed, and changed `hijri_fields` so a datetime value in a source Date field leaves its companion empty instead of blocking the save.

## Brief (ADR-0031)
Fix two items from Eldon's cross-model review on PR #155 (`cmp-005-hijri-dates-impl`, head `e702891`, Tier 3 legal invoice output, tests first, minimal diff, fail safe):
1. Item 2 (Medium): `print_formats/bilingual_tax_invoice.py`: `{{ render_frappe_sales_invoice_html(doc) }}` receives no `locale` or `compliance_profile` from Frappe, so a Saudi tenant with `hijriDisplay.enabled: false` still got the Hijri row and `numberSystem` was ignored. Choose the safe option (OFF on the engine print path unless resolved settings enable it, or resolve trusted per-site settings if already available in the codebase) and record the choice.
2. Item 3 (Low): `i18n/hijri_fields.py`: a datetime value in a source Date field leaves the companion empty (log doctype and field only, never the value) instead of blocking the save; malformed text still refuses.
3. Leave `sales_invoice_to_zatca_dict` and totals rows untouched.

## Files touched
- `apps/engine/change_engine/change_engine/print_formats/bilingual_tax_invoice.py`: added `country_default: bool | None = None` to `render_tax_invoice_html` (preserving existing `mode == "zatca_sa"` default for direct callers) and passed `country_default=False` from `render_frappe_sales_invoice_html` so the engine print path keeps Hijri OFF unless passed `locale`/`compliance_profile` settings enable it.
- `apps/engine/change_engine/change_engine/i18n/hijri_fields.py`: added `_is_datetime_value` and updated `_companion_value` so Python `datetime` instances and valid ISO/engine datetime strings leave the companion empty and log a warning with doctype and field name only (never the value), while malformed text and missing converter still fail closed.
- `apps/engine/change_engine/change_engine/tests/test_cmp_005_hijri_dates.py`: added tests (verified failing before the fix) for engine print defaults/settings/`hijriDisplay.enabled: false`/`numberSystem`, and for datetime source values leaving companions empty while malformed text refuses.
- `docs/log/2026-11-21-partner-antigravity-cmp-005-review-engine-print-settings.md`: this log.

## Decisions
- **Item 2 option chosen — Hijri row OFF by default on the engine print path until CMP-023:** Inspection of `adapter/frappe_backend.py` (`_sync_settings` and `tabChange Engine Blueprint State`) confirmed that per-company `hijriDisplay`, `calendar`, and `numberSystem` settings are not yet stored or synced in the Frappe site database (that is scoped to CMP-023 in G2). Therefore `render_frappe_sales_invoice_html` passes `country_default=False` to `render_tax_invoice_html` so the engine print template (`{{ render_frappe_sales_invoice_html(doc) }}`) omits the Hijri row unless resolved settings enabling it are passed, while honouring `locale`, `numberSystem`, and `compliance_profile.hijriDisplay.enabled` when supplied. `docs/PLAN.md` row CMP-005 does not promise a default, so no plan row edit was needed.

## Verification
- Before fix: `uv run --no-project --with "hijridate==2.6.0" --with "pydantic>=2" env PYTHONPATH=apps/engine/change_engine:. python -m unittest apps/engine/change_engine/change_engine/tests/test_cmp_005_calendar.py apps/engine/change_engine/change_engine/tests/test_cmp_005_hijri_dates.py apps/engine/change_engine/change_engine/tests/test_erp_007_bilingual_tax_invoice.py -v` -> 47 tests, 2 failures, 2 errors, 2 skipped (new/updated tests failed as expected).
- After fix (same command): 47 passed (2 skipped for optional PDF backend).
- `uv run --no-project --with pytest pytest scripts/tests`: 22 passed.
- `python3 scripts/check_docs.py`: 0 errors, 0 warnings.
- `python3 scripts/check_repo_hygiene.py`: OK (1666 files checked).
- `python3 scripts/scan_secrets.py`: 0 hits.
- `python3 scripts/check_plan_independence.py`: OK.

## Tokens or cost
Unknown.

## Next step
Human line-by-line review (ADR-0031), independent compliance review, Arabic copy review (ADR-0033), and live bench check of `before_update_after_submit` remain open before CMP-005 can move to `done`; CMP-023 will wire per-company calendar and `numberSystem` settings into the engine print path.
