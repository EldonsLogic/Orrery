"""Per-company calendar and week settings, resolved from a country pack (CMP-023).

Spec: docs/specs/company-calendar-settings.md. The pack and its override merger are read only through
`resolve_country_pack` (CMP-021). Ramadan comes from the pinned Umm al-Qura tables (`hijridate`, CMP-022),
never from hand-computed dates. No statutory limit is enforced here: pack and company values are data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time, timedelta
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from components.compliance.country_pack import resolve_country_pack

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")  # date.weekday() order
RAMADAN_MONTH = 9
_EASTERN_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


class CalendarSettingsError(ValueError):
    """Invalid input or an unavailable calendar. `code` is stable; no customer data is put in the message."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class WorkingHours:
    start: time
    end: time


@dataclass(frozen=True)
class ReducedPeriod:
    id: str
    labels: Mapping[str, str]  # read-only view
    rule: str  # "ramadan" or "fixed_dates"
    hours: WorkingHours
    gregorian_from: date | None = None
    gregorian_to: date | None = None


@dataclass(frozen=True)
class DayHours:
    start: time
    end: time
    period_id: str | None  # None for regular hours
    source: str  # "regular", "fixed_dates" or "computed" (Umm al-Qura Ramadan)


@dataclass(frozen=True)
class RamadanRange:
    start: date
    end: date
    source: str = "computed"  # an announced-date layer arrives with CMP-024


def _library():
    try:
        from hijridate import Gregorian, Hijri
    except ImportError:
        raise CalendarSettingsError("calendar_unavailable") from None
    return Gregorian, Hijri


def _check_date(value: Any) -> date:
    if type(value) is not date:  # rejects datetime, str, None
        raise CalendarSettingsError("invalid_date")
    return value


def _to_date(g: Any) -> date:
    return date(g.year, g.month, g.day)


def _time(text: str) -> time:
    return time.fromisoformat(text)


def _hours(raw: dict[str, str]) -> WorkingHours:
    return WorkingHours(_time(raw["from"]), _time(raw["to"]))


@dataclass(frozen=True)
class CompanyCalendarSettings:
    country_code: str
    pack_id: str
    pack_version: str
    evidence_status: str  # from the pack; "unverified" until its facts are verified
    timezone: str
    week_start: str
    weekend_days: tuple[str, ...]
    work_days: tuple[str, ...]
    hours: WorkingHours
    reduced_periods: tuple[ReducedPeriod, ...]
    number_system: str  # "western" or "eastern_arabic"
    applied_overrides: tuple[str, ...]

    def is_weekend(self, day: date) -> bool:
        return WEEKDAYS[_check_date(day).weekday()] in self.weekend_days

    def is_work_day(self, day: date) -> bool:
        """Weekly pattern only; the holiday calendar (CMP-024) is applied by the caller."""
        return WEEKDAYS[_check_date(day).weekday()] in self.work_days

    def week_start_date(self, day: date) -> date:
        offset = (_check_date(day).weekday() - WEEKDAYS.index(self.week_start)) % 7
        try:
            return day - timedelta(days=offset)
        except OverflowError:
            raise CalendarSettingsError("calendar_range") from None

    def ramadan_range(self, hijri_year: int) -> RamadanRange:
        """First and last Gregorian day of Ramadan, from the Umm al-Qura tables; fails closed outside them."""
        if type(hijri_year) is not int:
            raise CalendarSettingsError("invalid_year")
        _, Hijri = _library()
        try:
            first = Hijri(hijri_year, RAMADAN_MONTH, 1)
            last = Hijri(hijri_year, RAMADAN_MONTH, first.month_length())
            return RamadanRange(_to_date(first.to_gregorian()), _to_date(last.to_gregorian()))
        except (ValueError, OverflowError):
            raise CalendarSettingsError("calendar_range") from None

    def _in_ramadan(self, day: date) -> bool:
        Gregorian, _ = _library()
        try:
            return Gregorian(day.year, day.month, day.day).to_hijri().month == RAMADAN_MONTH
        except (ValueError, OverflowError):
            raise CalendarSettingsError("calendar_range") from None

    def hours_on(self, day: date) -> DayHours | None:
        """Hours worked on `day`, or None on a non-work day. More than one matching period fails closed."""
        if not self.is_work_day(day):
            return None
        matches = []
        for p in self.reduced_periods:
            if p.rule == "ramadan":
                hit = self._in_ramadan(day)
            else:
                hit = p.gregorian_from <= day <= p.gregorian_to
            if hit:
                matches.append(p)
        if len(matches) > 1:
            raise CalendarSettingsError("ambiguous_reduced_period")
        if matches:
            p = matches[0]
            return DayHours(p.hours.start, p.hours.end, p.id, "computed" if p.rule == "ramadan" else "fixed_dates")
        return DayHours(self.hours.start, self.hours.end, None, "regular")

    def format_digits(self, text: str) -> str:
        """Display only: ASCII digits to Eastern Arabic when the company chose it. Storage stays ASCII."""
        if not isinstance(text, str):
            raise CalendarSettingsError("invalid_text")
        return text.translate(_EASTERN_DIGITS) if self.number_system == "eastern_arabic" else text


def resolve_calendar_settings(
    country_code: str,
    packs_dir: Path,
    company_locale: dict[str, Any] | None = None,
    *,
    version: str | None = None,
    pack_id: str | None = None,
    allow_test_packs: bool = False,
    allow_unpinned: bool = False,
    environment: str = "production",
) -> CompanyCalendarSettings:
    """Pack defaults plus `company.locale` overrides, validated by the pack framework (fail closed).

    Pack and override errors (`CountryPackError` subclasses) propagate unchanged. Keys of `company_locale`
    outside this module's scope (fiscal year, holidays) are validated by the framework and left to their owners.
    """
    pack = resolve_country_pack(
        country_code, packs_dir, company_locale, version=version, pack_id=pack_id,
        allow_test_packs=allow_test_packs, allow_unpinned=allow_unpinned, environment=environment,
    )
    loc = pack["locale"]
    reduced = tuple(
        ReducedPeriod(
            id=rp["id"], labels=MappingProxyType(dict(rp["labels"])), rule=rp.get("rule", "ramadan"), hours=_hours(rp["hours"]),
            gregorian_from=date.fromisoformat(rp["gregorianFrom"]) if "gregorianFrom" in rp else None,
            gregorian_to=date.fromisoformat(rp["gregorianTo"]) if "gregorianTo" in rp else None,
        )
        for rp in loc["workingTime"].get("reducedPeriods", [])
    )
    return CompanyCalendarSettings(
        country_code=pack["countryCode"],
        pack_id=pack["packId"],
        pack_version=pack["version"],
        evidence_status=pack["evidenceStatus"],
        timezone=loc["timezone"],
        week_start=loc["week"]["startDay"],
        weekend_days=tuple(loc["week"]["weekendDays"]),
        work_days=tuple(loc["workingTime"]["workDays"]),
        hours=_hours(loc["workingTime"]["hours"]),
        reduced_periods=reduced,
        number_system=loc["numberSystem"],
        applied_overrides=tuple(pack["appliedOverrides"]),
    )
