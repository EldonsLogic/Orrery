"""Rerunnable Arabic translation audit and sync for ERP-006 trading scope."""

from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Any

AREA_DOCTYPES: dict[str, tuple[str, ...]] = {
    "Selling": (
        "Customer",
        "Customer Credit Limit",
        "Sales Order",
        "Sales Order Item",
        "Quotation",
        "Quotation Item",
        "Sales Team",
        "Selling Settings",
    ),
    "Buying": (
        "Supplier",
        "Purchase Order",
        "Purchase Order Item",
        "Buying Settings",
    ),
    "Stock": (
        "Item",
        "Item Barcode",
        "Item Default",
        "Item Tax",
        "UOM Conversion Detail",
        "Item Price",
        "Price List",
        "Warehouse",
        "Delivery Note",
        "Delivery Note Item",
        "Purchase Receipt",
        "Purchase Receipt Item",
        "Stock Entry",
        "Stock Entry Detail",
        "Stock Entry Type",
        "Stock Reconciliation",
        "Stock Reconciliation Item",
        "Material Request",
        "Material Request Item",
        "Stock Ledger Entry",
        "Bin",
        "Stock Settings",
    ),
    "Accounts": (
        "Account",
        "Sales Invoice",
        "Sales Invoice Item",
        "Sales Taxes and Charges",
        "Sales Invoice Advance",
        "Purchase Invoice",
        "Purchase Invoice Item",
        "Purchase Taxes and Charges",
        "Purchase Invoice Advance",
        "Payment Entry",
        "Payment Entry Reference",
        "Payment Entry Deduction",
        "Journal Entry",
        "Journal Entry Account",
        "GL Entry",
        "Payment Ledger Entry",
        "Fiscal Year",
        "Accounting Period",
        "Period Closing Voucher",
        "Sales Taxes and Charges Template",
        "Purchase Taxes and Charges Template",
        "Item Tax Template",
        "Tax Category",
        "Tax Rule",
        "Mode of Payment",
        "Bank",
        "Bank Account",
        "Bank Transaction",
        "Bank Reconciliation Tool",
        "Bank Statement Import",
        "Payment Term",
        "Payment Terms Template",
        "Cost Center",
        "Pricing Rule",
        "Exchange Rate Revaluation",
        "Accounts Settings",
    ),
    "Setup and masters": (
        "Company",
        "Global Defaults",
        "UOM",
        "UOM Conversion Factor",
        "Item Group",
        "Customer Group",
        "Supplier Group",
        "Territory",
        "Brand",
        "Sales Person",
        "Sales Partner",
        "Holiday List",
        "Currency Exchange",
        "Country",
        "Currency",
        "Address",
        "Contact",
        "Terms and Conditions",
    ),
}

TRADING_IN_SCOPE_DOCTYPES: tuple[str, ...] = tuple(
    dt for dts in AREA_DOCTYPES.values() for dt in dts
)

TRADING_IN_SCOPE_REPORTS: tuple[str, ...] = (
    "General Ledger",
    "Trial Balance",
    "Accounts Receivable",
    "Accounts Receivable Summary",
    "Accounts Payable",
    "Accounts Payable Summary",
    "Profit and Loss Statement",
    "Balance Sheet",
    "Cash Flow",
    "Sales Register",
    "Item-wise Sales Register",
    "Purchase Register",
    "Item-wise Purchase Register",
    "Customer Ledger Summary",
    "Supplier Ledger Summary",
    "Gross Profit",
    "Delivered Items To Be Billed",
    "Received Items To Be Billed",
    "Bank Reconciliation Statement",
    "Stock Ledger",
    "Stock Balance",
    "Stock and Account Value Comparison",
    "Stock Projected Qty",
    "Item Shortage Report",
    "Stock Ageing",
    "Batch-Wise Balance History",
    "Sales Order Analysis",
    "Customer Credit Balance",
    "Sales Person-wise Transaction Summary",
    "Purchase Order Analysis",
    "Procurement Tracker",
)


def _get_components_loader():
    from . import _ensure_components_on_path

    _ensure_components_on_path()
    from components.core.trading_ar import loader

    return loader


