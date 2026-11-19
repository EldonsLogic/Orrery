"""Strict Umm al-Qura entry/display boundary (ADR-0015, RULES 31).

The pinned MIT hijridate tables are the sole converter. No network, approximation,
moon-sighting inference or accounting rules. Arabic copy awaits ADR-0033 review.
"""

from dataclasses import dataclass
from datetime import date
import re

_ISO = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_ARABIC_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
# Covers month names, labels and errors; only native review may change this status.
ARABIC_COPY_REVIEW_STATUS = "unreviewed"
# Catalogue keys are safe for gateway i18n; never interpolate untrusted input/errors.
MESSAGES = {
    "invalid_date": {"en": "Enter a valid date as YYYY-MM-DD with an explicit calendar.",
                     "ar": "أدخل تاريخًا صالحًا بصيغة YYYY-MM-DD مع تحديد التقويم."},
    "calendar_range": {"en": "Date is outside the supported Umm al-Qura calendar range.",
                       "ar": "التاريخ خارج نطاق تقويم أم القرى المدعوم."},
    "calendar_unavailable": {"en": "Calendar conversion is unavailable.",
                             "ar": "تحويل التقويم غير متاح."},
    "invalid_locale": {"en": "Unsupported calendar display settings.",
                       "ar": "إعدادات عرض التقويم غير مدعومة."},
    "companion_label": {"en": "Hijri Date (Umm al-Qura)", "ar": "التاريخ الهجري (أم القرى)"},
}


class HijriDateError(ValueError):
    """Stable, localisable failure without dependency or customer data leakage."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(self.message("en"))

    def message(self, language: str) -> str:
        """Return catalogue text; Arabic remains unreviewed under ADR-0033."""
        return MESSAGES[self.code][language]


def _library():
    """Load only the installed pinned converter; fail closed if it is absent."""
    try:
        from hijridate import Gregorian, Hijri
    except ImportError:
        raise HijriDateError("calendar_unavailable") from None
    return Gregorian, Hijri


def _parts(value: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or not _ISO.fullmatch(value):
        raise HijriDateError("invalid_date")
    return tuple(map(int, value.split("-")))


def canonical_date(value: date | str) -> str:
    """Accept an exact date or canonical ASCII ISO string, never a timestamp."""
    if type(value) is date:
        return value.isoformat()
    parts = _parts(value)
    try:
        return date(*parts).isoformat()
    except ValueError:
        raise HijriDateError("invalid_date") from None


def to_hijri(value: date | str) -> str:
    """Convert canonical Gregorian input to a computed Hijri ISO display value."""
    canonical = canonical_date(value)
    Gregorian, _ = _library()
    try:
        return Gregorian(*_parts(canonical)).to_hijri().isoformat()
    except OverflowError:
        raise HijriDateError("calendar_range") from None
    except ValueError:
        raise HijriDateError("invalid_date") from None


def normalise_date(value: str, *, calendar: str) -> str:
    """Parse explicit year-month-day entry, normalise both Arabic digit sets to ISO.

    Calendar inference, D/M/Y, whitespace and bidi controls are refused. The result
    is always Gregorian; the canonical storage boundary never accepts local digits.
    """
    if not isinstance(value, str) or calendar not in ("gregorian", "hijri_umm_al_qura"):
        raise HijriDateError("invalid_date")
    normalised = value.translate(_DIGITS)
    if calendar == "gregorian":
        return canonical_date(normalised)
    parts = _parts(normalised)
    _, Hijri = _library()
    try:
        return Hijri(*parts).to_gregorian().isoformat()
    except OverflowError:
        raise HijriDateError("calendar_range") from None
    except ValueError:
        raise HijriDateError("invalid_date") from None


def localise_digits(value: str, number_system: str) -> str:
    """Use the Blueprint numberSystem vocabulary; reject unknown digit settings."""
    if number_system not in ("western", "eastern_arabic"):
        raise HijriDateError("invalid_locale")
    return value.translate(_ARABIC_DIGITS) if number_system == "eastern_arabic" else value


@dataclass(frozen=True)
class HijriDisplay:
    """Isolated display text with conversion provenance and Arabic review status."""

    text: str
    review_status: str
    source: str = "computed"


def format_hijri(value: date | str, *, language: str = "ar",
                 number_system: str = "western") -> HijriDisplay:
    """Format using the pinned calendar's month-name catalogue, isolated for RTL.

    Arabic wording is unreviewed; library table accuracy remains UNVERIFIED against
    the official Saudi calendar (CMP-022). Never use display text as a stored date.
    """
    if language not in ("ar", "en"):
        raise HijriDateError("invalid_locale")
    iso = to_hijri(value)
    _, Hijri = _library()
    year, month, day = _parts(iso)
    text = localise_digits(f"{day} {Hijri(year, month, day).month_name(language)} {year}", number_system)
    return HijriDisplay(("\u2067" if language == "ar" else "\u2066") + text + "\u2069",
                        ARABIC_COPY_REVIEW_STATUS if language == "ar" else "not_required")


def display_enabled(locale: dict, compliance_profile: dict, *, country_default: bool) -> bool:
    """Resolve existing Blueprint display settings; a required profile wins."""
    if not isinstance(locale, dict) or not isinstance(compliance_profile, dict):
        raise HijriDateError("invalid_locale")
    calendar = locale.get("calendar", {})
    profile = compliance_profile.get("hijriDisplay", {})
    if not isinstance(calendar, dict) or not isinstance(profile, dict):
        raise HijriDateError("invalid_locale")
    primary = calendar.get("primary", "gregorian")
    secondary = calendar.get("secondaryDisplay", "none")
    if (primary not in ("gregorian", "hijri_umm_al_qura")
            or secondary not in ("none", "gregorian", "hijri_umm_al_qura")
            or ("enabled" in profile and type(profile["enabled"]) is not bool)):
        raise HijriDateError("invalid_locale")
    return (profile.get("enabled", False) or primary == "hijri_umm_al_qura"
            or secondary == "hijri_umm_al_qura"
            or (country_default and not calendar and "enabled" not in profile))
