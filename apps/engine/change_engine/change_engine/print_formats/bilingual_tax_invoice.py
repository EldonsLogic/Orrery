"""Bilingual (Arabic/English, RTL) tax invoice HTML and PDF print format (ERP-007).

Supports two explicit modes:
- ``zatca_sa``: Saudi ZATCA Phase 1 tax invoice / simplified invoice / credit & debit notes.
  Validates strictly via ``change_engine.compliance.generate_phase1_invoice`` (CMP-003),
  fails closed on missing fields or engine total mismatches (ADR-0031), and embeds the
  5-tag TLV QR code inside a mandatory white clear zone (>= 4 mm).
- ``neutral``: Country-neutral bilingual invoice (Phase 1A golden path / Qatar / non-ZATCA).
  Has zero runtime dependency on country-specific compliance modules while still enforcing
  engine total consistency (ADR-0031) and full Arabic/English RTL layout parity.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
import html
import json
import re
from typing import Any, Mapping

from .qr_svg import render_qr_svg

DEFAULT_BRANDING_PRIMARY = "#2443D0"
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_DATA_IMAGE_URI_RE = re.compile(
    r"^data:image/(png|jpeg|jpg);base64,([A-Za-z0-9+/=\s]+)$",
    re.IGNORECASE,
)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_KSA_VAT_RE = re.compile(r"^3\d{13}3$")
_MAX_LOGO_BYTES = 2 * 1024 * 1024
_TWO_DECIMALS = Decimal("0.01")
_ZERO = Decimal("0.00")

_COUNTRY_CODES: dict[str, str] = {
    "sa": "SA",
    "saudi arabia": "SA",
    "kingdom of saudi arabia": "SA",
    "qa": "QA",
    "qatar": "QA",
    "ae": "AE",
    "uae": "AE",
    "united arab emirates": "AE",
    "eg": "EG",
    "egypt": "EG",
}

# Bilingual labels aligned with components/core/trading_ar/translations.json (ERP-006)
# and docs/brand/05-bilingual-rtl.md (equal size and weight, Arabic right, English left).
BILINGUAL_LABELS: dict[str, tuple[str, str]] = {
    "seller": ("المورّد / البائع", "Seller"),
    "customer": ("العميل", "Customer"),
    "invoice_number": ("رقم الفاتورة", "Invoice Number"),
    "issue_date": ("تاريخ الإصدار", "Issue Date"),
    "issue_time": ("وقت الإصدار", "Issue Time"),
    "hijri_date": ("التاريخ الهجري", "Hijri Date"),
    "currency": ("العملة", "Currency"),
    "vat_number": ("الرقم الضريبي", "VAT Number"),
    "cr_number": ("السجل التجاري", "CR Number"),
    "address": ("العنوان", "Address"),
    "invoice_type": ("نوع الفاتورة", "Invoice Type"),
    "preceding_invoice": ("مرجع الفاتورة السابقة", "Preceding Invoice Reference"),
    "amendment_reason": ("سبب التعديل", "Amendment Reason"),
    "line_no": ("#", "#"),
    "item_code": ("رمز الصنف", "Item Code"),
    "description": ("الوصف", "Description"),
    "quantity": ("الكمية", "Qty"),
    "unit_price": ("سعر الوحدة", "Unit Price"),
    "discount": ("الخصم", "Discount"),
    "vat_rate": ("نسبة الضريبة", "VAT %"),
    "vat_category": ("فئة الضريبة", "VAT Category"),
    "line_amount": ("المبلغ", "Amount"),
    "total_taxable_amount": ("الإجمالي الخاضع للضريبة", "Total Taxable Amount"),
    "total_vat_amount": ("إجمالي ضريبة القيمة المضافة", "Total VAT"),
    "grand_total": ("الإجمالي النهائي", "Grand Total"),
    "notes": ("ملاحظات", "Notes"),
    "qr_caption": ("رمز الاستجابة السريعة للفاتورة الإلكترونية", "E-Invoice QR Code"),
    "standard_badge": ("فاتورة ضريبية (B2B)", "Standard (B2B)"),
    "simplified_badge": ("فاتورة ضريبية مبسطة (B2C)", "Simplified (B2C)"),
    "neutral_badge": ("فاتورة مبيعات", "Sales Invoice"),
}

_DOC_TITLES: dict[tuple[str, str], tuple[str, str]] = {
    ("zatca_sa", "tax_invoice"): ("فاتورة ضريبية", "Tax Invoice"),
    ("zatca_sa", "simplified_tax_invoice"): ("فاتورة ضريبية مبسطة", "Simplified Tax Invoice"),
    ("zatca_sa", "credit_note"): ("إشعار دائن ضريبي", "Tax Credit Note"),
    ("zatca_sa", "debit_note"): ("إشعار مدين ضريبي", "Tax Debit Note"),
    ("neutral", "credit_note"): ("إشعار دائن", "Credit Note"),
    ("neutral", "debit_note"): ("إشعار مدين", "Debit Note"),
}

_VAT_CATEGORY_LABELS: dict[str, tuple[str, str]] = {
    "S": ("خاضع للضريبة الأساسية (S)", "Standard Rate (S)"),
    "Z": ("خاضع لنسبة الصفر (Z)", "Zero-rated (Z)"),
    "E": ("معفى من الضريبة (E)", "Exempt (E)"),
    "O": ("خارج نطاق الضريبة (O)", "Out of Scope (O)"),
}


@dataclass(frozen=True)
class InvoiceBranding:
    """Tenant branding overrides constrained by docs/brand/12-tenant-theming.md."""

    display_name: dict[str, str] | str | None = None
    primary_color: str = DEFAULT_BRANDING_PRIMARY
    logo_data_uri: str | None = None
    mono_logo: bool = False
    remove_powered_by: bool = False


@dataclass(frozen=True)
class ResolvedBranding:
    display_name_ar: str | None
    display_name_en: str | None
    primary_color: str
    logo_data_uri: str | None
    mono_logo: bool
    remove_powered_by: bool


def _srgb_channel_to_linear(channel: int) -> float:
    s = channel / 255.0
    return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4


def contrast_ratio_on_white(hex_color: str) -> float:
    """Compute WCAG 2.x contrast ratio of `#RRGGBB` against `#FFFFFF`."""
    if not isinstance(hex_color, str) or not _HEX_COLOR_RE.fullmatch(hex_color.strip()):
        raise ValueError(f"Invalid hex color '{hex_color}'; expected '#RRGGBB'")
    cleaned = hex_color.strip()
    r = int(cleaned[1:3], 16)
    g = int(cleaned[3:5], 16)
    b = int(cleaned[5:7], 16)
    lum = (
        0.2126 * _srgb_channel_to_linear(r)
        + 0.7152 * _srgb_channel_to_linear(g)
        + 0.0722 * _srgb_channel_to_linear(b)
    )
    return (1.0 + 0.05) / (lum + 0.05)


def _sanitize_logo_data_uri(uri: str | None) -> str | None:
    if uri is None or uri == "":
        return None
    if not isinstance(uri, str):
        raise ValueError("logo_data_uri must be a string")
    stripped = uri.strip()
    match = _DATA_IMAGE_URI_RE.fullmatch(stripped)
    if not match:
        raise ValueError(
            "logo_data_uri must be a base64 PNG or JPEG data URI (SVG/external URLs are forbidden)"
        )
    mime_sub = match.group(1).lower()
    b64_body = re.sub(r"\s+", "", match.group(2))
    try:
        raw = base64.b64decode(b64_body, validate=True)
    except Exception as exc:
        raise ValueError(f"Invalid base64 payload in logo_data_uri: {exc}") from exc
    if not raw:
        raise ValueError("logo_data_uri payload cannot be empty")
    if len(raw) > _MAX_LOGO_BYTES:
        raise ValueError(f"logo_data_uri exceeds 2 MB limit ({len(raw)} bytes)")
    canonical_sub = "jpeg" if mime_sub == "jpg" else mime_sub
    return f"data:image/{canonical_sub};base64,{base64.b64encode(raw).decode('ascii')}"


def resolve_invoice_branding(
    branding: InvoiceBranding | Mapping[str, Any] | None,
) -> ResolvedBranding:
    """Validate and normalize tenant branding for white-paper invoices."""
    if branding is None:
        return ResolvedBranding(
            display_name_ar=None,
            display_name_en=None,
            primary_color=DEFAULT_BRANDING_PRIMARY,
            logo_data_uri=None,
            mono_logo=False,
            remove_powered_by=False,
        )

    if isinstance(branding, InvoiceBranding):
        raw_display = branding.display_name
        raw_primary = branding.primary_color
        raw_logo = branding.logo_data_uri
        mono_logo = bool(branding.mono_logo)
        remove_powered_by = bool(branding.remove_powered_by)
    elif isinstance(branding, Mapping):
        raw_display = branding.get("display_name", branding.get("displayName"))
        raw_primary = branding.get("primary_color", branding.get("primary", DEFAULT_BRANDING_PRIMARY))
        raw_logo = branding.get("logo_data_uri", branding.get("logoDataUri"))
        mono_logo = bool(branding.get("mono_logo", branding.get("monoLogo", False)))
        remove_powered_by = bool(
            branding.get("remove_powered_by", branding.get("removePoweredBy", False))
        )
    else:
        raise TypeError("branding must be an InvoiceBranding, mapping, or None")

    primary = (raw_primary or DEFAULT_BRANDING_PRIMARY).strip()
    ratio = contrast_ratio_on_white(primary)
    if ratio < 4.5:
        raise ValueError(
            f"Branding primary color '{primary}' fails WCAG AA contrast on white "
            f"({ratio:.2f}:1 < 4.50:1)"
        )

    name_ar: str | None = None
    name_en: str | None = None
    if isinstance(raw_display, str):
        cleaned = raw_display.strip()
        if len(cleaned) > 40:
            raise ValueError("display_name must be 40 characters or fewer")
        if cleaned:
            name_ar = cleaned
            name_en = cleaned
    elif isinstance(raw_display, Mapping):
        ar_val = raw_display.get("ar")
        en_val = raw_display.get("en")
        if ar_val is not None:
            name_ar = str(ar_val).strip() or None
            if name_ar and len(name_ar) > 40:
                raise ValueError("display_name['ar'] must be 40 characters or fewer")
        if en_val is not None:
            name_en = str(en_val).strip() or None
            if name_en and len(name_en) > 40:
                raise ValueError("display_name['en'] must be 40 characters or fewer")
    elif raw_display is not None:
        raise ValueError("display_name must be a string, {'ar': ..., 'en': ...} mapping, or None")

    logo_uri = _sanitize_logo_data_uri(raw_logo)
    return ResolvedBranding(
        display_name_ar=name_ar,
        display_name_en=name_en,
        primary_color=primary,
        logo_data_uri=logo_uri,
        mono_logo=mono_logo,
        remove_powered_by=remove_powered_by,
    )


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _ltr(value: Any) -> str:
    return f'<bdi dir="ltr">{_esc(value)}</bdi>'


def _to_dec(val: Any, field_name: str) -> Decimal:
    if isinstance(val, Decimal):
        dec = val
    elif isinstance(val, (int, str)) and not isinstance(val, bool):
        try:
            dec = Decimal(str(val).strip())
        except InvalidOperation as exc:
            raise ValueError(f"{field_name} '{val}' is not a valid decimal number") from exc
    else:
        raise ValueError(f"{field_name} must be Decimal, int, or numeric string")
    if not dec.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return dec


def _fmt_money(val: Any, field_name: str = "amount") -> str:
    dec = _to_dec(val, field_name)
    return f"{dec.quantize(_TWO_DECIMALS):,.2f}"


def _fmt_qty(val: Any) -> str:
    dec = _to_dec(val, "quantity")
    normalized = dec.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _fmt_pct(vat_rate: Any) -> str:
    dec = _to_dec(vat_rate, "vat_rate")
    pct = dec * Decimal("100")
    normalized = pct.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return f"{text or '0'}%"


def _validate_neutral_invoice(invoice_data: Mapping[str, Any]) -> dict[str, Any]:
    """Validate minimal country-neutral invoice structure & ADR-0031 totals consistency."""
    errors: list[str] = []
    for key in ("invoice_id", "issue_date", "currency", "seller", "lines", "totals"):
        if invoice_data.get(key) in (None, "", [], {}):
            errors.append(f"Missing invoice: {key}")

    issue_date = str(invoice_data.get("issue_date") or "").strip()
    if issue_date and not _DATE_RE.fullmatch(issue_date):
        errors.append(f"Issue date '{issue_date}' must be 'YYYY-MM-DD'")

    seller = invoice_data.get("seller") or {}
    if isinstance(seller, Mapping) and not str(seller.get("name") or "").strip():
        errors.append("Seller legal name is required")

    lines = invoice_data.get("lines") or []
    if isinstance(lines, list):
        for idx, line in enumerate(lines, start=1):
            if not isinstance(line, Mapping):
                errors.append(f"Line {idx}: must be a mapping")
                continue
            if not str(line.get("description") or "").strip():
                errors.append(f"Line {idx}: description is required")
            try:
                qty = _to_dec(line.get("quantity"), f"Line {idx} quantity")
                if qty <= _ZERO:
                    errors.append(f"Line {idx}: quantity must be positive")
            except ValueError as exc:
                errors.append(str(exc))
            try:
                unit_price = _to_dec(line.get("unit_price"), f"Line {idx} unit_price")
                if unit_price < _ZERO:
                    errors.append(f"Line {idx}: unit_price cannot be negative")
            except ValueError as exc:
                errors.append(str(exc))

    totals = invoice_data.get("totals") or {}
    if isinstance(totals, Mapping) and totals:
        try:
            taxable = _to_dec(totals.get("total_taxable_amount"), "total_taxable_amount")
            vat = _to_dec(totals.get("total_vat_amount"), "total_vat_amount")
            grand = _to_dec(totals.get("grand_total"), "grand_total")
            for label, val in (
                ("Total taxable amount", taxable),
                ("Total VAT amount", vat),
                ("Grand total", grand),
            ):
                if val < _ZERO:
                    errors.append(f"{label} cannot be negative")
                if val != val.quantize(_TWO_DECIMALS):
                    errors.append(f"{label} '{val}' must already be rounded to 2 decimals")
            if taxable + vat != grand:
                errors.append(
                    f"Engine totals disagree: taxable {taxable} + VAT {vat} != grand total {grand}"
                )
        except ValueError as exc:
            errors.append(str(exc))

    tx_type = str(invoice_data.get("transaction_type") or "invoice").strip().lower()
    if tx_type in ("credit_note", "debit_note"):
        if not str(invoice_data.get("preceding_invoice_reference") or "").strip():
            errors.append(f"Preceding invoice reference is mandatory for {tx_type}")

    if errors:
        raise ValueError("; ".join(errors))
    return dict(invoice_data)


def _format_address_parts(addr: Mapping[str, Any] | None) -> tuple[str, str]:
    if not isinstance(addr, Mapping) or not addr:
        return ("", "")
    en_parts: list[str] = []
    if addr.get("building_no"):
        en_parts.append(str(addr["building_no"]).strip())
    for key in ("street", "district", "city", "postal_code", "country_code"):
        val = str(addr.get(key) or "").strip()
        if val:
            en_parts.append(val)
    ar_parts: list[str] = []
    for key in ("building_no", "street_ar", "district_ar", "city_ar", "postal_code", "country_code"):
        fallback_key = key[:-3] if key.endswith("_ar") else key
        val = str(addr.get(key) or addr.get(fallback_key) or "").strip()
        if val:
            ar_parts.append(val)
    return ("، ".join(ar_parts), ", ".join(en_parts))


def _render_party_card(
    title_ar: str,
    title_en: str,
    party: Mapping[str, Any] | None,
    *,
    fallback_none_ar: str = "عميل نقدي / غير محدد",
    fallback_none_en: str = "Walk-in / Unspecified",
) -> str:
    if not isinstance(party, Mapping) or not party:
        return (
            '<div class="party-card">'
            f'<div class="card-header"><span class="bi-ar">{_esc(title_ar)}</span>'
            f'<span class="bi-en">{_esc(title_en)}</span></div>'
            f'<div class="card-body">'
            f'<div class="bi-row muted"><span class="bi-ar">{_esc(fallback_none_ar)}</span>'
            f'<span class="bi-en">{_esc(fallback_none_en)}</span></div>'
            "</div></div>"
        )

    name_en = str(party.get("name") or "").strip()
    name_ar = str(party.get("name_ar") or "").strip() or name_en
    vat_num = str(party.get("vat_number") or "").strip()
    cr_num = str(party.get("cr_number") or "").strip()
    buyer_id_type = str(party.get("buyer_id_type") or "").strip()
    buyer_id_val = str(party.get("buyer_id_value") or "").strip()
    addr_ar, addr_en = _format_address_parts(party.get("address"))

    rows: list[str] = [
        '<div class="party-name bi-row">'
        f'<span class="bi-ar">{_esc(name_ar)}</span>'
        f'<span class="bi-en">{_esc(name_en)}</span>'
        "</div>"
    ]
    if vat_num:
        lbl_ar, lbl_en = BILINGUAL_LABELS["vat_number"]
        rows.append(
            '<div class="detail-row">'
            f'<span class="bi-ar">{_esc(lbl_ar)}: {_ltr(vat_num)}</span>'
            f'<span class="bi-en">{_esc(lbl_en)}: {_ltr(vat_num)}</span>'
            "</div>"
        )
    if cr_num:
        lbl_ar, lbl_en = BILINGUAL_LABELS["cr_number"]
        rows.append(
            '<div class="detail-row">'
            f'<span class="bi-ar">{_esc(lbl_ar)}: {_ltr(cr_num)}</span>'
            f'<span class="bi-en">{_esc(lbl_en)}: {_ltr(cr_num)}</span>'
            "</div>"
        )
    if buyer_id_type and buyer_id_val:
        rows.append(
            '<div class="detail-row">'
            f'<span class="bi-ar">{_esc(buyer_id_type)}: {_ltr(buyer_id_val)}</span>'
            f'<span class="bi-en">{_esc(buyer_id_type)}: {_ltr(buyer_id_val)}</span>'
            "</div>"
        )
    if addr_ar or addr_en:
        lbl_ar, lbl_en = BILINGUAL_LABELS["address"]
        rows.append(
            '<div class="detail-row">'
            f'<span class="bi-ar">{_esc(lbl_ar)}: {_esc(addr_ar)}</span>'
            f'<span class="bi-en">{_esc(lbl_en)}: {_esc(addr_en)}</span>'
            "</div>"
        )

    return (
        '<div class="party-card">'
        f'<div class="card-header"><span class="bi-ar">{_esc(title_ar)}</span>'
        f'<span class="bi-en">{_esc(title_en)}</span></div>'
        f'<div class="card-body">{"".join(rows)}</div>'
        "</div>"
    )


def render_tax_invoice_html(
    invoice_data: Mapping[str, Any],
    *,
    mode: str = "zatca_sa",
    branding: InvoiceBranding | Mapping[str, Any] | None = None,
) -> str:
    """Render a bilingual Arabic/English RTL print-ready HTML tax invoice.

    Args:
        invoice_data: Invoice payload matching ZATCA Phase 1 schema (or neutral schema in ``neutral`` mode).
        mode: ``"zatca_sa"`` (ZATCA Phase 1 validation + mandatory TLV QR) or ``"neutral"``.
        branding: Optional tenant branding validated against WCAG AA 4.5:1 on white and logo rules.
    """
    if mode not in ("zatca_sa", "neutral"):
        raise ValueError(f"Unsupported print format mode '{mode}'; expected 'zatca_sa' or 'neutral'")

    resolved_branding = resolve_invoice_branding(branding)
    raw_dict = dict(invoice_data)
    qr_tlv: str | None = None

    if mode == "zatca_sa":
        # Lazy import preserves neutral-mode independence from country compliance modules (ADR-0026).
        from change_engine.compliance import generate_phase1_invoice

        zatca_inv = generate_phase1_invoice(raw_dict)
        qr_tlv = zatca_inv.qr_code_tlv
        invoice_id = zatca_inv.invoice_id
        issue_date = zatca_inv.issue_date
        issue_time = zatca_inv.issue_time
        invoice_type = zatca_inv.invoice_type
        tx_type = zatca_inv.transaction_type
        currency = zatca_inv.currency
        preceding_ref = zatca_inv.preceding_invoice_reference
        amendment_reason = zatca_inv.amendment_reason
        totals_dict = {
            "total_taxable_amount": zatca_inv.totals.total_taxable_amount,
            "total_vat_amount": zatca_inv.totals.total_vat_amount,
            "grand_total": zatca_inv.totals.grand_total,
        }
    else:
        validated = _validate_neutral_invoice(raw_dict)
        qr_tlv = validated.get("qr_code_tlv")
        invoice_id = str(validated["invoice_id"]).strip()
        issue_date = str(validated["issue_date"]).strip()
        issue_time = str(validated.get("issue_time") or "").strip()
        invoice_type = str(validated.get("invoice_type") or "neutral").strip().lower()
        tx_type = str(validated.get("transaction_type") or "invoice").strip().lower()
        currency = str(validated["currency"]).strip()
        preceding_ref = validated.get("preceding_invoice_reference")
        amendment_reason = validated.get("amendment_reason")
        totals_dict = dict(validated["totals"])

    title_ar, title_en = _DOC_TITLES.get((mode, tx_type), ("فاتورة", "Invoice"))
    if mode == "zatca_sa":
        badge_key = "standard_badge" if invoice_type == "standard" else "simplified_badge"
    else:
        badge_key = "neutral_badge"
    badge_ar, badge_en = BILINGUAL_LABELS[badge_key]

    seller_map = raw_dict.get("seller") or {}
    buyer_map = raw_dict.get("buyer")
    hijri_date = str(raw_dict.get("hijri_date") or "").strip()
    notes_text = str(raw_dict.get("notes") or "").strip()

    # Branding header elements (never displace mandatory legal layout or QR clear zone)
    logo_html = ""
    if resolved_branding.logo_data_uri:
        mono_cls = " logo-mono" if resolved_branding.mono_logo else ""
        logo_html = (
            f'<div class="brand-logo-wrap">'
            f'<img class="brand-logo{mono_cls}" src="{_esc(resolved_branding.logo_data_uri)}" '
            f'alt="Tenant Logo"/>'
            f"</div>"
        )

    tenant_banner = ""
    if resolved_branding.display_name_ar or resolved_branding.display_name_en:
        dn_ar = resolved_branding.display_name_ar or resolved_branding.display_name_en or ""
        dn_en = resolved_branding.display_name_en or resolved_branding.display_name_ar or ""
        tenant_banner = (
            '<div class="brand-name bi-row">'
            f'<span class="bi-ar">{_esc(dn_ar)}</span>'
            f'<span class="bi-en">{_esc(dn_en)}</span>'
            "</div>"
        )

    # Metadata grid rows
    meta_entries: list[tuple[tuple[str, str], str]] = [
        (BILINGUAL_LABELS["invoice_number"], _ltr(invoice_id)),
        (BILINGUAL_LABELS["issue_date"], _ltr(issue_date)),
    ]
    if issue_time:
        meta_entries.append((BILINGUAL_LABELS["issue_time"], _ltr(issue_time)))
    if hijri_date:
        meta_entries.append((BILINGUAL_LABELS["hijri_date"], _ltr(hijri_date)))
    meta_entries.append((BILINGUAL_LABELS["currency"], _ltr(currency)))

    meta_rows_html = "".join(
        "<tr>"
        f'<th class="meta-label-ar">{_esc(lbl[0])}</th>'
        f'<td class="meta-value">{val_html}</td>'
        f'<th class="meta-label-en">{_esc(lbl[1])}</th>'
        "</tr>"
        for lbl, val_html in meta_entries
    )

    adjustment_html = ""
    if preceding_ref or amendment_reason:
        ref_lbl = BILINGUAL_LABELS["preceding_invoice"]
        reason_lbl = BILINGUAL_LABELS["amendment_reason"]
        adjustment_html = (
            '<div class="adjustment-box">'
            + (
                '<div class="bi-row">'
                f'<span class="bi-ar"><strong>{_esc(ref_lbl[0])}:</strong> {_ltr(preceding_ref)}</span>'
                f'<span class="bi-en"><strong>{_esc(ref_lbl[1])}:</strong> {_ltr(preceding_ref)}</span>'
                "</div>"
                if preceding_ref
                else ""
            )
            + (
                '<div class="bi-row">'
                f'<span class="bi-ar"><strong>{_esc(reason_lbl[0])}:</strong> {_esc(amendment_reason)}</span>'
                f'<span class="bi-en"><strong>{_esc(reason_lbl[1])}:</strong> {_esc(amendment_reason)}</span>'
                "</div>"
                if amendment_reason
                else ""
            )
            + "</div>"
        )

    # Line items table
    line_rows_html: list[str] = []
    for idx, line in enumerate(raw_dict.get("lines") or [], start=1):
        item_code = str(line.get("item_code") or "").strip()
        desc_en = str(line.get("description") or "").strip()
        desc_ar = str(line.get("description_ar") or "").strip()
        qty_str = _fmt_qty(line["quantity"])
        unit_price_str = _fmt_money(line["unit_price"], f"line {idx} unit_price")
        discount_dec = _to_dec(line.get("discount", "0"), f"line {idx} discount")
        discount_str = _fmt_money(discount_dec, f"line {idx} discount")
        vat_rate_raw = line.get("vat_rate", "0")
        vat_rate_str = _fmt_pct(vat_rate_raw) if vat_rate_raw not in (None, "") else "0%"
        vat_cat = str(line.get("vat_category") or "").strip().upper()
        ex_code = str(line.get("exemption_reason_code") or "").strip()
        ex_text = str(line.get("exemption_reason_text") or "").strip()

        if line.get("line_total") not in (None, ""):
            line_amount_str = _fmt_money(line["line_total"], f"line {idx} line_total")
        elif line.get("line_net_amount") not in (None, ""):
            line_amount_str = _fmt_money(line["line_net_amount"], f"line {idx} line_net_amount")
        else:
            # Display gross less discount only if engine didn't pass line_net_amount;
            # document totals below always come strictly from engine `totals` (ADR-0031).
            qty_dec = _to_dec(line["quantity"], f"line {idx} quantity")
            price_dec = _to_dec(line["unit_price"], f"line {idx} unit_price")
            line_amount_str = _fmt_money(
                (qty_dec * price_dec - discount_dec).quantize(_TWO_DECIMALS),
                f"line {idx} amount",
            )

        desc_cell = f'<div class="item-desc-en">{_esc(desc_en)}</div>'
        if desc_ar and desc_ar != desc_en:
            desc_cell = (
                f'<div class="item-desc-ar">{_esc(desc_ar)}</div>'
                f'<div class="item-desc-en">{_esc(desc_en)}</div>'
            )
        if ex_code or ex_text:
            reason_joined = " — ".join(p for p in (ex_code, ex_text) if p)
            desc_cell += f'<div class="item-exemption">{_esc(reason_joined)}</div>'

        cat_pair = _VAT_CATEGORY_LABELS.get(vat_cat)
        cat_cell = (
            f'<span class="cat-ar">{_esc(cat_pair[0])}</span>'
            f'<span class="cat-en">{_esc(cat_pair[1])}</span>'
            if cat_pair
            else _ltr(vat_cat or "-")
        )

        line_rows_html.append(
            "<tr>"
            f'<td class="num-col">{_ltr(idx)}</td>'
            f'<td class="code-col">{_ltr(item_code or "-")}</td>'
            f'<td class="desc-col">{desc_cell}</td>'
            f'<td class="num-col">{_ltr(qty_str)}</td>'
            f'<td class="num-col">{_ltr(unit_price_str)}</td>'
            f'<td class="num-col">{_ltr(discount_str)}</td>'
            f'<td class="num-col">{_ltr(vat_rate_str)}</td>'
            f'<td class="cat-col">{cat_cell}</td>'
            f'<td class="num-col">{_ltr(line_amount_str)}</td>'
            "</tr>"
        )

    # QR code block (with mandatory >= 4mm white clear zone)
    qr_html = ""
    if qr_tlv:
        qr_svg = render_qr_svg(
            qr_tlv,
            size_mm=32.0,
            quiet_modules=4,
            label=f"ZATCA QR {invoice_id}",
            tlv_attribute=qr_tlv,
        )
        qr_cap_ar, qr_cap_en = BILINGUAL_LABELS["qr_caption"]
        qr_html = (
            '<div class="qr-panel">'
            '<div class="qr-clear-zone">'
            f"{qr_svg}"
            "</div>"
            '<div class="qr-caption bi-row">'
            f'<span class="bi-ar">{_esc(qr_cap_ar)}</span>'
            f'<span class="bi-en">{_esc(qr_cap_en)}</span>'
            "</div>"
            "</div>"
        )

    taxable_str = _fmt_money(totals_dict["total_taxable_amount"], "total_taxable_amount")
    vat_str = _fmt_money(totals_dict["total_vat_amount"], "total_vat_amount")
    grand_str = _fmt_money(totals_dict["grand_total"], "grand_total")

    lbl_taxable = BILINGUAL_LABELS["total_taxable_amount"]
    lbl_vat = BILINGUAL_LABELS["total_vat_amount"]
    lbl_grand = BILINGUAL_LABELS["grand_total"]

    totals_html = (
        '<table class="totals-table">'
        "<tr>"
        f'<th class="tot-ar">{_esc(lbl_taxable[0])}</th>'
        f'<td class="tot-val">{_ltr(f"{taxable_str} {currency}")}</td>'
        f'<th class="tot-en">{_esc(lbl_taxable[1])}</th>'
        "</tr>"
        "<tr>"
        f'<th class="tot-ar">{_esc(lbl_vat[0])}</th>'
        f'<td class="tot-val">{_ltr(f"{vat_str} {currency}")}</td>'
        f'<th class="tot-en">{_esc(lbl_vat[1])}</th>'
        "</tr>"
        '<tr class="grand-row">'
        f'<th class="tot-ar">{_esc(lbl_grand[0])}</th>'
        f'<td class="tot-val">{_ltr(f"{grand_str} {currency}")}</td>'
        f'<th class="tot-en">{_esc(lbl_grand[1])}</th>'
        "</tr>"
        "</table>"
    )

    notes_html = ""
    if notes_text:
        n_ar, n_en = BILINGUAL_LABELS["notes"]
        notes_html = (
            '<div class="notes-box">'
            f'<div class="bi-row"><strong><span class="bi-ar">{_esc(n_ar)}</span>'
            f'<span class="bi-en">{_esc(n_en)}</span></strong></div>'
            f'<div class="notes-body">{_esc(notes_text)}</div>'
            "</div>"
        )

    footer_powered = (
        ""
        if resolved_branding.remove_powered_by
        else (
            '<span class="powered-by">'
            f'مدعوم من {_ltr("Orrery")} &nbsp;|&nbsp; Powered by {_ltr("Orrery")}'
            "</span>"
        )
    )

    seller_card = _render_party_card(*BILINGUAL_LABELS["seller"], seller_map)
    buyer_card = _render_party_card(*BILINGUAL_LABELS["customer"], buyer_map)

    headers = [
        BILINGUAL_LABELS["line_no"],
        BILINGUAL_LABELS["item_code"],
        BILINGUAL_LABELS["description"],
        BILINGUAL_LABELS["quantity"],
        BILINGUAL_LABELS["unit_price"],
        BILINGUAL_LABELS["discount"],
        BILINGUAL_LABELS["vat_rate"],
        BILINGUAL_LABELS["vat_category"],
        BILINGUAL_LABELS["line_amount"],
    ]
    thead_cells = "".join(
        "<th>"
        f'<div class="th-ar">{_esc(h[0])}</div>'
        + (f'<div class="th-en">{_esc(h[1])}</div>' if h[1] != h[0] else "")
        + "</th>"
        for h in headers
    )

    primary_hex = resolved_branding.primary_color
    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{_esc(title_ar)} / {_esc(title_en)} — {_esc(invoice_id)}</title>
<style>
  @page {{
    size: A4 portrait;
    margin: 14mm 14mm 16mm 14mm;
  }}
  * {{
    box-sizing: border-box;
  }}
  html, body {{
    margin: 0;
    padding: 0;
    background: #ffffff;
    color: #0e1117;
    font-family: 'Readex Pro', 'Alexandria', 'DejaVu Sans', 'Noto Sans Arabic', Arial, sans-serif;
    font-size: 9.5pt;
    line-height: 1.45;
    direction: rtl;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }}
  bdi {{
    unicode-bidi: isolate;
    direction: ltr;
  }}
  .invoice-page {{
    width: 100%;
    max-width: 182mm;
    margin: 0 auto;
    background: #ffffff;
  }}
  .top-header {{
    display: table;
    width: 100%;
    border-bottom: 2px solid {primary_hex};
    padding-bottom: 4mm;
    margin-bottom: 4.5mm;
  }}
  .header-start, .header-end {{
    display: table-cell;
    vertical-align: middle;
  }}
  .header-start {{
    width: 55%;
    text-align: right;
    padding-left: 5mm;
  }}
  .header-end {{
    width: 45%;
    text-align: left;
    direction: ltr;
  }}
  .brand-logo-wrap {{
    margin-bottom: 2mm;
  }}
  .brand-logo {{
    min-height: 8mm;
    max-height: 14mm;
    max-width: 60mm;
    width: auto;
    height: auto;
    display: inline-block;
  }}
  .brand-logo.logo-mono {{
    filter: grayscale(100%) contrast(120%);
  }}
  .brand-name {{
    font-size: 11pt;
    font-weight: 700;
    color: {primary_hex};
    margin-bottom: 1.5mm;
  }}
  .doc-title-row {{
    display: table;
    width: 100%;
    margin-bottom: 1mm;
  }}
  .doc-title-ar, .doc-title-en {{
    display: table-cell;
    width: 50%;
    font-size: 14pt;
    font-weight: 700;
    color: {primary_hex};
  }}
  .doc-title-ar {{
    text-align: right;
  }}
  .doc-title-en {{
    text-align: left;
    direction: ltr;
  }}
  .doc-badge-row {{
    display: table;
    width: 100%;
    font-size: 9pt;
    font-weight: 600;
    color: #334155;
  }}
  .doc-badge-row .bi-ar {{
    display: table-cell;
    text-align: right;
  }}
  .doc-badge-row .bi-en {{
    display: table-cell;
    text-align: left;
    direction: ltr;
  }}
  .bi-row {{
    display: table;
    width: 100%;
  }}
  .bi-ar, .bi-en {{
    display: table-cell;
    width: 50%;
    font-size: 9.5pt;
    font-weight: 600;
    vertical-align: top;
  }}
  .bi-ar {{
    text-align: right;
    padding-left: 2mm;
  }}
  .bi-en {{
    text-align: left;
    direction: ltr;
    padding-right: 2mm;
  }}
  .party-name .bi-ar, .party-name .bi-en {{
    font-size: 10pt;
    font-weight: 700;
    color: #0e1117;
    margin-bottom: 1.5mm;
  }}
  .detail-row {{
    display: table;
    width: 100%;
    margin-top: 1mm;
    font-size: 9pt;
    font-weight: 400;
    color: #1e293b;
  }}
  .detail-row .bi-ar, .detail-row .bi-en {{
    font-size: 9pt;
    font-weight: 400;
  }}
  .meta-table {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 4.5mm;
    border: 1px solid #d5dce6;
  }}
  .meta-table th, .meta-table td {{
    padding: 1.8mm 2.5mm;
    border-bottom: 1px solid #e2e8f0;
    font-size: 9.2pt;
  }}
  .meta-label-ar {{
    width: 30%;
    text-align: right;
    font-weight: 600;
    background: #f8fafc;
    color: {primary_hex};
  }}
  .meta-value {{
    width: 40%;
    text-align: center;
    font-weight: 600;
    color: #0e1117;
  }}
  .meta-label-en {{
    width: 30%;
    text-align: left;
    direction: ltr;
    font-weight: 600;
    background: #f8fafc;
    color: {primary_hex};
  }}
  .parties-grid {{
    display: table;
    width: 100%;
    table-layout: fixed;
    border-spacing: 3mm 0;
    margin: 0 -3mm 4.5mm -3mm;
  }}
  .party-col {{
    display: table-cell;
    width: 50%;
    vertical-align: top;
  }}
  .party-card {{
    border: 1px solid #d5dce6;
    border-radius: 1.5mm;
    background: #ffffff;
    break-inside: avoid;
  }}
  .card-header {{
    display: table;
    width: 100%;
    background: #f5f7fa;
    border-bottom: 1.5px solid {primary_hex};
    padding: 2mm 2.5mm;
    color: {primary_hex};
  }}
  .card-body {{
    padding: 2.5mm;
  }}
  .muted {{
    color: #64748b;
  }}
  .adjustment-box {{
    border: 1px solid {primary_hex};
    background: #f8fafc;
    padding: 2.5mm 3mm;
    margin-bottom: 4.5mm;
    break-inside: avoid;
  }}
  .lines-table {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 5mm;
  }}
  .lines-table th {{
    background: #f5f7fa;
    color: {primary_hex};
    border-top: 1.5px solid {primary_hex};
    border-bottom: 1.5px solid {primary_hex};
    border-left: 1px solid #e2e8f0;
    border-right: 1px solid #e2e8f0;
    padding: 2mm 1.5mm;
    text-align: center;
    font-size: 8.8pt;
    font-weight: 700;
  }}
  .th-ar, .th-en {{
    font-size: 8.8pt;
    font-weight: 700;
  }}
  .th-en {{
    direction: ltr;
  }}
  .lines-table td {{
    border: 1px solid #e2e8f0;
    padding: 2mm 1.5mm;
    vertical-align: top;
    font-size: 9pt;
  }}
  .num-col {{
    text-align: center;
    white-space: nowrap;
  }}
  .code-col {{
    text-align: center;
    white-space: nowrap;
    font-weight: 600;
  }}
  .desc-col {{
    text-align: right;
  }}
  .item-desc-ar {{
    font-weight: 600;
    color: #0e1117;
  }}
  .item-desc-en {{
    direction: ltr;
    text-align: left;
    font-weight: 500;
    color: #1e293b;
  }}
  .item-exemption {{
    font-size: 8.2pt;
    color: #475569;
    margin-top: 0.8mm;
  }}
  .cat-col {{
    text-align: center;
    font-size: 8.5pt;
  }}
  .cat-ar, .cat-en {{
    display: block;
  }}
  .cat-en {{
    direction: ltr;
  }}
  .summary-section {{
    display: table;
    width: 100%;
    margin-top: 3mm;
    break-inside: avoid;
  }}
  .summary-totals-cell {{
    display: table-cell;
    width: 58%;
    vertical-align: top;
    padding-left: 4mm;
  }}
  .summary-qr-cell {{
    display: table-cell;
    width: 42%;
    vertical-align: top;
    text-align: center;
  }}
  .totals-table {{
    width: 100%;
    border-collapse: collapse;
    border: 1px solid #d5dce6;
  }}
  .totals-table th, .totals-table td {{
    padding: 2.2mm 2.5mm;
    border-bottom: 1px solid #e2e8f0;
    font-size: 9.5pt;
  }}
  .tot-ar {{
    text-align: right;
    font-weight: 600;
    width: 34%;
  }}
  .tot-val {{
    text-align: center;
    font-weight: 700;
    width: 32%;
    white-space: nowrap;
  }}
  .tot-en {{
    text-align: left;
    direction: ltr;
    font-weight: 600;
    width: 34%;
  }}
  .grand-row th, .grand-row td {{
    background: #f5f7fa;
    border-top: 1.5px solid {primary_hex};
    border-bottom: 1.5px solid {primary_hex};
    color: {primary_hex};
    font-size: 10.5pt;
    font-weight: 700;
  }}
  .qr-panel {{
    display: block;
    width: 100%;
    text-align: center;
    break-inside: avoid;
  }}
  .qr-clear-zone {{
    display: inline-block;
    background: #ffffff;
    padding: 4.5mm;
    border: 1px solid #d5dce6;
    margin: 0;
  }}
  .qr-clear-zone svg {{
    display: block;
  }}
  .qr-caption {{
    max-width: 72mm;
    margin: 1.5mm auto 0 auto;
    font-size: 8.5pt;
    color: #334155;
  }}
  .notes-box {{
    margin-top: 4mm;
    padding: 2.5mm 3mm;
    border: 1px solid #e2e8f0;
    background: #ffffff;
  }}
  .notes-body {{
    margin-top: 1mm;
    font-size: 9pt;
    color: #334155;
  }}
  .doc-footer {{
    margin-top: 6mm;
    padding-top: 2.5mm;
    border-top: 1px solid #d5dce6;
    display: table;
    width: 100%;
    font-size: 8.5pt;
    color: #475569;
  }}
  .footer-ref {{
    display: table-cell;
    text-align: right;
  }}
  .footer-brand {{
    display: table-cell;
    text-align: left;
    direction: ltr;
  }}
</style>
</head>
<body dir="rtl">
  <div class="invoice-page" data-print-mode="{_esc(mode)}">
    <div class="top-header">
      <div class="header-start">
        {logo_html}
        {tenant_banner}
        <div class="doc-title-row">
          <span class="doc-title-ar">{_esc(title_ar)}</span>
          <span class="doc-title-en">{_esc(title_en)}</span>
        </div>
        <div class="doc-badge-row">
          <span class="bi-ar">{_esc(badge_ar)}</span>
          <span class="bi-en">{_esc(badge_en)}</span>
        </div>
      </div>
      <div class="header-end">
        <table class="meta-table">
          {meta_rows_html}
        </table>
      </div>
    </div>

    <div class="parties-grid">
      <div class="party-col">{seller_card}</div>
      <div class="party-col">{buyer_card}</div>
    </div>

    {adjustment_html}

    <table class="lines-table">
      <thead>
        <tr>{thead_cells}</tr>
      </thead>
      <tbody>
        {"".join(line_rows_html)}
      </tbody>
    </table>

    <div class="summary-section">
      <div class="summary-totals-cell">
        {totals_html}
        {notes_html}
      </div>
      <div class="summary-qr-cell">
        {qr_html}
      </div>
    </div>

    <div class="doc-footer">
      <span class="footer-ref">{_ltr(invoice_id)}</span>
      <span class="footer-brand">{footer_powered}</span>
    </div>
  </div>
</body>
</html>"""


