"""Bilingual Arabic/English print formats for change_engine (ERP-007)."""

from .bilingual_tax_invoice import (
    BILINGUAL_LABELS,
    DEFAULT_BRANDING_PRIMARY,
    InvoiceBranding,
    contrast_ratio_on_white,
    install_bilingual_tax_invoice_print_format,
    render_frappe_sales_invoice_html,
    render_tax_invoice_html,
    render_tax_invoice_pdf,
    resolve_invoice_branding,
    sales_invoice_to_zatca_dict,
)
from .brand_assets import BrandAssetError, SanitizedLogo, sanitize_brand_logo
from .brand_tokens import (
    ENTITLEMENT_REMOVE_POWERED_BY,
    BrandingError,
    DocumentBranding,
    ResolvedDocumentBranding,
    contrast_ratio,
    resolve_document_branding,
)
from .branded_documents import (
    render_branded_purchase_order_html,
    render_branded_quote_html,
    render_branded_tax_invoice_html,
)
from .document_labels import UNREVIEWED_ARABIC_LABELS
from .document_layout import (
    LockedLayoutViolation,
    assert_locked_layout,
    verify_locked_layout,
)
from .qr_svg import build_qr_matrix, render_qr_svg


def __getattr__(name: str):  # LOCKED_DOCUMENT_CSS reads the token file, so it loads on first use
    if name == "LOCKED_DOCUMENT_CSS":
        from . import document_layout

        return document_layout.LOCKED_DOCUMENT_CSS
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "BILINGUAL_LABELS",
    "BrandAssetError",
    "BrandingError",
    "DEFAULT_BRANDING_PRIMARY",
    "DocumentBranding",
    "ENTITLEMENT_REMOVE_POWERED_BY",
    "InvoiceBranding",
    "LockedLayoutViolation",
    "ResolvedDocumentBranding",
    "SanitizedLogo",
    "UNREVIEWED_ARABIC_LABELS",
    "assert_locked_layout",
    "contrast_ratio",
    "render_branded_purchase_order_html",
    "render_branded_quote_html",
    "render_branded_tax_invoice_html",
    "resolve_document_branding",
    "sanitize_brand_logo",
    "verify_locked_layout",
    "build_qr_matrix",
    "contrast_ratio_on_white",
    "install_bilingual_tax_invoice_print_format",
    "render_frappe_sales_invoice_html",
    "render_qr_svg",
    "render_tax_invoice_html",
    "render_tax_invoice_pdf",
    "resolve_invoice_branding",
    "sales_invoice_to_zatca_dict",
]
