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
