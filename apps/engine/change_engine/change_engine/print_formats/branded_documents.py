"""Tenant-branded bilingual tax invoice, quotation and purchase order HTML (ERP-016).

All three documents share the locked shell in ``document_layout``: RTL Arabic page, Arabic on the
right and English on the left, LTR islands for numbers and identifiers, tenant branding only
through colour tokens, a logo and a display name in the header, and a verified region layout.
Numbers are never computed here for the ledger or tax: the tax invoice takes its totals from the
ZATCA engine (or the neutral invoice's engine totals) and the quote and purchase order only render
engine-supplied totals after checking taxable + VAT = grand total (ADR-0031).

Rendering is deterministic and fails closed: invalid data, rejected branding or any deviation from
the locked layout raises, it never falls back to a weaker page.

Arabic copy new in ERP-016 is UNREVIEWED (ADR-0033); see ``document_labels``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Mapping

from .bilingual_tax_invoice import (
    BILINGUAL_LABELS,
    _DATE_RE,
    _TWO_DECIMALS,
    _ZERO,
    _esc,
    _fmt_money,
    _fmt_pct,
    _fmt_qty,
    _ltr,
    _render_party_card,
    _to_dec,
    prepare_tax_invoice_view,
)
from .brand_tokens import ResolvedDocumentBranding, resolve_document_branding
from .document_labels import ALL_LABELS, DOCUMENT_LABELS, QUOTE_STATUSES
from .document_layout import assert_locked_layout, render_document_shell, render_token_block

_MAX_TERMS = 50
_MAX_TERM_CHARS = 1000


# ------------------------------------------------------------------ shared fragments
def _pair(key: str) -> tuple[str, str]:
    return ALL_LABELS[key]


def _bi(key: str, *, strong: bool = False) -> str:
    ar, en = _pair(key)
    inner = f'<span class="bi-ar">{_esc(ar)}</span><span class="bi-en">{_esc(en)}</span>'
    return f"<strong>{inner}</strong>" if strong else inner


def _logo_html(brand: ResolvedDocumentBranding) -> str:
    if brand.logo is None:
        return ""
    mono = " logo-mono" if brand.mono_logo else ""
    return (
        '<div class="brand-logo-wrap">'
        f'<img class="brand-logo{mono}" src="{_esc(brand.logo.data_uri)}" alt=""/>'
        "</div>"
    )


def _name_banner(brand: ResolvedDocumentBranding) -> str:
    if not (brand.display_name_ar or brand.display_name_en):
        return ""
    ar = brand.display_name_ar or brand.display_name_en or ""
    en = brand.display_name_en or brand.display_name_ar or ""
    return (
        '<div class="brand-name bi-row">'
        f'<span class="bi-ar">{_esc(ar)}</span><span class="bi-en">{_esc(en)}</span></div>'
    )


def _title_rows(title: tuple[str, str], badge: str) -> str:
    return (
        '<div class="doc-title-row">'
        f'<span class="doc-title-ar">{_esc(title[0])}</span>'
        f'<span class="doc-title-en">{_esc(title[1])}</span></div>{badge}'
    )


def _meta_rows(entries: list[tuple[tuple[str, str], str]]) -> str:
    return "".join(
        "<tr>"
        f'<th class="meta-label-ar">{_esc(label[0])}</th>'
        f'<td class="meta-value">{value_html}</td>'
        f'<th class="meta-label-en">{_esc(label[1])}</th></tr>'
        for label, value_html in entries
    )


def _header_region(brand: ResolvedDocumentBranding, title_block: str, meta_rows: str) -> str:
    return (
        '<div class="top-header" data-locked-region="header">'
        f'<div class="header-start">{_logo_html(brand)}{_name_banner(brand)}{title_block}</div>'
        f'<div class="header-end"><table class="meta-table">{meta_rows}</table></div>'
        "</div>"
    )


def _footer_region(brand: ResolvedDocumentBranding, reference: str) -> str:
    powered = ""
    if brand.show_powered_by:
        powered = (
            '<span class="powered-by">'
            f'مدعوم من {_ltr("Orrery")} &nbsp;|&nbsp; Powered by {_ltr("Orrery")}</span>'
        )
    return (
        '<div class="doc-footer" data-locked-region="footer">'
        f'<span class="footer-ref">{_ltr(reference)}</span>'
        f'<span class="footer-brand">{powered}</span></div>'
    )


def _party_region(name: str, card: str) -> str:
    return f'<div class="party-col" data-locked-region="{name}">{card}</div>'


def _lines_head(keys: list[str]) -> str:
    cells = []
    for key in keys:
        ar, en = _pair(key)
        cells.append(
            f'<th><div class="th-ar">{_esc(ar)}</div>'
            + (f'<div class="th-en">{_esc(en)}</div>' if en != ar else "")
            + "</th>"
        )
    return "".join(cells)


def _totals_table(totals: Mapping[str, Any], currency: str) -> str:
    rows = []
    for key, field, cls in (
        ("total_taxable_amount", "total_taxable_amount", ""),
        ("total_vat_amount", "total_vat_amount", ""),
        ("grand_total", "grand_total", ' class="grand-row"'),
    ):
        ar, en = BILINGUAL_LABELS[key]
        amount = _fmt_money(totals[field], field)
        rows.append(
            f"<tr{cls}>"
            f'<th class="tot-ar">{_esc(ar)}</th>'
            f'<td class="tot-val">{_ltr(f"{amount} {currency}")}</td>'
            f'<th class="tot-en">{_esc(en)}</th></tr>'
        )
    return f'<table class="totals-table">{"".join(rows)}</table>'


def _text_block(css_class: str, key: str, body_html: str) -> str:
    return (
        f'<div class="{css_class}">'
        f'<div class="bi-row">{_bi(key, strong=True)}</div>'
        f"{body_html}</div>"
    )


def _shell(kind: str, title: tuple[str, str], reference: str, brand: ResolvedDocumentBranding,
           body: str) -> str:
    title_html = f"{_esc(title[0])} / {_esc(title[1])} — {_esc(reference)}"
    document = render_document_shell(
        kind=kind,
        title_html=title_html,
        token_block=render_token_block(brand.primary_color, brand.accent_color),
        body_html=body,
    )
    assert_locked_layout(document, kind)
    return document


# ------------------------------------------------------------------ tax invoice
def render_branded_tax_invoice_html(
    invoice_data: Mapping[str, Any],
    *,
    mode: str = "zatca_sa",
    branding: Any = None,
    entitlements: Mapping[str, Any] | None = None,
) -> str:
    """Tenant-branded bilingual tax invoice with the compliance regions locked.

    ``mode`` and the invoice payload are exactly those of ``render_tax_invoice_html`` (ERP-007);
    ``branding`` is a ``DocumentBranding`` or mapping (see ``resolve_document_branding``).
    """
    if mode not in ("zatca_sa", "neutral"):
        raise ValueError(f"Unsupported print format mode '{mode}'; expected 'zatca_sa' or 'neutral'")
    brand = resolve_document_branding(branding, entitlements=entitlements)
    view = prepare_tax_invoice_view(invoice_data, mode)

    header = _header_region(
        brand,
        _title_rows(
            (view.title_ar, view.title_en),
            '<div class="doc-badge-row">'
            f'<span class="bi-ar">{_esc(view.badge_ar)}</span>'
            f'<span class="bi-en">{_esc(view.badge_en)}</span></div>',
        ),
        view.meta_rows_html,
    )
    has_qr = bool(view.qr_html)
    kind = (
        "tax_invoice_zatca_sa" if mode == "zatca_sa"
        else "tax_invoice_neutral_qr" if has_qr else "tax_invoice_neutral"
    )
    body = (
        header
        + '<div class="parties-grid">'
        + _party_region("seller", view.seller_card)
        + _party_region("buyer", view.buyer_card)
        + "</div>"
        + view.adjustment_html
        + '<table class="lines-table" data-locked-region="lines">'
        + f"<thead><tr>{view.thead_cells}</tr></thead>"
        + f'<tbody>{"".join(view.line_rows_html)}</tbody></table>'
        + '<div class="summary-section">'
        + f'<div class="summary-totals-cell{"" if has_qr else " summary-wide"}" '
        + f'data-locked-region="totals">{view.totals_html}{view.notes_html}</div>'
        + (
            f'<div class="summary-qr-cell" data-locked-region="qr">{view.qr_html}</div>'
            if has_qr else ""
        )
        + "</div>"
        + _footer_region(brand, view.invoice_id)
    )
    return _shell(kind, (view.title_ar, view.title_en), view.invoice_id, brand, body)


# ------------------------------------------------------------------ quote and purchase order
def _need(data: Mapping[str, Any], key: str, errors: list[str]) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"Missing {key}")
        return ""
    return value.strip()


def _parse_date(value: str, key: str, errors: list[str]) -> date | None:
    if not value:
        return None
    if not _DATE_RE.fullmatch(value):
        errors.append(f"{key} '{value}' must be 'YYYY-MM-DD'")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errors.append(f"{key} '{value}' is not a real date")
        return None


def _check_party(data: Mapping[str, Any], key: str, errors: list[str]) -> None:
    party = data.get(key)
    if not isinstance(party, Mapping) or not str(party.get("name") or "").strip():
        errors.append(f"{key} name is required")


def _check_lines(data: Mapping[str, Any], errors: list[str]) -> None:
    lines = data.get("lines")
    if not isinstance(lines, list) or not lines:
        errors.append("At least one line is required")
        return
    for idx, line in enumerate(lines, start=1):
        if not isinstance(line, Mapping):
            errors.append(f"Line {idx}: must be a mapping")
            continue
        if not str(line.get("description") or "").strip():
            errors.append(f"Line {idx}: description is required")
        for field, minimum_exclusive in (("quantity", True), ("unit_price", False)):
            try:
                number = _to_dec(line.get(field), f"Line {idx} {field}")
                if (number <= _ZERO) if minimum_exclusive else (number < _ZERO):
                    errors.append(f"Line {idx}: {field} must be "
                                  f"{'positive' if minimum_exclusive else 'not negative'}")
            except ValueError as exc:
                errors.append(str(exc))


def _check_totals(data: Mapping[str, Any], errors: list[str]) -> None:
    totals = data.get("totals")
    if not isinstance(totals, Mapping) or not totals:
        errors.append("Missing totals")
        return
    try:
        taxable = _to_dec(totals.get("total_taxable_amount"), "total_taxable_amount")
        vat = _to_dec(totals.get("total_vat_amount"), "total_vat_amount")
        grand = _to_dec(totals.get("grand_total"), "grand_total")
    except ValueError as exc:
        errors.append(str(exc))
        return
    for label, value in (("Total taxable amount", taxable), ("Total VAT amount", vat),
                         ("Grand total", grand)):
        if value < _ZERO:
            errors.append(f"{label} cannot be negative")
        if value != value.quantize(_TWO_DECIMALS):
            errors.append(f"{label} '{value}' must already be rounded to 2 decimals")
    if taxable + vat != grand:
        errors.append(f"Engine totals disagree: taxable {taxable} + VAT {vat} != grand total {grand}")


def _terms(data: Mapping[str, Any]) -> list[str]:
    raw = data.get("terms")
    if raw is None or raw == "" or raw == []:
        return []
    items = [raw] if isinstance(raw, str) else raw
    if not isinstance(items, list) or len(items) > _MAX_TERMS:
        raise ValueError(f"terms must be text or a list of at most {_MAX_TERMS} items")
    out = []
    for item in items:
        if not isinstance(item, str) or len(item) > _MAX_TERM_CHARS:
            raise ValueError(f"each term must be text of at most {_MAX_TERM_CHARS} characters")
        if item.strip():
            out.append(item.strip())
    return out


def _lines_region(lines: list[Mapping[str, Any]]) -> str:
    rows = []
    for idx, line in enumerate(lines, start=1):
        qty = _to_dec(line["quantity"], "quantity")
        price = _to_dec(line["unit_price"], "unit_price")
        discount = _to_dec(line.get("discount", "0"), "discount")
        if line.get("line_total") not in (None, ""):
            amount = _to_dec(line["line_total"], "line_total")
        else:
            amount = (qty * price - discount).quantize(_TWO_DECIMALS)
        vat_raw = line.get("vat_rate", "0")
        desc_en = str(line.get("description") or "").strip()
        desc_ar = str(line.get("description_ar") or "").strip()
        desc = f'<div class="item-desc-en">{_esc(desc_en)}</div>'
        if desc_ar and desc_ar != desc_en:
            desc = f'<div class="item-desc-ar">{_esc(desc_ar)}</div>' + desc
        rows.append(
            "<tr>"
            f'<td class="num-col">{_ltr(idx)}</td>'
            f'<td class="code-col">{_ltr(str(line.get("item_code") or "").strip() or "-")}</td>'
            f'<td class="desc-col">{desc}</td>'
            f'<td class="num-col">{_ltr(_fmt_qty(qty))}</td>'
            f'<td class="num-col">{_ltr(_fmt_money(price, "unit_price"))}</td>'
            f'<td class="num-col">{_ltr(_fmt_money(discount, "discount"))}</td>'
            f'<td class="num-col">{_ltr(_fmt_pct(vat_raw) if vat_raw not in (None, "") else "0%")}</td>'
            f'<td class="num-col">{_ltr(_fmt_money(amount, "amount"))}</td>'
            "</tr>"
        )
    head = _lines_head(["line_no", "item_code", "description", "quantity", "unit_price",
                        "discount", "vat_rate", "line_amount"])
    return (
        '<table class="lines-table" data-locked-region="lines">'
        f'<thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table>'
    )


def _totals_region(data: Mapping[str, Any], currency: str) -> str:
    return (
        '<div class="summary-section"><div class="summary-totals-cell summary-wide" '
        f'data-locked-region="totals">{_totals_table(data["totals"], currency)}</div></div>'
    )


def _terms_region(data: Mapping[str, Any]) -> str:
    terms = _terms(data)
    body = "".join(f"<div>{_esc(t)}</div>" for t in terms) or (
        f'<div class="bi-row muted">{_bi("no_terms")}</div>'
    )
    notes = str(data.get("notes") or "").strip()
    notes_html = (
        _text_block("notes-box", "notes", f'<div class="notes-body">{_esc(notes)}</div>')
        if notes else ""
    )
    return (
        '<div class="terms-region" data-locked-region="terms">'
        + _text_block("terms-box", "terms", f'<div class="terms-body">{body}</div>')
        + notes_html + "</div>"
    )


def _validate_commercial(data: Mapping[str, Any], *, id_key: str, due_key: str,
                         parties: tuple[str, ...]) -> tuple[str, str, str, date | None, date | None, str]:
    errors: list[str] = []
    if not isinstance(data, Mapping):
        raise ValueError("document data must be a mapping")
    doc_id = _need(data, id_key, errors)
    issue = _need(data, "issue_date", errors)
    due = _need(data, due_key, errors)
    currency = _need(data, "currency", errors)
    issue_date = _parse_date(issue, "issue_date", errors)
    due_date = _parse_date(due, due_key, errors)
    if issue_date and due_date and due_date < issue_date:
        errors.append(f"{due_key} cannot be before issue_date")
    for party in parties:
        _check_party(data, party, errors)
    _check_lines(data, errors)
    _check_totals(data, errors)
    if errors:
        raise ValueError("; ".join(errors))
    return doc_id, issue, due, issue_date, due_date, currency


def render_branded_quote_html(
    quote_data: Mapping[str, Any],
    *,
    branding: Any = None,
    entitlements: Mapping[str, Any] | None = None,
) -> str:
    """Tenant-branded bilingual quotation (not a tax invoice; no QR)."""
    brand = resolve_document_branding(branding, entitlements=entitlements)
    quote_id, issue, valid_until, _i, _v, currency = _validate_commercial(
        quote_data, id_key="quote_id", due_key="valid_until", parties=("seller", "buyer")
    )
    status = quote_data.get("status")
    pill = ""
    if status is not None:
        if status not in QUOTE_STATUSES:
            raise ValueError(f"status must be one of {sorted(QUOTE_STATUSES)}")
        token, icon, label_key = QUOTE_STATUSES[status]
        pill = (
            f'<div><span class="status-pill status-{token}">'
            f'<span class="status-icon" aria-hidden="true">{icon}</span>'
            f"{_bi('status')}: {_bi(label_key)}</span></div>"
        )
    meta = [
        (_pair("quote_number"), _ltr(quote_id)),
        (_pair("issue_date"), _ltr(issue)),
        (_pair("valid_until"), _ltr(valid_until)),
    ]
    reference = str(quote_data.get("reference") or "").strip()
    if reference:
        meta.append((_pair("customer_reference"), _ltr(reference)))
    meta.append((_pair("currency"), _ltr(currency)))
    body = (
        _header_region(brand, _title_rows(_pair("quote_title"), pill), _meta_rows(meta))
        + '<div class="parties-grid">'
        + _party_region("seller", _render_party_card(*_pair("seller"), quote_data["seller"]))
        + _party_region("buyer", _render_party_card(*_pair("customer"), quote_data["buyer"]))
        + "</div>"
        + _lines_region(quote_data["lines"])
        + _totals_region(quote_data, currency)
        + _terms_region(quote_data)
        + _footer_region(brand, quote_id)
    )
    return _shell("quote", _pair("quote_title"), quote_id, brand, body)


def render_branded_purchase_order_html(
    po_data: Mapping[str, Any],
    *,
    branding: Any = None,
    entitlements: Mapping[str, Any] | None = None,
) -> str:
    """Tenant-branded bilingual purchase order (not a tax invoice; no QR)."""
    brand = resolve_document_branding(branding, entitlements=entitlements)
    po_id, issue, required_by, _i, _r, currency = _validate_commercial(
        po_data, id_key="po_id", due_key="required_by", parties=("buyer", "supplier")
    )
    meta = [
        (_pair("po_number"), _ltr(po_id)),
        (_pair("issue_date"), _ltr(issue)),
        (_pair("required_by"), _ltr(required_by)),
    ]
    payment_terms = str(po_data.get("payment_terms") or "").strip()
    if payment_terms:
        meta.append((_pair("payment_terms"), _esc(payment_terms)))
    meta.append((_pair("currency"), _ltr(currency)))
    delivery = po_data.get("delivery")
    if delivery is not None and not isinstance(delivery, Mapping):
        raise ValueError("delivery must be a mapping")
    delivery_card = _render_party_card(
        *_pair("delivery_address"), delivery or None,
        fallback_none_ar=_pair("delivery_unspecified")[0],
        fallback_none_en=_pair("delivery_unspecified")[1],
    )
    body = (
        _header_region(brand, _title_rows(_pair("po_title"), ""), _meta_rows(meta))
        + '<div class="parties-grid">'
        + _party_region("buyer", _render_party_card(*_pair("buyer"), po_data["buyer"]))
        + _party_region("supplier", _render_party_card(*_pair("supplier"), po_data["supplier"]))
        + "</div>"
        + f'<div class="delivery-box" data-locked-region="delivery">{delivery_card}</div>'
        + _lines_region(po_data["lines"])
        + _totals_region(po_data, currency)
        + _terms_region(po_data)
        + _footer_region(brand, po_id)
    )
    return _shell("purchase_order", _pair("po_title"), po_id, brand, body)


__all__ = [
    "DOCUMENT_LABELS",
    "render_branded_purchase_order_html",
    "render_branded_quote_html",
    "render_branded_tax_invoice_html",
]
