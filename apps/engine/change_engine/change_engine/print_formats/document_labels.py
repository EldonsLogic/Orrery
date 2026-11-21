"""Bilingual labels for the branded quote and purchase order templates (ERP-016).

Labels shared with the tax invoice stay in ``BILINGUAL_LABELS`` (ERP-007). The labels below are
new in ERP-016. Their Arabic wording was drafted without a native-speaker review and is
UNREVIEWED under ADR-0033 (a native Arabic speaker must review the document set before any
customer sees it). Every key here is listed in ``UNREVIEWED_ARABIC_LABELS``; a reviewer removes a
key from that set only after approving its wording.

Renderers read every label through ``label_pair``. Outside dev and test (``CHANGE_ENGINE_ENV`` not
``dev`` or ``test``; unset counts as production, as in ERP-027) a document that needs an
unreviewed Arabic label is refused with ``UnreviewedArabicLabelError`` (round 6, fail closed).
"""

from __future__ import annotations

import os

from .bilingual_tax_invoice import BILINGUAL_LABELS

ENGINE_ENV_VAR = "CHANGE_ENGINE_ENV"
REVIEW_EXEMPT_ENVS = frozenset({"dev", "test"})


class UnreviewedArabicLabelError(RuntimeError):
    """A document needs an Arabic label no native speaker has approved yet (ADR-0033)."""

    code = "unreviewed_arabic_label"

    def __init__(self, key: str) -> None:
        super().__init__(f"{self.code}: label '{key}' needs a native Arabic review before it "
                         "can print outside dev and test")
        self.key = key

DOCUMENT_LABELS: dict[str, tuple[str, str]] = {
    "quote_title": ("عرض سعر", "Quotation"),
    "quote_number": ("رقم العرض", "Quote Number"),
    "valid_until": ("صالح حتى", "Valid Until"),
    "customer_reference": ("مرجع العميل", "Customer Reference"),
    "terms": ("الشروط والأحكام", "Terms & Conditions"),
    "no_terms": ("لا توجد شروط إضافية", "No additional terms"),
    "po_title": ("أمر شراء", "Purchase Order"),
    "po_number": ("رقم أمر الشراء", "PO Number"),
    "supplier": ("المورّد", "Supplier"),
    "buyer": ("المشتري", "Buyer"),
    "required_by": ("تاريخ التسليم المطلوب", "Required Delivery Date"),
    "delivery_address": ("عنوان التسليم", "Delivery Address"),
    "delivery_unspecified": ("غير محدد", "Not specified"),
    "payment_terms": ("شروط الدفع", "Payment Terms"),
    "status": ("الحالة", "Status"),
    "powered_by": ("مدعوم من المنصة", "Powered by the platform"),
    "status_pending": ("قيد الانتظار", "Pending"),
    "status_accepted": ("مقبول", "Accepted"),
    "status_expired": ("منتهي", "Expired"),
    # Informational only (ERP-016 round 5, Q-520): the invoice discount the engine spread into
    # the line amounts, shown on its own; it is never subtracted again.
    "invoice_discount_included": ("خصم الفاتورة (مشمول في مبالغ البنود)",
                                  "Invoice discount (included in line amounts)"),
}

UNREVIEWED_ARABIC_LABELS: frozenset[str] = frozenset(DOCUMENT_LABELS)

_overlap = set(DOCUMENT_LABELS) & set(BILINGUAL_LABELS)
if _overlap:  # pragma: no cover - import-time guard against silently shadowing reviewed copy
    raise RuntimeError(f"ERP-016 labels shadow reviewed ERP-007 labels: {sorted(_overlap)}")

ALL_LABELS: dict[str, tuple[str, str]] = {**BILINGUAL_LABELS, **DOCUMENT_LABELS}


def label_pair(key: str) -> tuple[str, str]:
    """(Arabic, English) for ``key``; refuses an unreviewed Arabic label outside dev and test."""
    if key in UNREVIEWED_ARABIC_LABELS and \
            os.environ.get(ENGINE_ENV_VAR, "").strip().lower() not in REVIEW_EXEMPT_ENVS:
        raise UnreviewedArabicLabelError(key)
    return ALL_LABELS[key]

# Quote status -> (fixed status token, icon). Colour is never the only signal (rule 40).
QUOTE_STATUSES: dict[str, tuple[str, str, str]] = {
    "pending": ("warning", "!", "status_pending"),
    "accepted": ("success", "✓", "status_accepted"),
    "expired": ("danger", "×", "status_expired"),
}
