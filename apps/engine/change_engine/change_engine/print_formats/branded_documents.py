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
from typing import Any, Mapping

from .bilingual_tax_invoice import (
    BILINGUAL_LABELS,
    _DATE_RE,
    _ZERO,
    _esc,
    _fmt_pct,
    _fmt_qty,
    _ltr,
    _render_party_card,
    _to_dec,
    prepare_tax_invoice_view,
)
from .brand_tokens import ResolvedDocumentBranding, resolve_document_branding
from .document_labels import DOCUMENT_LABELS, QUOTE_STATUSES, label_pair
from .document_reconciliation import (
    CheckedAmounts,
    check_amounts,
    format_amount,
    format_unit_price,
    in_print_context,
    snapshot_document,
)
from .document_layout import assert_locked_layout, render_document_shell, render_token_block

_MAX_TERMS = 50
_MAX_TERM_CHARS = 1000
# Supplier country values and the currency that make a neutral invoice a UAE one (round 6).
_UAE_COUNTRIES = frozenset({"AE", "ARE", "UNITED ARAB EMIRATES"})
_UAE_CURRENCY = "AED"
# ZATCA invoice type -> locked layout kind; anything else is refused.
_ZATCA_KINDS = {"standard": "tax_invoice_zatca_sa_standard",
                "simplified": "tax_invoice_zatca_sa_simplified"}


class UaeTaxInvoiceModeUnavailable(ValueError):
    """Neutral mode cannot print a UAE tax invoice; there is no UAE mode yet (Q-553).

    UNVERIFIED: Cabinet Decision 52/2017 Art. 59(1) (https://tax.gov.ae/en/legislation.aspx,
    accessed 2026-11-21) asks for the words "Tax Invoice", the supplier TRN (and the recipient's
    when registered) and the tax in AED; the neutral layout guarantees none of them.
    """

    code = "uae_tax_invoice_mode_unavailable"

    def __init__(self) -> None:
        super().__init__(f"{self.code}: a UAE supplier or an AED invoice needs a UAE tax invoice "
                         "mode, which does not exist yet")


# ------------------------------------------------------------------ shared fragments
def _pair(key: str) -> tuple[str, str]:
    return label_pair(key)


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
        ar, en = _pair("powered_by")
        powered = f'<span class="powered-by">{_esc(ar)} &nbsp;|&nbsp; {_esc(en)}</span>'
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


def _totals_table(checked: CheckedAmounts, currency: str) -> str:
    rows = []
    entries = [("total_taxable_amount", checked.taxable, ""),
               ("total_vat_amount", checked.vat, ""),
               ("grand_total", checked.grand, ' class="grand-row"')]
    if checked.discount > 0:
        # Only the part of the document discount the printed line amounts do not carry, so the
        # printed lines less this row equal the taxable total.
        entries.insert(0, ("discount", checked.discount, ""))
    for key, value, cls in entries:
        ar, en = BILINGUAL_LABELS[key]
        amount = format_amount(value, checked.precision)
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
@in_print_context
def render_branded_tax_invoice_html(
    invoice_data: Mapping[str, Any],
    *,
    mode: str = "zatca_sa",
    branding: Any = None,
    entitlements: Mapping[str, Any] | None = None,
    locale: dict[str, Any] | None = None,
    compliance_profile: dict[str, Any] | None = None,
    country_default: bool | None = False,
) -> str:
    """Tenant-branded bilingual tax invoice with the compliance regions locked.

    ``mode`` and the invoice payload are exactly those of ``render_tax_invoice_html`` (ERP-007);
    ``branding`` is a ``DocumentBranding`` or mapping (see ``resolve_document_branding``).
    ``locale`` and ``compliance_profile`` decide the Hijri date row as in
    ``render_tax_invoice_html`` (CMP-005); like the engine print path, it is off unless the
    settings enable it (``country_default=None`` restores the per-mode default).
    """
    if mode not in ("zatca_sa", "neutral"):
        raise ValueError(f"Unsupported print format mode '{mode}'; expected 'zatca_sa' or 'neutral'")
    brand = resolve_document_branding(branding, entitlements=entitlements)
    # Snapshot once, check that copy, and print from the checked snapshot (its checked numeric
    # fields are the Decimal values the check used): the caller's objects are never read again.
    snapshot = snapshot_document(invoice_data)
    if mode == "neutral" and _is_uae_invoice(snapshot):
        raise UaeTaxInvoiceModeUnavailable()
    errors: list[str] = []
    checked = check_amounts(snapshot, errors, tax_invoice=True)
    if errors or checked is None:
        raise ValueError("; ".join(errors))
    # ZATCA lists line and invoice discounts separately (UNVERIFIED, Q-552): in tax invoice mode
    # the invoice discount already spread into the lines is also shown on an informational row.
    included = (
        (_pair("invoice_discount_included"), checked.allocated)
        if mode == "zatca_sa" and checked.allocated > 0 else None
    )
    view = prepare_tax_invoice_view(checked.document, mode, discount_row=checked.discount,
                                    included_discount_row=included, locale=locale,
                                    compliance_profile=compliance_profile,
                                    country_default=country_default)

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
    if mode == "zatca_sa":
        kind = _ZATCA_KINDS.get(view.invoice_type)
        if kind is None:
            raise ValueError(f"Unsupported ZATCA invoice type '{view.invoice_type}'")
    else:
        kind = "tax_invoice_neutral_qr" if has_qr else "tax_invoice_neutral"
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