def render_tax_invoice_pdf(
    invoice_data: Mapping[str, Any],
    *,
    mode: str = "zatca_sa",
    branding: InvoiceBranding | Mapping[str, Any] | None = None,
    backend: str = "auto",
) -> bytes:
    """Render the bilingual tax invoice directly to PDF bytes using WeasyPrint or wkhtmltopdf."""
    if backend not in ("auto", "weasyprint", "wkhtmltopdf"):
        raise ValueError(f"Unsupported PDF backend '{backend}'")

    html_str = render_tax_invoice_html(invoice_data, mode=mode, branding=branding)

    if backend in ("auto", "weasyprint"):
        try:
            import weasyprint  # type: ignore[import-not-found]

            pdf_bytes = weasyprint.HTML(string=html_str).write_pdf()
            if not pdf_bytes or not pdf_bytes.startswith(b"%PDF-"):
                raise RuntimeError("WeasyPrint produced empty or invalid PDF output")
            return pdf_bytes
        except ImportError:
            if backend == "weasyprint":
                raise RuntimeError("WeasyPrint is not installed in this Python environment")

    if backend in ("auto", "wkhtmltopdf"):
        try:
            from frappe.utils.pdf import get_pdf  # type: ignore[import-not-found]

            pdf_bytes = get_pdf(html_str)
            if not pdf_bytes or not pdf_bytes.startswith(b"%PDF-"):
                raise RuntimeError("wkhtmltopdf produced empty or invalid PDF output")
            return pdf_bytes
        except (ImportError, AttributeError):
            try:
                import pdfkit  # type: ignore[import-not-found]

                pdf_bytes = pdfkit.from_string(
                    html_str,
                    False,
                    options={"encoding": "UTF-8", "quiet": "", "page-size": "A4"},
                )
                if not pdf_bytes or not pdf_bytes.startswith(b"%PDF-"):
                    raise RuntimeError("wkhtmltopdf/pdfkit produced empty or invalid PDF output")
                return pdf_bytes
            except ImportError:
                if backend == "wkhtmltopdf":
                    raise RuntimeError("frappe.utils.pdf / wkhtmltopdf is not available")

    raise RuntimeError(
        "No PDF rendering backend available (install weasyprint or run inside the Frappe bench)"
    )


