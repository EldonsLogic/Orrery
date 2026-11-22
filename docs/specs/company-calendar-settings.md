# Per-company calendar and week settings (CMP-023)

Status: draft
Owner: partner
Related: [ADR-0015](../decisions/ADR-0015-country-packs-calendars-locale.md), [country-pack-framework.md](../compliance/country-pack-framework.md), [calendars-and-locale.md](../architecture/calendars-and-locale.md), RULES 31

First slice of the CMP-023 row: a deterministic settings module at `components/compliance/company_calendar/`. It reads a country pack only through `resolve_country_pack` (CMP-021) and the Umm al-Qura tables of `hijridate` 2.6.0 (CMP-022). It does not change the pack schema, the Blueprint contract or any pack.

## 1. Settings model
`resolve_calendar_settings(country_code, packs_dir, company_locale, version=..., environment=...)` returns an immutable `CompanyCalendarSettings`:

| Field | Source in `company.locale` / pack `localeDefaults` | Notes |
|---|---|---|
| `week_start` | `week.startDay` | Any weekday; need not be a work day. |
| `weekend_days` | `week.weekendDays` | 1 to 3 unique weekdays. |
| `work_days` | `workingTime.workDays` | Disjoint from `weekend_days`. A day in neither list is simply not a work day (rotas, half days). |
| `hours` | `workingTime.hours` | `from` before `to`, `HH:MM`. |
| `reduced_periods` | `workingTime.reducedPeriods` | `ramadan` (moves with the Umm al-Qura year) or `fixed_dates` (Gregorian from/to). Ramadan hours are one such period. |
| `number_system` | `numberSystem` | `western` or `eastern_arabic`, the existing Blueprint vocabulary (not `latn`/`arab`). |
| `timezone`, `country_code`, `pack_id`, `pack_version`, `evidence_status`, `applied_overrides` | pack | Carried so a caller can see which defaults were used and that the pack facts are still `unverified`. |

Behaviour: `is_weekend(d)`, `is_work_day(d)` (weekly pattern only; the holiday calendar is CMP-024), `week_start_date(d)`, `hours_on(d)` (reduced period hours, else regular hours, `None` on a non-work day, with `period_id` and `source` of `regular`, `fixed_dates` or `computed`), `ramadan_range(hijri_year)` and `format_digits(text)` (display only: ASCII digits to Eastern Arabic; stored and entered values stay ASCII, calendars-and-locale.md).

## 2. Defaults and allowed company overrides
Defaults come from the pack's `localeDefaults`. A company may override exactly the paths the pack lists in `overridesPolicy.overridablePaths`; for the four shipped packs that includes every setting above. The module adds no override rules of its own: the framework's allowlist, locked paths and post-merge invariants apply, and `company_locale` keys outside this module (fiscal year, holidays) are validated by the framework and left to their owners (CMP-025, CMP-024).

## 3. Ramadan
- Ramadan is Hijri month 9 in the Umm al-Qura tables of the pinned library; the code never computes lunar dates. The library covers 1343 to 1500 AH; a date or year outside it fails closed.
- The computed range can differ by a day from the announced one (moon sighting). The result carries `source: computed`; the announced-date layer (company override, then pack announced date, then computed, calendars-and-locale.md) arrives with CMP-024 and is not in this slice.
- A reduced period applies only on work days. If two periods match one date (for example a `ramadan` and an overlapping `fixed_dates` period) the module raises instead of picking one.

## 4. Validation and failure behaviour
Fail closed, no silent fallback:
- Unknown country, missing pack, rejected or locked override, invalid weekday, overlapping work and weekend days, bad `HH:MM`, unknown number system: the framework raises (`UnknownCountryError`, `PackNotFoundError`, `OverrideRejectedError`) and the module lets it propagate.
- `CalendarSettingsError` with a stable `code` (`invalid_date`, `invalid_year`, `invalid_text`, `calendar_range`, `calendar_unavailable`, `ambiguous_reduced_period`): non-`date` input (timestamps, strings), Hijri year or date outside the tables, library missing, ambiguous period. Messages carry no customer data and no user-facing text; the UI maps codes through i18n.
- Inputs are never mutated; results are frozen.

## 5. Legal values are data, not code
The code enforces no statutory rule: no daily or weekly hour cap, no minimum Ramadan reduction, no weekend rule. Every working-time value is pack or company data and inherits the pack's evidence status (all four packs are `unverified`, see each pack's `evidence.json`). Reported figures that conflict with each other, for example Qatar Ramadan hours of 6 or 4 a day, stay UNVERIFIED in [qatar-research.md](../compliance/qatar-research.md) and are not encoded.

## 6. Tests
`components/compliance/company_calendar/tests/test_company_calendar.py`, run with `python3 -m unittest discover -s components/compliance/company_calendar/tests -t .` (needs `jsonschema` and `hijridate==2.6.0`). Covers pack defaults for SA, AE, EG, QA, overrides and their rejection, day classification, week start, Ramadan 1447 and 1448 boundaries against the pinned tables, fixed-date periods, ambiguity, out-of-table dates, digits.

## Open questions (for the founders, not yet entered in open-questions.md)
1. May a company remove its Ramadan reduction or set longer hours than the pack default? Statutory minimums per country are UNVERIFIED, so the module allows it today.
2. Should a moon-sighting announcement shift Ramadan hours the day it is announced? Needs the CMP-024 announced-date layer and a rule on who publishes it.
3. Should a day that is neither a work day nor a weekend (for example a Friday half day) be modelled as its own setting? Not in this slice.
4. Reviewer tier: proposed Tier 2 (settings reader, no tax or payroll maths). Raise to Tier 3 if the reviewer treats pack consumption as compliance code.
