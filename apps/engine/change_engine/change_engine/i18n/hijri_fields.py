"""Declarative companion fields and validation sync; no DDL or privileged writes.

Install definitions only through the existing reviewed configuration/apply path.
Consumers can derive on render without persisting companions. Gregorian source
fields remain authoritative; companions are read-only Data, never Date columns.
"""

from .hijri import HijriDateError, MESSAGES, to_hijri

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


def derive_companions(doc) -> dict[str, str]:
    """Derive display values from canonical sources for render, without mutating doc."""
    return {f"custom_{source}_hijri": to_hijri(value) if value not in (None, "") else ""
            for source in TRADING_DATES.get(_get(doc, "doctype"), ())
            for value in [_get(doc, source)]}


def sync_companions(doc, method=None) -> None:
    """Lifecycle hook: atomically derive installed companions before saving.

    Unconfigured documents need no conversion and remain untouched. Permissions
    and transactions stay with the calling lifecycle; this hook never saves or
    commits, and does not install fields or alter canonical date sources.
    """
    meta = getattr(doc, "meta", None)
    sources = [source for source in TRADING_DATES.get(_get(doc, "doctype"), ())
               if meta is not None and meta.has_field(f"custom_{source}_hijri")]
    values = {f"custom_{source}_hijri": to_hijri(value) if value not in (None, "") else ""
              for source in sources for value in [_get(doc, source)]}
    for field, value in values.items():
        setattr(doc, field, value)