def _get_attr_or_key(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _format_issue_date(val: Any) -> str:
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d")
    if isinstance(val, date):
        return val.isoformat()
    return str(val or "").strip()


def _format_issue_time(val: Any) -> str:
    if val is None or val == "":
        return ""
    if isinstance(val, time):
        return val.strftime("%H:%M:%S")
    if isinstance(val, timedelta):
        total_sec = int(val.total_seconds()) % 86400
        hh = total_sec // 3600
        mm = (total_sec % 3600) // 60
        ss = total_sec % 60
        return f"{hh:02d}:{mm:02d}:{ss:02d}"
    text = str(val).strip()
    if "." in text:
        text = text.split(".", 1)[0]
    parts = text.split(":")
    if len(parts) == 2 and all(p.isdigit() for p in parts):
        return f"{int(parts[0]):02d}:{int(parts[1]):02d}:00"
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        return f"{int(parts[0]):02d}:{int(parts[1]):02d}:{int(parts[2]):02d}"
    return text


def _country_to_iso(country_val: Any) -> str:
    text = str(country_val or "").strip()
    if not text:
        return ""
    if len(text) == 2 and text.isalpha():
        return text.upper()
    return _COUNTRY_CODES.get(text.lower(), text)


def _resolve_frappe_module(frappe_module: Any) -> Any:
    if frappe_module is not None:
        return frappe_module
    try:
        import frappe  # type: ignore[import-not-found]

        if getattr(frappe, "db", None) is not None:
            return frappe
    except ImportError:
        pass
    return None


def _load_doc_safe(fm: Any, doctype: str, name: Any) -> Any:
    if fm is None or not name:
        return None
    try:
        return fm.get_doc(doctype, name)
    except Exception:
        return None


def _extract_address_dict(addr_doc: Any, default_country: str = "") -> dict[str, Any]:
    if addr_doc is None:
        return {}
    country_raw = _get_attr_or_key(addr_doc, "country") or default_country
    return {
        "street": str(_get_attr_or_key(addr_doc, "address_line1") or "").strip(),
        "building_no": str(
            _get_attr_or_key(addr_doc, "custom_building_no")
            or _get_attr_or_key(addr_doc, "building_no")
            or _get_attr_or_key(addr_doc, "address_line2")
            or ""
        ).strip(),
        "postal_code": str(_get_attr_or_key(addr_doc, "pincode") or "").strip(),
        "city": str(_get_attr_or_key(addr_doc, "city") or "").strip(),
        "district": str(
            _get_attr_or_key(addr_doc, "custom_district")
            or _get_attr_or_key(addr_doc, "county")
            or _get_attr_or_key(addr_doc, "state")
            or _get_attr_or_key(addr_doc, "address_line2")
            or ""
        ).strip(),
        "country_code": _country_to_iso(country_raw),
    }


def _doc_num_to_dec(val: Any, field_name: str) -> Decimal:
    """Convert a Frappe ORM numeric field (float, int, Decimal, or str) cleanly without binary float drift."""
    if isinstance(val, float):
        if not Decimal(str(val)).is_finite():
            raise ValueError(f"{field_name} must be finite")
        return Decimal(str(val))
    return _to_dec(val, field_name)


def _extract_doc_tax_rate(doc: Any) -> Decimal | None:
    taxes = _get_attr_or_key(doc, "taxes") or []
    for row in taxes:
        rate = _get_attr_or_key(row, "rate")
        if rate not in (None, ""):
            dec = _doc_num_to_dec(rate, "tax rate")
            if dec > Decimal("1"):
                return (dec / Decimal("100")).normalize()
            return dec.normalize()
    return None


def _extract_line_vat_rate(item: Any, doc_default_rate: Decimal | None) -> Decimal:
    explicit = _get_attr_or_key(item, "vat_rate")
    if explicit not in (None, ""):
        dec = _doc_num_to_dec(explicit, "item vat_rate")
        return (dec / Decimal("100")).normalize() if dec > Decimal("1") else dec
    item_tax_rate_raw = _get_attr_or_key(item, "item_tax_rate")
    if isinstance(item_tax_rate_raw, str) and item_tax_rate_raw.strip():
        try:
            parsed = json.loads(item_tax_rate_raw)
            if isinstance(parsed, dict) and parsed:
                first_rate = next(iter(parsed.values()))
                dec = _doc_num_to_dec(first_rate, "item_tax_rate")
                return (dec / Decimal("100")).normalize() if dec > Decimal("1") else dec
        except Exception:
            pass
    elif isinstance(item_tax_rate_raw, Mapping) and item_tax_rate_raw:
        first_rate = next(iter(item_tax_rate_raw.values()))
        dec = _doc_num_to_dec(first_rate, "item_tax_rate")
        return (dec / Decimal("100")).normalize() if dec > Decimal("1") else dec
    if doc_default_rate is not None:
        return doc_default_rate
    return _ZERO


def sales_invoice_to_zatca_dict(
    doc: Any,
    *,
    frappe_module: Any = None,
    company_doc: Any = None,
    company_address_doc: Any = None,
    customer_doc: Any = None,
    customer_address_doc: Any = None,
    timezone: str | None = None,
    mode: str = "auto",
) -> tuple[dict[str, Any], str]:
    """Convert an ERPNext Sales Invoice doc into an invoice dictionary and resolved print mode.

    Never recomputes document totals; reads ``net_total``, ``total_taxes_and_charges``, and
    ``grand_total`` directly from the engine document (ADR-0031).
    """
    if mode not in ("auto", "zatca_sa", "neutral"):
        raise ValueError(f"Unsupported mode '{mode}'; expected 'auto', 'zatca_sa', or 'neutral'")

    fm = _resolve_frappe_module(frappe_module)

    company_name = _get_attr_or_key(doc, "company")
    if company_doc is None and company_name:
        company_doc = _load_doc_safe(fm, "Company", company_name)

    comp_addr_name = _get_attr_or_key(doc, "company_address")
    if company_address_doc is None and comp_addr_name:
        company_address_doc = _load_doc_safe(fm, "Address", comp_addr_name)

    customer_id = _get_attr_or_key(doc, "customer")
    if customer_doc is None and customer_id:
        customer_doc = _load_doc_safe(fm, "Customer", customer_id)

    cust_addr_name = _get_attr_or_key(doc, "customer_address") or _get_attr_or_key(
        customer_doc, "customer_primary_address"
    )
    if customer_address_doc is None and cust_addr_name:
        customer_address_doc = _load_doc_safe(fm, "Address", cust_addr_name)

    resolved_tz = (timezone or _get_attr_or_key(doc, "timezone") or "").strip()
    if not resolved_tz and fm is not None:
        try:
            resolved_tz = str(fm.db.get_single_value("System Settings", "time_zone") or "").strip()
        except Exception:
            resolved_tz = ""

    seller_country = _country_to_iso(_get_attr_or_key(company_doc, "country"))
    seller_vat = str(
        _get_attr_or_key(doc, "company_tax_id")
        or _get_attr_or_key(company_doc, "tax_id")
        or ""
    ).strip()
    seller_name = str(
        _get_attr_or_key(company_doc, "company_name") or company_name or ""
    ).strip()
    seller_name_ar = _get_attr_or_key(company_doc, "custom_company_name_ar") or _get_attr_or_key(
        company_doc, "company_name_in_arabic"
    )
    seller_cr = _get_attr_or_key(company_doc, "custom_cr_number") or _get_attr_or_key(
        company_doc, "cr_no"
    )

    seller_dict: dict[str, Any] = {
        "name": seller_name,
        "vat_number": seller_vat or None,
        "name_ar": seller_name_ar,
        "cr_number": seller_cr,
    }
    seller_addr = _extract_address_dict(company_address_doc, default_country=seller_country)
    if seller_addr:
        seller_dict["address"] = seller_addr

    buyer_name = str(
        _get_attr_or_key(doc, "customer_name")
        or _get_attr_or_key(customer_doc, "customer_name")
        or customer_id
        or ""
    ).strip()
    buyer_name_ar = _get_attr_or_key(customer_doc, "custom_customer_name_ar") or _get_attr_or_key(
        customer_doc, "customer_name_in_arabic"
    )
    buyer_vat = str(
        _get_attr_or_key(doc, "tax_id") or _get_attr_or_key(customer_doc, "tax_id") or ""
    ).strip()
    buyer_addr = _extract_address_dict(customer_address_doc)
    buyer_dict: dict[str, Any] | None = None
    if buyer_name or buyer_vat or buyer_addr:
        buyer_dict = {
            "name": buyer_name,
            "name_ar": buyer_name_ar,
            "vat_number": buyer_vat or None,
        }
        if buyer_addr:
            buyer_dict["address"] = buyer_addr

    is_return = bool(_get_attr_or_key(doc, "is_return", 0))
    is_debit_note = bool(_get_attr_or_key(doc, "is_debit_note", 0))
    is_pos = bool(_get_attr_or_key(doc, "is_pos", 0))
    currency = str(_get_attr_or_key(doc, "currency") or "").strip()

    if mode == "auto":
        is_ksa_company = seller_country == "SA"
        is_ksa_sar = currency == "SAR" and bool(_KSA_VAT_RE.fullmatch(seller_vat))
        resolved_mode = "zatca_sa" if (is_ksa_company or is_ksa_sar) else "neutral"
    else:
        resolved_mode = mode

    explicit_inv_type = str(_get_attr_or_key(doc, "custom_zatca_invoice_type") or "").strip().lower()
    if explicit_inv_type in ("standard", "simplified"):
        invoice_type = explicit_inv_type
    elif is_pos or (not buyer_vat and not buyer_addr):
        invoice_type = "simplified"
    else:
        invoice_type = "standard"

    if is_return:
        transaction_type = "credit_note"
    elif is_debit_note:
        transaction_type = "debit_note"
    elif resolved_mode == "zatca_sa":
        transaction_type = "simplified_tax_invoice" if invoice_type == "simplified" else "tax_invoice"
    else:
        transaction_type = "invoice"

    def _fmt_engine_total(val: Decimal) -> str:
        q = val.quantize(_TWO_DECIMALS)
        return f"{q:.2f}" if val == q else format(val, "f")

    net_total = _doc_num_to_dec(_get_attr_or_key(doc, "net_total", 0), "net_total")
    tax_total = _doc_num_to_dec(_get_attr_or_key(doc, "total_taxes_and_charges", 0), "total_taxes_and_charges")
    grand_total = _doc_num_to_dec(_get_attr_or_key(doc, "grand_total", 0), "grand_total")

    # ERPNext return Sales Invoices store negative quantities and negative totals,
    # whereas ZATCA Phase 1 models (CMP-003) represent credit notes with positive magnitudes.
    negate_return = (is_return or is_debit_note) and grand_total < _ZERO and net_total <= _ZERO and tax_total <= _ZERO
    if negate_return:
        net_total = abs(net_total)
        tax_total = abs(tax_total)
        grand_total = abs(grand_total)

    doc_default_rate = _extract_doc_tax_rate(doc)
    lines: list[dict[str, Any]] = []
    for item in _get_attr_or_key(doc, "items") or []:
        qty_dec = _doc_num_to_dec(_get_attr_or_key(item, "qty", 0), "item qty")
        if negate_return and qty_dec < _ZERO:
            qty_dec = abs(qty_dec)
        rate_dec = _doc_num_to_dec(_get_attr_or_key(item, "rate", 0), "item rate")
        vat_rate = _extract_line_vat_rate(item, doc_default_rate)
        ex_code = _get_attr_or_key(item, "custom_exemption_reason_code") or _get_attr_or_key(
            item, "exemption_reason_code"
        )
        ex_text = _get_attr_or_key(item, "custom_exemption_reason_text") or _get_attr_or_key(
            item, "exemption_reason_text"
        )
        vat_cat = str(
            _get_attr_or_key(item, "custom_vat_category")
            or _get_attr_or_key(item, "vat_category")
            or ""
        ).strip().upper()
        if not vat_cat:
            if vat_rate > _ZERO:
                vat_cat = "S"
            elif ex_code or ex_text:
                vat_cat = "Z"

        line_amount = _get_attr_or_key(item, "net_amount")
        if line_amount is None:
            line_amount = _get_attr_or_key(item, "amount")
        line_amount_dec = _doc_num_to_dec(line_amount, "item net_amount") if line_amount is not None else None
        if line_amount_dec is not None and negate_return and line_amount_dec < _ZERO:
            line_amount_dec = abs(line_amount_dec)

        discount_amt = _get_attr_or_key(item, "discount_amount", 0)
        discount_dec = _doc_num_to_dec(discount_amt or 0, "item discount_amount")
        if negate_return and discount_dec < _ZERO:
            discount_dec = abs(discount_dec)

        line_dict: dict[str, Any] = {
            "item_code": str(_get_attr_or_key(item, "item_code") or "").strip(),
            "description": str(
                _get_attr_or_key(item, "item_name")
                or _get_attr_or_key(item, "description")
                or _get_attr_or_key(item, "item_code")
                or ""
            ).strip(),
            "description_ar": _get_attr_or_key(item, "custom_item_name_ar")
            or _get_attr_or_key(item, "item_name_ar"),
            "quantity": format(qty_dec, "f"),
            "unit_price": _fmt_engine_total(rate_dec),
            "discount": _fmt_engine_total(discount_dec),
            "vat_rate": format(vat_rate, "f"),
            "vat_category": vat_cat,
            "exemption_reason_code": ex_code,
            "exemption_reason_text": ex_text,
        }
        if line_amount_dec is not None:
            line_dict["line_net_amount"] = _fmt_engine_total(line_amount_dec)
        lines.append(line_dict)

    invoice_dict: dict[str, Any] = {
        "invoice_id": str(_get_attr_or_key(doc, "name") or "").strip(),
        "issue_date": _format_issue_date(_get_attr_or_key(doc, "posting_date")),
        "issue_time": _format_issue_time(_get_attr_or_key(doc, "posting_time")),
        "timezone": resolved_tz,
        "currency": currency,
        "invoice_type": invoice_type,
        "transaction_type": transaction_type,
        "seller": seller_dict,
        "buyer": buyer_dict,
        "lines": lines,
        "totals": {
            "total_taxable_amount": _fmt_engine_total(net_total),
            "total_vat_amount": _fmt_engine_total(tax_total),
            "grand_total": _fmt_engine_total(grand_total),
        },
        "preceding_invoice_reference": _get_attr_or_key(doc, "return_against"),
        "amendment_reason": (
            _get_attr_or_key(doc, "custom_amendment_reason")
            or _get_attr_or_key(doc, "reason_for_issuance")
            or _get_attr_or_key(doc, "remarks")
        ),
        "hijri_date": _get_attr_or_key(doc, "custom_hijri_date") or _get_attr_or_key(doc, "hijri_date"),
    }
    return invoice_dict, resolved_mode


def render_frappe_sales_invoice_html(
    doc: Any,
    *,
    mode: str = "auto",
    branding: InvoiceBranding | Mapping[str, Any] | None = None,
    frappe_module: Any = None,
) -> str:
    """Jinja-callable entrypoint: convert an ERPNext Sales Invoice and render bilingual HTML."""
    invoice_dict, resolved_mode = sales_invoice_to_zatca_dict(
        doc,
        frappe_module=frappe_module,
        mode=mode,
    )
    return render_tax_invoice_html(invoice_dict, mode=resolved_mode, branding=branding)


def install_bilingual_tax_invoice_print_format(
    frappe_module: Any = None,
    *,
    set_default: bool = False,
    name: str = "Bilingual Tax Invoice",
) -> dict[str, Any]:
    """Create or update the Frappe Print Format document for Sales Invoice (idempotent, no DDL)."""
    if frappe_module is None:
        import frappe as frappe_module  # type: ignore[no-redef]

    template_html = "{{ render_frappe_sales_invoice_html(doc) }}"
    exists = bool(frappe_module.db.exists("Print Format", name))
    if exists:
        pf = frappe_module.get_doc("Print Format", name)
        action = "updated"
    else:
        pf = frappe_module.get_doc({"doctype": "Print Format", "name": name})
        action = "created"

    pf.doc_type = "Sales Invoice"
    pf.module = "Change Engine"
    pf.print_format_for = "DocType"
    pf.standard = "No"
    pf.custom_format = 1
    pf.disabled = 0
    pf.raw_printing = 0
    pf.print_format_type = "Jinja"
    pf.default_print_language = "ar"
    pf.html = template_html
    if exists:
        pf.save(ignore_permissions=True)
    else:
        pf.insert(ignore_permissions=True)

    if set_default:
        frappe_module.make_property_setter(
            {
                "doctype": "Sales Invoice",
                "property": "default_print_format",
                "value": name,
                "property_type": "Data",
                "for_doctype": True,
            }
        )

    frappe_module.db.commit()
    return {
        "name": name,
        "action": action,
        "doc_type": "Sales Invoice",
        "set_default": set_default,
    }