def _default_bench_root() -> Path:
    exe = Path(sys.executable).resolve()
    if len(exe.parents) >= 3 and (exe.parents[2] / "apps").is_dir():
        return exe.parents[2]
    cwd = Path.cwd().resolve()
    if cwd.name == "sites" and (cwd.parent / "apps").is_dir():
        return cwd.parent
    return cwd


def load_po_arabic_map(bench_root: Path | None = None) -> dict[str, str]:
    """Read shipped non-fuzzy ar.po catalogues matching Section 2 of arabic-translation-gap-trading.md."""
    from babel.messages.pofile import read_po

    root = bench_root or _default_bench_root()
    po_files = (
        root / "apps" / "frappe" / "frappe" / "locale" / "ar.po",
        root / "apps" / "erpnext" / "erpnext" / "locale" / "ar.po",
        root / "apps" / "hrms" / "hrms" / "locale" / "ar.po",
    )
    po_map: dict[str, str] = {}
    for po_path in po_files:
        if not po_path.is_file():
            continue
        with po_path.open("rb") as fh:
            for msg in read_po(fh):
                if not msg.id or msg.context or msg.pluralizable or msg.fuzzy:
                    continue
                if (
                    isinstance(msg.id, str)
                    and isinstance(msg.string, str)
                    and msg.string.strip()
                    and msg.string != msg.id
                ):
                    po_map[msg.id] = msg.string
    return po_map


def extract_doctype_strings(meta: Any, doctype_name: str) -> set[str]:
    """Extract unique stripped UI strings for a single DocType per Section 2 of the audit spec."""
    strings: set[str] = {doctype_name}
    for df in getattr(meta, "fields", ()):
        if getattr(df, "fieldtype", None) not in ("Column Break", "Fold") and getattr(df, "label", None):
            cleaned = df.label.strip()
            if cleaned:
                strings.add(cleaned)
        desc = getattr(df, "description", None)
        if desc and len(desc) < 300:
            cleaned = desc.strip()
            if cleaned:
                strings.add(cleaned)
        if getattr(df, "fieldtype", None) == "Select" and getattr(df, "options", None):
            for opt in df.options.split("\n"):
                cleaned = opt.strip()
                if cleaned and not cleaned.isdigit():
                    strings.add(cleaned)
    return strings


def check_excluded_site_translations(frappe_module: Any = None) -> list[str]:
    """Return any site Translation records for language='ar' that translate excluded codes/formats."""
    if frappe_module is None:
        import frappe as frappe_module  # type: ignore[no-redef]
    loader = _get_components_loader()
    rows = frappe_module.get_all(
        "Translation",
        filters={"language": "ar"},
        fields=["source_text", "translated_text"],
    )
    violations: list[str] = []
    for row in rows:
        src = (row.get("source_text") or "").strip()
        if src and loader.is_excluded_source(src):
            violations.append(src)
    return sorted(set(violations))


def check_rtl_support(frappe_module: Any = None, bench_root: Path | None = None) -> dict[str, Any]:
    """Verify Arabic Language enablement, Jinja RTL detection, and compiled locale path availability."""
    if frappe_module is None:
        import frappe as frappe_module  # type: ignore[no-redef]
    root = bench_root or _default_bench_root()
    lang_doc = frappe_module.db.get_value(
        "Language",
        "ar",
        ["language_code", "language_name", "enabled"],
        as_dict=True,
    )

    rtl_active = False
    try:
        from frappe.utils.jinja_globals import is_rtl

        prev_lang = getattr(frappe_module.local, "lang", None)
        try:
            frappe_module.local.lang = "ar"
            rtl_active = bool(is_rtl())
        finally:
            frappe_module.local.lang = prev_lang
    except ImportError:
        rtl_active = False

    locale_dir = root / "sites" / "assets" / "locale" / "ar" / "LC_MESSAGES"
    runtime_app_strings = 0
    if hasattr(frappe_module, "translate") and hasattr(frappe_module.translate, "get_translations_from_apps"):
        runtime_app_strings = len(frappe_module.translate.get_translations_from_apps("ar") or {})

    return {
        "language_enabled": bool(lang_doc and lang_doc.get("enabled")),
        "rtl_active": rtl_active,
        "sites_assets_locale_ar_exists": locale_dir.is_dir(),
        "runtime_app_strings": runtime_app_strings,
    }


