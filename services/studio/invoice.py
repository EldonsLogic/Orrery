"""Invoice view from the synthetic dataset (DAT-002). Every figure is copied verbatim from the dataset's stored `expected`
block (synthetic test expectations, not tax output); nothing is added, multiplied or rounded here. The QR payload is
encoded by the real Phase 1 encoder (CMP-003) from those stored figures and decoded back with its decoder."""
from __future__ import annotations

from . import _paths  # noqa: F401  (import path setup)
from .session import StudioError
from components.compliance.zatca_sa.phase1 import decode_phase1_tlv, encode_phase1_tlv  # type: ignore  # noqa: E402
from services.datasets.loader import load_market  # type: ignore  # noqa: E402

MARKETS = {"ksa": "SA", "uae": "AE", "egy": "EG", "qat": "QA"}
LANGS = ("en", "ar")


def _names(record: dict | None) -> dict:
    record = record or {}
    return {"ar": record.get("name_ar"), "en": record.get("name_en")}


def invoice_view(market: str, lang: str, invoice_id: str | None = None) -> dict:
    if market not in MARKETS:
        raise StudioError(400, "STUDIO-QUERY-MARKET", "/market", allowed=sorted(MARKETS))
    if lang not in LANGS:
        raise StudioError(400, "STUDIO-QUERY-LANG", "/lang", allowed=list(LANGS))
    data = load_market(MARKETS[market])  # verifies the file against manifest.json (raises ValueError on a mismatch)
    invoices = data["sales_invoices"]
    inv = invoices[0] if invoice_id is None else next((i for i in invoices if i["id"] == invoice_id), None)
    if inv is None:
        raise StudioError(404, "STUDIO-INVOICE-UNKNOWN", "/invoice")
    tenant = data["tenant"]
    items = {i["code"]: i for i in data["items"]}
    units = {u["code"]: u for u in data["units"]}
    customer = next((c for c in data["customers"] if c["code"] == inv["customer"]), {})
    expected = inv["expected"]
    seller_name = tenant["legal_name_ar"]
    timestamp = inv["invoice_date"]
    payload = encode_phase1_tlv(seller_name, tenant["vat_number"], timestamp, expected["total"], expected["vat_amount"])
    tags = decode_phase1_tlv(payload)
    lines = []
    for ln in inv["lines"]:
        item = items.get(ln["item"], {})
        lines.append({"item": ln["item"], "name": _names(item), "unit": _names(units.get(item.get("unit"))),
                      "quantity": ln["quantity"], "unitPrice": ln["unit_price"],
                      "discountPercent": ln["discount_percent"], "lineNet": ln["line_net"]})
    return {"ok": True, "market": market, "country": data["meta"]["market"], "lang": lang,
            "dir": "rtl" if lang == "ar" else "ltr", "synthetic": True,
            "label": data["expected"]["label"], "notice": data["meta"].get("notice"),
            "currency": data["meta"]["currency"], "countryName": {"ar": data["meta"].get("country_ar"),
                                                                    "en": data["meta"].get("country_en")},
            "vatRatePercent": data["config"]["vat"]["rate_percent"], "vatRateSource": data["config"]["vat"]["source"],
            "invoices": [i["id"] for i in invoices],
            "invoice": {"id": inv["id"], "date": inv["invoice_date"], "dueDate": inv.get("due_date"),
                        "salesOrder": inv.get("sales_order"), "deliveryNote": inv.get("delivery_note"),
                        "discountPercent": inv.get("discount_percent")},
            "seller": {"legalName": {"ar": tenant["legal_name_ar"], "en": tenant["legal_name_en"]},
                       "vatNumber": tenant["vat_number"], "crNumber": tenant.get("cr_number")},
            "buyer": {"name": _names(customer), "code": customer.get("code"), "vatNumber": customer.get("vat_number")},
            "lines": lines, "expected": expected,
            "qr": {"payload": payload, "tags": {str(k): v for k, v in sorted(tags.items())},
                   "inputs": {"1": "tenant.legal_name_ar", "2": "tenant.vat_number", "3": "invoice_date",
                              "4": "expected.total", "5": "expected.vat_amount"}}}
