# Session log: cmp-023-company-calendar

Date: 2026-11-23
Author: partner
Tool and model: claude-code (Sonnet 5.5)
Plan IDs: CMP-023

## Summary
First slice of CMP-023: a spec and a tested `components/compliance/company_calendar/` module that resolves week start, weekend, work days, hours, reduced (Ramadan) periods and number system from the country pack plus company overrides; Ramadan comes from the pinned Umm al-Qura tables. 30 new tests pass (country pack suite still 99 passing, loader untouched).

## Files touched
- docs/specs/company-calendar-settings.md: settings model, overrides, Ramadan, failure behaviour, open questions
- components/compliance/company_calendar/: `settings.py`, `__init__.py`, `tests/test_company_calendar.py`
- .github/workflows/tests.yml: wire the new suite (path allowlist plus one step that installs `hijridate==2.6.0`)
- docs/PLAN.md: CMP-023 `todo` to `doing`

## Decisions
- Used `hijridate` directly (the CMP-022 pinned library), not `change_engine.i18n.hijri`, so `components/` does not import from `apps/engine/`.
- Kept the number-system vocabulary of the pack and Blueprint (`western`, `eastern_arabic`).
- No statutory limit is enforced in code; all working-time values are pack or company data and stay UNVERIFIED with the pack's evidence status.
- Package named `company_calendar` to avoid shadowing the stdlib `calendar`.

## Tokens or cost
Unknown.

## Next step
CMP-023 stays `doing` until the founders answer the open questions in the spec. Remaining from the row: announced (moon-sighting) Ramadan dates (needs CMP-024), a Blueprint-level `company.locale` resolver call site (BPL), UI settings screen. CMP-024 holidays, CMP-025 fiscal year, CMP-026 timezones follow.

## Review fixes, round 1

Cross-model review by ChatGPT gpt-6.1-sol at `f2b1898`: APPROVE with two Lows. It checked 632 Ramadan boundary dates across 1343 to 1500 AH against the pinned tables, and four deliberate Ramadan mutations were caught by the existing tests.

- Low 1: a reduced period's `labels` dict could be changed in place despite the immutable-result contract. Labels are now a read-only `MappingProxyType`; `test_nested_labels_are_immutable` failed before the fix and passes after.
- Low 2: `week_start_date(date.min)` raised a raw `OverflowError`. It now raises `CalendarSettingsError("calendar_range")`; `test_week_start_date_before_the_calendar_range_fails_closed` failed before and passes after.
- Spec updated for both. Calendar suite 32 OK, country pack suite unchanged and OK.
