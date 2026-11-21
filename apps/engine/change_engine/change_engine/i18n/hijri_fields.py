"""Declarative companion fields and validation sync; no DDL or privileged writes.

Install definitions only through the existing reviewed configuration/apply path.
Consumers can derive on render without persisting companions. Gregorian source
fields remain authoritative; companions are read-only Data, never Date columns.
"""

from datetime import datetime
import logging
import re

try:
    import frappe
except ImportError:
    frappe = None

from .hijri import HijriDateError, MESSAGES, to_hijri

_log = logging.getLogger(__name__)
_DATETIME_STR = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}"
    r"(?::[0-9]{2}(?:\.[0-9]{1,6})?)?(?:Z|[+-][0-9]{2}:[0-9]{2})?"
)

TRADING_DATES = {
    "Sales Invoice": ("posting_date", "due_date"),
    "Purchase Invoice": ("posting_date", "due_date", "bill_date"),
    "Sales Order": ("transaction_date", "delivery_date"),
    "Purchase Order": ("transaction_date", "schedule_date"),
    "Quotation": ("transaction_date", "valid_till"),
    "Delivery Note": ("posting_date",),
    "Purchase Receipt": ("posting_date",),
    "Payment Entry": ("posting_date",),
    "Stock Entry": ("posting_date",),
}


def companion_fields(doctype: str, *, language: str = "en") -> list[dict]:
    """Return custom-field definitions for reviewed installation (Arabic unreviewed)."""
    if language not in ("ar", "en") or doctype not in TRADING_DATES:
        raise HijriDateError("invalid_locale")
    return [{"fieldname": f"custom_{source}_hijri", "fieldtype": "Data",
             "label": MESSAGES["companion_label"][language], "insert_after": source,
             "read_only": 1, "no_copy": 1, "print_hide": 1, "allow_on_submit": 1}
            for source in TRADING_DATES[doctype]]


def _get(doc, key):
    return doc.get(key) if isinstance(doc, dict) else getattr(doc, key, None)


def _is_datetime_value(value) -> bool:
    """Return True when a Date field holds a Python datetime or valid ISO/engine timestamp."""
    if isinstance(value, datetime):
        return True
    if not isinstance(value, str) or not _DATETIME_STR.fullmatch(value):
        return False
    try:
        datetime.fromisoformat(value)
        return True
    except ValueError:
        return False


def _companion_value(doctype: str, source: str, value) -> str:
    """Hijri display for one source date, empty when there is nothing safe to show.

    Far-future sentinels (2099-12-31), legacy dates outside the calendar tables, and
    datetime values in a source Date field leave the display empty and log the field,
    never the value. Malformed values, a missing converter and other failures still propagate.
    """
    if value in (None, ""):
        return ""
    if _is_datetime_value(value):
        _log.warning("Hijri companion left empty: %s.%s holds a datetime value", doctype, source)
        return ""
    try:
        return to_hijri(value)
    except HijriDateError as error:
        if error.code != "calendar_range":
            raise
        _log.warning("Hijri companion left empty: %s.%s outside Umm al-Qura range", doctype, source)
        return ""


def derive_companions(doc) -> dict[str, str]:
    """Derive display values from canonical sources for render, without mutating doc."""
    doctype = _get(doc, "doctype")
    return {f"custom_{source}_hijri": _companion_value(doctype, source, _get(doc, source))
            for source in TRADING_DATES.get(doctype, ())}


def sync_companions(doc, method=None) -> None:
    """Lifecycle hook: atomically derive installed companions before saving.

    Unconfigured documents need no conversion and remain untouched. Permissions
    and transactions stay with the calling lifecycle; this hook never saves or
    commits, and does not install fields or alter canonical date sources.
    """
    meta = getattr(doc, "meta", None)
    doc_type = _get(doc, "doctype")
    sources = [source for source in TRADING_DATES.get(doc_type, ())
               if meta is not None and meta.has_field(f"custom_{source}_hijri")]
    try:
        values = {f"custom_{source}_hijri": _companion_value(doc_type, source, _get(doc, source))
                  for source in sources}
    except HijriDateError as error:
        if frappe is None:
            raise
        # Engine saves get a translated Frappe ValidationError, not a raw ValueError.
        lang = str(getattr(getattr(frappe, "local", None), "lang", "en") or "en")
        frappe.throw(error.message("ar" if lang.startswith("ar") else "en"))
        raise
    for field, value in values.items():
        setattr(doc, field, value)