def audit_trading_arabic_coverage(
    frappe_module: Any = None,
    include_site_translations: bool = True,
    bench_root: Path | None = None,
    po_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run the ERP-006 Arabic translation gap & RTL readiness audit against the connected site."""
    if frappe_module is None:
        import frappe as frappe_module  # type: ignore[no-redef]

    loader = _get_components_loader()
    po_translations = po_map if po_map is not None else load_po_arabic_map(bench_root=bench_root)

    site_translations: dict[str, str] = {}
    if include_site_translations:
        for row in frappe_module.get_all(
            "Translation",
            filters={"language": "ar"},
            fields=["source_text", "translated_text", "context"],
        ):
            if row.get("context"):
                continue
            src = (row.get("source_text") or "").strip()
            tr = row.get("translated_text") or ""
            if src and tr.strip() and tr != src:
                site_translations[src] = tr

    combined = dict(po_translations)
    combined.update(site_translations)

    unique_all: set[str] = set()
    by_area: dict[str, dict[str, Any]] = {}
    missing_by_string: dict[str, list[str]] = {}

    for area, doctypes in AREA_DOCTYPES.items():
        area_total = 0
        area_covered = 0
        area_missing_all = 0
        area_excluded = 0
        area_missing_translatable = 0
        for dt in doctypes:
            meta = frappe_module.get_meta(dt)
            strs = extract_doctype_strings(meta, dt)
            unique_all |= strs
            area_total += len(strs)
            for s in strs:
                if s in combined:
                    area_covered += 1
                else:
                    area_missing_all += 1
                    missing_by_string.setdefault(s, [])
                    if dt not in missing_by_string[s]:
                        missing_by_string[s].append(dt)
                    if loader.is_excluded_source(s):
                        area_excluded += 1
                    else:
                        area_missing_translatable += 1
        area_translatable = area_total - area_excluded
        area_translatable_covered = area_covered
        by_area[area] = {
            "strings": area_total,
            "covered": area_covered,
            "missing_all": area_missing_all,
            "excluded": area_excluded,
            "missing_translatable": area_missing_translatable,
            "translatable_coverage_pct": round(
                (100.0 * area_translatable_covered / area_translatable) if area_translatable else 100.0,
                1,
            ),
        }

    missing_excluded = sorted(s for s in missing_by_string if loader.is_excluded_source(s))
    missing_translatable = sorted(s for s in missing_by_string if not loader.is_excluded_source(s))
    covered_unique = len(unique_all) - len(missing_by_string)
    translatable_total = len(unique_all) - len(missing_excluded)
    translatable_covered = covered_unique

    missing_reports = [r for r in TRADING_IN_SCOPE_REPORTS if r not in combined]
    excluded_site_violations = check_excluded_site_translations(frappe_module=frappe_module)
    rtl_info = check_rtl_support(frappe_module=frappe_module, bench_root=bench_root)

    return {
        "unique_strings_total": len(unique_all),
        "po_covered_unique": sum(1 for s in unique_all if s in po_translations),
        "site_covered_unique": len(site_translations),
        "covered_unique": covered_unique,
        "missing_all_unique": len(missing_by_string),
        "missing_excluded_unique": len(missing_excluded),
        "missing_translatable_unique": len(missing_translatable),
        "translatable_total": translatable_total,
        "translatable_covered": translatable_covered,
        "translatable_coverage_pct": round(
            (100.0 * translatable_covered / translatable_total) if translatable_total else 100.0,
            1,
        ),
        "by_area": by_area,
        "reports_total": len(TRADING_IN_SCOPE_REPORTS),
        "reports_translated": len(TRADING_IN_SCOPE_REPORTS) - len(missing_reports),
        "reports_missing": missing_reports,
        "excluded_site_translations": excluded_site_violations,
        "missing_translatable_strings": missing_translatable,
        "rtl_and_runtime": rtl_info,
    }


def sync_trading_arabic_translations(
    dry_run: bool = False,
    frappe_module: Any = None,
) -> dict[str, Any]:
    """Synchronize the 107 trading Arabic Translation records onto the connected site."""
    loader = _get_components_loader()
    return loader.apply_trading_ar_translations(dry_run=dry_run, frappe_module=frappe_module)
