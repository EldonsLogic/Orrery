"""Umm al-Qura date conversion for engine consumers.

Gregorian dates remain the stored values. The Hijri ISO-like string is a calendar
display value, not a Gregorian date or a time-zone-bearing timestamp.
"""

from datetime import date

from .i18n.hijri import HijriDateError, normalise_date, to_hijri


def hijri_to_gregorian(year: int, month: int, day: int) -> date:
    """Convert a valid Umm al-Qura date to the canonical Gregorian date.

    Raise ValueError for invalid dates and dates outside the library's tables.
    """
    if any(type(part) is not int for part in (year, month, day)):
        raise HijriDateError("invalid_date")
    return date.fromisoformat(normalise_date(f"{year:04d}-{month:02d}-{day:02d}", calendar="hijri_umm_al_qura"))


def gregorian_to_hijri(value: date) -> str:
    """Return a zero-padded Hijri date; reject timestamps and unsupported dates."""
    if type(value) is not date:
        raise TypeError("value must be a Gregorian date, not a timestamp")
    return to_hijri(value)