def _country(value: Any) -> str:
    return value.strip().upper() if isinstance(value, str) else ""


def _is_uae_invoice(data: Mapping[str, Any]) -> bool:
    """True when the supplier is in the UAE or the invoice is in AED (any spelling we accept)."""
    if _country(data.get("currency")) == _UAE_CURRENCY:
        return True
    seller = data.get("seller")
    if not isinstance(seller, Mapping):
        return False
    address = seller.get("address")
    countries = [seller.get("country_code"), seller.get("country")]
    if isinstance(address, Mapping):
        countries += [address.get("country_code"), address.get("country")]
    return any(_country(value) in _UAE_COUNTRIES for value in countries)


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
        # A line without its rate would print 0% while the totals carry VAT (round 6).
        rate = line.get("vat_rate")
        if rate is None or (isinstance(rate, str) and not rate.strip()):
            errors.append(f"Line {idx}: vat_rate is required")
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


def _lines_region(lines: list[Mapping[str, Any]], checked: CheckedAmounts) -> str:
    places = checked.precision
    rows = []
    for idx, (line, row) in enumerate(zip(lines, checked.lines), start=1):
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
            f'<td class="num-col">{_ltr(_fmt_qty(row.quantity))}</td>'
            f'<td class="num-col">{_ltr(format_unit_price(row.unit_price, places))}</td>'
            f'<td class="num-col">{_ltr(format_amount(row.shown_discount, places))}</td>'
            f'<td class="num-col">{_ltr(_fmt_pct(row.vat_rate))}</td>'
            f'<td class="num-col">{_ltr(format_amount(row.amount, places))}</td>'
            "</tr>"
        )
    head = _lines_head(["line_no", "item_code", "description", "quantity", "unit_price",
                        "discount", "vat_rate", "line_amount"])
    return (
        '<table class="lines-table" data-locked-region="lines">'
        f'<thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table>'
    )


def _totals_region(currency: str, checked: CheckedAmounts) -> str:
    return (
        '<div class="summary-section"><div class="summary-totals-cell summary-wide" '
        'data-locked-region="totals">'
        f'{_totals_table(checked, currency)}'
        "</div></div>"
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
                         parties: tuple[str, ...]
                         ) -> tuple[str, str, str, str, CheckedAmounts]:
    """Check the snapshot ``data``; the caller prints only from ``checked.document``."""
    errors: list[str] = []
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
    checked = check_amounts(data, errors)
    if errors or checked is None:
        raise ValueError("; ".join(dict.fromkeys(errors)))
    return doc_id, issue, due, currency, checked


@in_print_context
def render_branded_quote_html(
    quote_data: Mapping[str, Any],
    *,
    branding: Any = None,
    entitlements: Mapping[str, Any] | None = None,
) -> str:
    """Tenant-branded bilingual quotation (not a tax invoice; no QR)."""
    brand = resolve_document_branding(branding, entitlements=entitlements)
    quote_id, issue, valid_until, currency, checked = _validate_commercial(
        snapshot_document(quote_data), id_key="quote_id", due_key="valid_until",
        parties=("seller", "buyer")
    )
    quote_data = checked.document
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
        + _lines_region(quote_data["lines"], checked)
        + _totals_region(currency, checked)
        + _terms_region(quote_data)
        + _footer_region(brand, quote_id)
    )
    return _shell("quote", _pair("quote_title"), quote_id, brand, body)


@in_print_context
def render_branded_purchase_order_html(
    po_data: Mapping[str, Any],
    *,
    branding: Any = None,
    entitlements: Mapping[str, Any] | None = None,
) -> str:
    """Tenant-branded bilingual purchase order (not a tax invoice; no QR)."""
    brand = resolve_document_branding(branding, entitlements=entitlements)
    po_id, issue, required_by, currency, checked = _validate_commercial(
        snapshot_document(po_data), id_key="po_id", due_key="required_by",
        parties=("buyer", "supplier")
    )
    po_data = checked.document
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
        + _lines_region(po_data["lines"], checked)
        + _totals_region(currency, checked)
        + _terms_region(po_data)
        + _footer_region(brand, po_id)
    )
    return _shell("purchase_order", _pair("po_title"), po_id, brand, body)


__all__ = [
    "DOCUMENT_LABELS",
    "UaeTaxInvoiceModeUnavailable",
    "render_branded_purchase_order_html",
    "render_branded_quote_html",
    "render_branded_tax_invoice_html",
]
