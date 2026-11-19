"""Umm al-Qura date conversion for engine consumers.

Gregorian dates remain the stored values. The Hijri ISO-like string is a calendar
display value, not a Gregorian date or a time-zone-bearing timestamp.
"""

from datetime import date

from hijridate import Gregorian, Hijri


def hijri_to_gregorian(year: int, month: int, day: int) -> date:
    """Convert a valid Umm al-Qura date to the canonical Gregorian date.

    Raise ValueError for invalid dates and dates outside the library's tables.
    """
    try:
        return Hijri(year, month, day).to_gregorian()
    except OverflowError as exc:
        raise ValueError(str(exc)) from exc


def gregorian_to_hijri(value: date) -> str:
    """Return a zero-padded Hijri date; reject timestamps and unsupported dates."""
    if type(value) is not date:
        raise TypeError("value must be a Gregorian date, not a timestamp")
    try:
        return Gregorian(value.year, value.month, value.day).to_hijri().isoformat()
    except OverflowError as exc:
        raise ValueError(str(exc)) from exc
