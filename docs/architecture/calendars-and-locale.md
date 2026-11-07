# Calendars and locale

Status: draft
Owner: eldon

How the platform handles dates, weeks, working time, fiscal years, numbers and time zones across KSA, UAE, Egypt and Qatar. Settings live in the Blueprint (`company.locale`, [schema](../../contracts/blueprint.schema.json)); defaults come from the [country pack](country-packs.md).

## Principles
1. **Store canonically, display locally.** Every date is stored as Gregorian ISO 8601 (dates as `YYYY-MM-DD`, instants as UTC). Hijri is a display, entry and rule layer on top. No table holds a Hijri date as the only copy, except when a document legally records the Hijri date, in which case both are stored.
2. **Commerce and tax run on Gregorian** in practice in all four countries (UNVERIFIED, confirm per country with a local accountant). Hijri matters for Saudi official and some contract contexts, possibly the zakat year (UNVERIFIED), and religious dates (Ramadan, Eid). Egypt may use the Coptic calendar in some contexts (UNVERIFIED); not planned for v1.
3. **Per-company settings with country defaults.** Every `company.locale` field is optional; omitted fields resolve from the country pack, and the resolved values are stored with the compiled artifact.
4. **Numbers and money come from code.** The model never formats or computes dates or amounts.

## Hijri (Umm al-Qura)
- The supported Hijri calendar is **Umm al-Qura** (`hijri_umm_al_qura`), a computed calendar used officially in Saudi Arabia. Library choice for conversion is UNVERIFIED: candidates are the platform's runtime `Intl` support, a maintained Umm al-Qura table library, or our own table. Pick one in the spike, record its licence, and pin it.
- **Sources of divergence** (must be designed for, not ignored):
  - Moon-sighting announcements for Ramadan, Eid and Hajj-related dates can differ from the computed calendar by a day.
  - Regional authorities can announce different dates (UAE and Egypt rely on their own announcements, UNVERIFIED).
  - Umm al-Qura vs observation-based calendars differ by up to a day for some months.
- **Override mechanism:** the country pack's holiday table has an "announced dates" layer (date pairs published by the pack owner when an authority announces); a company can additionally add/remove/move days through `locale.holidays.overrides` (audited, with reason). Rule order: company override, then pack announced date, then computed date. Conversion functions return a flag `computed` or `announced`.
- Documents that show a Hijri date print the computed date unless an announced override exists, and never invent a date.

## Dual-date display on documents
- Controlled by `locale.calendar.secondaryDisplay` and the compliance profile's `hijriDisplay`.
- **Legal layout wins**: where the authority prescribes the date format or position (for example on a Saudi tax invoice), the pack's template decides; tenant preferences only apply to additional, non-mandatory locations.
- Both dates are always printed in the same locale and direction as the surrounding text; digits follow `locale.numberSystem` unless the template mandates otherwise.

## Date pickers and RTL
- Pickers show the primary calendar with the secondary date as a small label; switching calendars never changes the stored value.
- Month and weekday order follow the writing direction; week starts on `locale.week.startDay`.
- Typed entry accepts both Gregorian and Hijri, with unambiguous parsing (year range disambiguates; ambiguous input asks).
- Ranges (`from`, `to`) stay logical (start/end) and flip in RTL. Never concatenate dates into strings by hand; use the formatter.
- Eastern Arabic digits are a display option; inputs normalise to Western digits before storage.

## Week, weekend and working time
- Defaults by pack (UNVERIFIED, confirm): KSA weekend Friday and Saturday; UAE weekend Saturday and Sunday for most employers with Friday partial in government (changed in 2022; UNVERIFIED); Egypt weekend Friday and Saturday (UNVERIFIED). The company can override weekend days, work days and hours.
- **Reduced hours** (for example Ramadan) are periods in `workingTime.reducedPeriods`, either `ramadan` (moves with the Hijri calendar) or fixed dates.
- Working-day calculations (`add_working_days`, `working_days_between`, `next_working_day`) use: work days, weekend days, the holiday calendar after overrides, and nothing else. They are deterministic code with tests.

## Due dates
- Payment terms are stored as rules (for example net 30, end of month, "30 working days"). Due date = computed by code from the document date (Gregorian) and the rule. Whether a due date on a weekend/holiday moves forward is a tenant setting with the pack default.
- Dual-date display of the due date is display only.

## Fiscal year and periods
- `locale.fiscalYear.type`: `gregorian` (default) or `hijri`. A Hijri fiscal year is a rule (start month/day in the Hijri calendar) mapped to Gregorian boundaries per year and stored as explicit period rows, so reports and locks work on Gregorian ranges.
- Periods (month, quarter, year) are stored with Gregorian start and end. VAT filing periods follow the tax authority's rules (pack), independent of the company fiscal year.
- Period closing and locking happens in the engine; the Hijri layer cannot reopen a closed period.
- A change of fiscal year type is a rigid-zone change: team review, and it only applies to future periods.

## Time zones
- Store UTC; display in `locale.timezone` (IANA: Asia/Riyadh, Asia/Dubai, Africa/Cairo).
- KSA, UAE and Qatar have no daylight saving (Qatar UNVERIFIED). Egypt reintroduced daylight saving in 2023 (UNVERIFIED, confirm and watch for changes); rely on the IANA tz database, updated through the normal dependency path, and test around transitions.
- "Today" for a document is the company's local date, not UTC.

## Tests and evals
| Area | Cases |
|---|---|
| Conversion | Known Gregorian to Umm al-Qura pairs across years, month boundaries, Ramadan/Eid boundaries; round trip |
| Divergence | Announced-date override beats computed; company override beats announced; flags set correctly |
| Working days | Weekend variants (Fri-Sat, Sat-Sun), holiday on weekend, Ramadan hours, moved holiday, month and year boundaries |
| Due dates | Net days, end of month, working-day terms across holidays |
| Fiscal year | Hijri fiscal boundaries mapped to Gregorian; leap years; period lock |
| Time zones | Egypt DST transition days; UTC to local date at midnight |
| Documents | Dual-date golden PDFs, Arabic and English, RTL layout, mandated format wins over tenant option |
| UI | Date picker in RTL, typed Hijri input parsing, Eastern Arabic digits |
| AI evals | Arabic prompts with Hijri dates ("first of Ramadan", "end of the Hijri year"), mixed-calendar phrases, relative dates in Gulf dialect; the model must call date tools, not compute |

## Open questions
1. Hijri library choice and licence (UNVERIFIED).
2. Whether the zakat year needs a Hijri fiscal year in v1 (UNVERIFIED; legal).
3. UAE and Egypt official calendars and weekend rules (UNVERIFIED).
4. Who publishes announced-date updates, and how fast (process owner per pack).

Plan IDs: ERP (calendar component), BPL (locale resolution), WEB (pickers, documents), QA (cases above).
