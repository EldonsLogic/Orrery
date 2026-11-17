"""Loader and site synchronization for core.trading_ar (ERP-006)."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

PACKAGE_DIR = Path(__file__).resolve().parent
TRANSLATIONS_PATH = PACKAGE_DIR / "translations.json"

EXPECTED_TRANSLATABLE_COUNT = 107
EXPECTED_EXCLUDED_COUNT = 45

_NAMING_SERIES_RE = re.compile(r"^[A-Z0-9-]+\.(?:YYYY|YY|MM|DD|#+)\.?-?$")
_NUMBER_FORMAT_RE = re.compile(r"^#[#.,' ]+$")
_ARABIC_CHAR_RE = re.compile(r"[\u0600-\u06FF]")


def load_pack(path: Path | None = None) -> dict[str, Any]:
    """Load and validate the translation pack JSON payload."""
    target = path or TRANSLATIONS_PATH
    data = json.loads(target.read_text(encoding="utf-8"))
    if data.get("language") != "ar":
        raise ValueError(f"Expected language 'ar', got {data.get('language')!r}")

    entries = data.get("entries")
    if not isinstance(entries, list) or len(entries) != EXPECTED_TRANSLATABLE_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_TRANSLATABLE_COUNT} translatable entries, "
            f"got {len(entries) if isinstance(entries, list) else type(entries).__name__}"
        )

    excluded = data.get("excluded") or {}
    excluded_flat: list[str] = []
    for key in (
        "namingSeriesPatterns",
        "numberFormats",
        "barcodeTypes",
        "valuationMethods",
        "internalTreeFields",
    ):
        vals = excluded.get(key, [])
        if not isinstance(vals, list):
            raise ValueError(f"excluded.{key} must be a list")
        excluded_flat.extend(vals)
    if len(excluded_flat) != EXPECTED_EXCLUDED_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_EXCLUDED_COUNT} excluded patterns, got {len(excluded_flat)}"
        )

    seen: set[str] = set()
    for entry in entries:
        src = entry.get("source")
        tr = entry.get("translation")
        if not isinstance(src, str) or not src or src != src.strip():
            raise ValueError(f"Invalid source string (empty or unstripped): {src!r}")
        if src in seen:
            raise ValueError(f"Duplicate source string in pack: {src!r}")
        seen.add(src)
        if is_excluded_source(src, excluded_set=set(excluded_flat)):
            raise ValueError(f"Excluded code/format string must not be translated: {src!r}")
        if not isinstance(tr, str) or not tr.strip() or tr == src or not _ARABIC_CHAR_RE.search(tr):
            raise ValueError(f"Translation for {src!r} must be non-empty Arabic text")

    return data


def load_translations(path: Path | None = None) -> dict[str, str]:
    """Return a validated mapping of English source_text -> Arabic translated_text."""
    pack = load_pack(path)
    return {entry["source"]: entry["translation"] for entry in pack["entries"]}


def is_excluded_source(text: str, excluded_set: set[str] | None = None) -> bool:
    """Return True for non-translatable naming series, number formats, barcode types, FIFO/LIFO, Lft/Rgt."""
    stripped = text.strip()
    if excluded_set is None:
        pack = json.loads(TRANSLATIONS_PATH.read_text(encoding="utf-8"))
        excluded = pack.get("excluded") or {}
        excluded_set = {
            item
            for items in excluded.values()
            if isinstance(items, list)
            for item in items
        }
    if stripped in excluded_set:
        return True
    if _NAMING_SERIES_RE.fullmatch(stripped):
        return True
    if _NUMBER_FORMAT_RE.fullmatch(stripped):
        return True
    return False


def apply_trading_ar_translations(
    dry_run: bool = False,
    frappe_module: Any = None,
) -> dict[str, Any]:
    """Idempotently upsert the 107 Arabic Translation records onto the connected Frappe site.

    Never writes records for excluded codes, naming series, or number formats.
    """
    if frappe_module is None:
        import frappe as frappe_module  # type: ignore[no-redef]

    translations = load_translations()
    created = 0
    updated = 0
    unchanged = 0
    skipped_excluded = 0

    existing_rows = frappe_module.get_all(
        "Translation",
        filters={"language": "ar"},
        fields=["name", "source_text", "translated_text", "context"],
    )
    by_source: dict[str, dict[str, Any]] = {}
    for row in existing_rows:
        if not row.get("context"):
            by_source[row["source_text"]] = row

    for source_text, translated_text in translations.items():
        if is_excluded_source(source_text):
            skipped_excluded += 1
            continue

        existing = by_source.get(source_text)
        if existing is None:
            created += 1
            if not dry_run:
                doc = frappe_module.get_doc(
                    {
                        "doctype": "Translation",
                        "language": "ar",
                        "source_text": source_text,
                        "translated_text": translated_text,
                    }
                )
                doc.insert(ignore_permissions=True)
        elif existing.get("translated_text") != translated_text:
            updated += 1
            if not dry_run:
                frappe_module.db.set_value(
                    "Translation",
                    existing["name"],
                    "translated_text",
                    translated_text,
                )
        else:
            unchanged += 1

    if not dry_run and (created or updated):
        frappe_module.db.commit()
        if hasattr(frappe_module, "translate") and hasattr(frappe_module.translate, "clear_cache"):
            frappe_module.translate.clear_cache()

    return {
        "language": "ar",
        "total": len(translations),
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "skipped_excluded": skipped_excluded,
        "dry_run": dry_run,
    }
