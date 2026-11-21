"""ERP-016: tenant-branded bilingual tax invoice, quote and purchase order templates.

Covers ADR-0014 guardrails (token-only branding, WCAG AA, asset sanitising, Powered-by
entitlement), the locked compliance layout, ADR-0016 engine invisibility and ADR-0033 Arabic
review marking. All data is synthetic.
"""

from __future__ import annotations

import base64
import json
import re
import struct
import tempfile
import unittest
import zlib
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock

from change_engine.compliance import ZatcaValidationError, decode_phase1_tlv
from change_engine.print_formats import (
    BILINGUAL_LABELS,
    BrandAssetError,
    BrandingError,
    DocumentBranding,
    ENTITLEMENT_REMOVE_POWERED_BY,
    LOCKED_DOCUMENT_CSS,
    LockedLayoutViolation,
    UNREVIEWED_ARABIC_LABELS,
    assert_locked_layout,
    contrast_ratio,
    render_branded_purchase_order_html,
    render_branded_quote_html,
    render_branded_tax_invoice_html,
    resolve_document_branding,
    sanitize_brand_logo,
    verify_locked_layout,
)
from change_engine.print_formats.document_layout import PRINT_SURFACES, STATUS_TOKENS

SVG_NS = 'xmlns="http://www.w3.org/2000/svg"'
GOOD_SVG = (
    f'<svg {SVG_NS} viewBox="0 0 100 40"><rect width="100" height="40" fill="#0b5fa5"/>'
    '<text x="5" y="25" font-size="12" fill="#ffffff">Al Noor</text></svg>'
)
EVIL_SVG = (
    f'<svg {SVG_NS} xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 100 40" '
    'onload="alert(1)">'
    "<script>alert(1)</script>"
    '<rect width="10" height="10" fill="javascript:alert(1)" onclick="x()" '
    'style="fill:url(https://evil.example/x)"/>'
    '<foreignObject><div xmlns="http://www.w3.org/1999/xhtml">hi</div></foreignObject>'
    '<image href="https://evil.example/x.png" width="10" height="10"/>'
    '<use xlink:href="https://evil.example/s.svg#a"/>'
    '<a xlink:href="javascript:alert(1)"><circle r="5" cx="5" cy="5"/></a>'
    "<style>@import url(https://evil.example/x.css); rect{fill:red}</style>"
    '<animate attributeName="x" from="0" to="1"/>'
    '<path d="M0 0L10 10" fill="jav&#x61;script:alert(2)"/>'
    "</svg>"
)


def _png(width: int = 600, height: int = 600, *, extra_chunks: list | None = None,
         trailing: bytes = b"") -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    rows = b"".join(b"\x00" + b"\x00\x00\x00\x00" * min(width, 4) for _ in range(min(height, 4)))
    out = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
    for kind, data in extra_chunks or []:
        out += chunk(kind, data)
    out += chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")
    return out + trailing


def _jpeg(width: int = 600, height: int = 600, *, trailing: bytes = b"",
          comment: bytes = b"") -> bytes:
    out = b"\xff\xd8"
    if comment:
        out += b"\xff\xfe" + struct.pack(">H", len(comment) + 2) + comment
    out += b"\xff\xdb" + struct.pack(">H", 67) + b"\x00" + bytes(range(1, 65))
    out += b"\xff\xc0" + struct.pack(">H", 11) + b"\x08" + struct.pack(">HH", height, width)
    out += b"\x01\x01\x11\x00"
    out += b"\xff\xda" + struct.pack(">H", 8) + b"\x01\x01\x00\x00\x3f\x00" + b"\x12\x34"
    return out + b"\xff\xd9" + trailing


def _uri(raw: bytes | str, mime: str) -> str:
    data = raw.encode("utf-8") if isinstance(raw, str) else raw
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def _tax_invoice_data() -> dict:
    return {
        "invoice_id": "INV-2026-0001",
        "issue_date": "2026-11-17",
        "issue_time": "14:30:00",
        "hijri_date": "1448-06-07",
        "timezone": "Asia/Riyadh",
        "currency": "SAR",
        "invoice_type": "standard",
        "transaction_type": "tax_invoice",
        "seller": {
            "name": "Al-Noor Trading Est",
            "name_ar": "مؤسسة النور للتجارة",
            "vat_number": "300000000000003",
            "cr_number": "1010123456",
            "address": {
                "street": "King Fahd Road", "street_ar": "طريق الملك فهد",
                "building_no": "1234", "postal_code": "12345",
                "city": "Riyadh", "city_ar": "الرياض",
                "district": "Al-Olaya", "district_ar": "العليا", "country_code": "SA",
            },
        },
        "buyer": {
            "name": "Gulf Enterprises LLC",
            "name_ar": "شركة المشاريع الخليجية",
            "vat_number": "310122393500003",
            "address": {
                "street": "Prince Sultan Street", "street_ar": "شارع الأمير سلطان",
                "building_no": "5678", "postal_code": "23456",
                "city": "Jeddah", "city_ar": "جدة",
                "district": "Al-Rawdah", "district_ar": "الروضة", "country_code": "SA",
            },
        },
        "lines": [
            {
                "item_code": "ITEM-001", "description": "Office Desk Chair",
                "description_ar": "كرسي مكتب", "quantity": "2", "unit_price": "100.00",
                "discount": "0.00", "vat_rate": "0.15", "vat_category": "S",
            }
        ],
        "totals": {
            "total_taxable_amount": "200.00", "total_vat_amount": "30.00",
            "grand_total": "230.00",
        },
    }


def _neutral_invoice_data() -> dict:
    return {
        "invoice_id": "SINV-QA-0001", "issue_date": "2026-11-17", "currency": "QAR",
        "transaction_type": "invoice",
        "seller": {"name": "Golden Trading Co", "name_ar": "شركة التجارة الذهبية"},
        "buyer": {"name": "CUST-001", "name_ar": "العميل الأول"},
        "lines": [
            {
                "item_code": "ITEM-001", "description": "Trading Item (piece)",
                "description_ar": "صنف تجاري (قطعة)", "quantity": "10",
                "unit_price": "15.00", "discount": "0.00", "vat_rate": "0",
                "vat_category": "",
            }
        ],
        "totals": {
            "total_taxable_amount": "150.00", "total_vat_amount": "0.00",
            "grand_total": "150.00",
        },
    }


def _quote_data() -> dict:
    return {
        "quote_id": "QTN-2026-0007",
        "issue_date": "2026-11-17",
        "valid_until": "2026-12-17",
        "reference": "RFQ-5521",
        "currency": "SAR",
        "status": "pending",
        "seller": {
            "name": "Al-Noor Trading Est", "name_ar": "مؤسسة النور للتجارة",
            "vat_number": "300000000000003", "cr_number": "1010123456",
        },
        "buyer": {
            "name": "Gulf Enterprises LLC", "name_ar": "شركة المشاريع الخليجية",
            "vat_number": "310122393500003",
        },
        "lines": [
            {
                "item_code": "ITEM-001", "description": "Office Desk Chair",
                "description_ar": "كرسي مكتب", "quantity": "2", "unit_price": "100.00",
                "discount": "0.00", "vat_rate": "0.15",
            }
        ],
        "totals": {
            "total_taxable_amount": "200.00", "total_vat_amount": "30.00",
            "grand_total": "230.00",
        },
        "terms": ["Prices valid for 30 days", "Payment within 30 days of invoice"],
        "notes": "Delivery included",
    }


def _po_data() -> dict:
    return {
        "po_id": "PO-2026-0042",
        "issue_date": "2026-11-17",
        "required_by": "2026-12-01",
        "currency": "SAR",
        "buyer": {
            "name": "Al-Noor Trading Est", "name_ar": "مؤسسة النور للتجارة",
            "vat_number": "300000000000003", "cr_number": "1010123456",
        },
        "supplier": {
            "name": "Gulf Supplies LLC", "name_ar": "شركة الخليج للتوريدات",
            "vat_number": "310122393500003",
        },
        "delivery": {
            "name": "Main Warehouse", "name_ar": "المستودع الرئيسي",
            "address": {"street": "Industrial Area", "city": "Riyadh", "city_ar": "الرياض",
                        "country_code": "SA"},
        },
        "payment_terms": "Net 30",
        "lines": [
            {
                "item_code": "RAW-9", "description": "Steel Sheet 2mm",
                "description_ar": "ألواح فولاذ 2 مم", "quantity": "50", "unit_price": "10.00",
                "discount": "0.00", "vat_rate": "0.15",
            }
        ],
        "totals": {
            "total_taxable_amount": "500.00", "total_vat_amount": "75.00",
            "grand_total": "575.00",
        },
        "terms": "Goods must be delivered with the PO number on the packing list",
    }


def _render(kind: str, **kwargs) -> str:
    if kind == "tax":
        return render_branded_tax_invoice_html(_tax_invoice_data(), mode="zatca_sa", **kwargs)
    if kind == "neutral":
        return render_branded_tax_invoice_html(_neutral_invoice_data(), mode="neutral", **kwargs)
    if kind == "quote":
        return render_branded_quote_html(_quote_data(), **kwargs)
    if kind == "po":
        return render_branded_purchase_order_html(_po_data(), **kwargs)
    raise AssertionError(kind)


LAYOUT_KIND = {
    "tax": "tax_invoice_zatca_sa", "neutral": "tax_invoice_neutral",
    "quote": "quote", "po": "purchase_order",
}
ALL_KINDS = tuple(LAYOUT_KIND)

TENANT_BRANDING = {
    "display_name": {"ar": "النخلة للتجارة", "en": "Al Nakhla Trading"},
    "primary_color": "#0B5FA5",
}


def _regions(doc: str) -> list[str]:
    return re.findall(r'data-locked-region="([a-z_]+)"', doc)


def _style_block(doc: str) -> str:
    return re.search(r"<style>(.*?)</style>", doc, re.S).group(1)


def _css_outside_root(css: str) -> str:
    return re.sub(r":root\s*\{[^}]*\}", "", css)


class _TagCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict]] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    handle_startendtag = handle_starttag


def _tags(doc: str) -> list[tuple[str, dict]]:
    collector = _TagCollector()
    collector.feed(doc)
    return collector.tags


# --------------------------------------------------------------------------------------
# Brand asset sanitising (SEC-018 rules applied at render time)
# --------------------------------------------------------------------------------------
class TestBrandAssets(unittest.TestCase):
    def test_png_and_jpeg_accepted_and_reencoded_without_metadata(self):
        png = sanitize_brand_logo(_uri(_png(extra_chunks=[(b"tEXt", b"Comment\x00<script>")]),
                                       "image/png"))
        self.assertEqual(png.mime, "image/png")
        self.assertTrue(png.data_uri.startswith("data:image/png;base64,"))
        out = base64.b64decode(png.data_uri.split(",", 1)[1])
        self.assertNotIn(b"tEXt", out)
        self.assertNotIn(b"<script>", out)
        self.assertEqual(len(png.sha256), 64)

        jpg = sanitize_brand_logo(_uri(_jpeg(comment=b"<script>alert(1)</script>"), "image/jpeg"))
        self.assertTrue(jpg.data_uri.startswith("data:image/jpeg;base64,"))
        self.assertNotIn(b"<script>", base64.b64decode(jpg.data_uri.split(",", 1)[1]))

    def test_raw_bytes_are_accepted(self):
        self.assertEqual(sanitize_brand_logo(_png()).mime, "image/png")
        self.assertEqual(sanitize_brand_logo(GOOD_SVG.encode()).mime, "image/svg+xml")

    def test_rejects_disallowed_or_mismatched_types(self):
        cases = {
            "gif": _uri(b"GIF89a" + b"\x00" * 40, "image/gif"),
            "exe renamed png": _uri(b"MZ\x90\x00" + b"\x00" * 200, "image/png"),
            "html": _uri("<html><script>alert(1)</script></html>", "text/html"),
            "jpeg declared as png": _uri(_jpeg(), "image/png"),
            "png declared as svg": _uri(_png(), "image/svg+xml"),
            "empty": _uri(b"", "image/png"),
            "external url": "https://evil.example/logo.png",
            "not base64": "data:image/png;base64,@@@@",
            "webp": _uri(b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/webp"),
        }
        for name, source in cases.items():
            with self.subTest(name), self.assertRaises(BrandAssetError):
                sanitize_brand_logo(source)

    def test_rejects_polyglots_trailing_data_apng_and_bad_crc(self):
        with self.assertRaises(BrandAssetError):
            sanitize_brand_logo(_png(trailing=b"<script>alert(1)</script>"))
        with self.assertRaises(BrandAssetError):
            sanitize_brand_logo(_jpeg(trailing=b"<html>"))
        with self.assertRaises(BrandAssetError):
            sanitize_brand_logo(_png(extra_chunks=[(b"acTL", struct.pack(">II", 2, 0))]))
        broken = bytearray(_png())
        broken[40] ^= 0xFF  # corrupt a CRC / data byte
        with self.assertRaises(BrandAssetError):
            sanitize_brand_logo(bytes(broken))

    def test_size_and_dimension_limits(self):
        with self.assertRaises(BrandAssetError):
            sanitize_brand_logo(_png(5000, 100))
        with self.assertRaises(BrandAssetError):
            sanitize_brand_logo(_png(trailing=b"") + b"\x00" * (2 * 1024 * 1024 + 1))
        big_svg = GOOD_SVG.replace("</svg>", "<!--" + "a" * 210_000 + "--></svg>")
        with self.assertRaises(BrandAssetError):
            sanitize_brand_logo(big_svg)

    def test_svg_attack_payload_is_stripped_to_safe_drawable(self):
        logo = sanitize_brand_logo(EVIL_SVG)
        self.assertEqual(logo.mime, "image/svg+xml")
        svg = base64.b64decode(logo.data_uri.split(",", 1)[1]).decode("utf-8")
        lowered = svg.lower()
        for needle in ("script", "onload", "onclick", "javascript", "foreignobject", "<image",
                       "<style", "@import", "evil.example", "style=", "<a ", "<animate",
                       "xlink:href", "href="):
            self.assertNotIn(needle, lowered, needle)
        self.assertIn("<path", svg)
        self.assertTrue(logo.changes)  # every strip is reported for the audit trail

    def test_svg_output_is_idempotent_and_good_svg_survives(self):
        logo = sanitize_brand_logo(GOOD_SVG)
        svg = base64.b64decode(logo.data_uri.split(",", 1)[1]).decode("utf-8")
        self.assertIn("<rect", svg)
        again = sanitize_brand_logo(svg)
        self.assertEqual(
            base64.b64decode(again.data_uri.split(",", 1)[1]).decode("utf-8"), svg
        )

    def test_svg_same_document_use_is_kept_but_loops_are_rejected(self):
        ok = (
            f'<svg {SVG_NS} viewBox="0 0 10 10"><defs><circle id="c" r="2" cx="3" cy="3"/></defs>'
            '<use href="#c"/></svg>'
        )
        svg = base64.b64decode(sanitize_brand_logo(ok).data_uri.split(",", 1)[1]).decode()
        self.assertIn("<use", svg)
        loop = (
            f'<svg {SVG_NS} viewBox="0 0 10 10"><g id="a"><circle r="2" cx="3" cy="3"/>'
            '<use href="#a"/></g></svg>'
        )
        with self.assertRaises(BrandAssetError):
            sanitize_brand_logo(loop)

    def test_svg_xml_attacks_rejected(self):
        xxe = (
            '<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
            f'<svg {SVG_NS} viewBox="0 0 10 10"><text>&xxe;</text><rect width="1" height="1"/></svg>'
        )
        laughs = (
            '<!DOCTYPE svg [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;">]>'
            f'<svg {SVG_NS} viewBox="0 0 10 10"><text>&b;</text><rect width="1" height="1"/></svg>'
        )
        only_script = f'<svg {SVG_NS} viewBox="0 0 10 10"><script>alert(1)</script></svg>'
        bidi = f'<svg {SVG_NS} viewBox="0 0 10 10"><text>a‮b</text><rect width="1" height="1"/></svg>'
        no_viewbox = f"<svg {SVG_NS}><rect width='1' height='1'/></svg>"
        not_svg = "<html><body>hi</body></html>"
        broken = f"<svg {SVG_NS} viewBox='0 0 10 10'><rect"
        for name, payload in {
            "xxe": xxe, "entity expansion": laughs, "nothing drawable": only_script,
            "bidi control": bidi, "no viewBox": no_viewbox, "not svg": not_svg,
            "malformed": broken,
        }.items():
            with self.subTest(name), self.assertRaises(BrandAssetError):
                sanitize_brand_logo(payload)

    def test_svg_obfuscated_urls_are_removed(self):
        svg_in = (
            f'<svg {SVG_NS} viewBox="0 0 10 10">'
            '<rect width="1" height="1" fill="  JaVaScRiPt:alert(1)"/>'
            '<rect width="1" height="1" fill="url(&#x68;ttps://evil.example/a)"/>'
            '<rect width="1" height="1" fill="URL(relative.svg#grad)"/>'
            '<rect width="1" height="1" fill="url (relative.svg#grad)"/>'
            '<rect width="1" height="1" stroke="data:text/html,x"/>'
            '<circle r="3" cx="3" cy="3" fill="#112233"/></svg>'
        )
        svg = base64.b64decode(sanitize_brand_logo(svg_in).data_uri.split(",", 1)[1]).decode()
        for needle in ("javascript", "evil.example", "relative.svg", "data:", "url(", "url ("):
            self.assertNotIn(needle, svg.lower())
        self.assertIn("<circle", svg)


# --------------------------------------------------------------------------------------
# Branding tokens, WCAG AA guardrail, entitlement
# --------------------------------------------------------------------------------------
class TestBrandingTokens(unittest.TestCase):
    def test_defaults_and_passing_primary_kept_as_is(self):
        default = resolve_document_branding(None)
        self.assertTrue(default.primary_color.startswith("#"))
        self.assertTrue(default.show_powered_by)
        kept = resolve_document_branding({"primary_color": "#0B5FA5"})
        self.assertEqual(kept.primary_color.lower(), "#0b5fa5")
        self.assertEqual(kept.adjustments, ())

    def test_failing_primary_is_auto_adjusted_to_meet_aa_on_every_print_surface(self):
        resolved = resolve_document_branding({"primary_color": "#F59E0B"})
        self.assertNotEqual(resolved.primary_color.lower(), "#f59e0b")
        self.assertTrue(resolved.adjustments)
        for surface in PRINT_SURFACES:
            self.assertGreaterEqual(contrast_ratio(resolved.primary_color, surface), 4.5)

    def test_unfixable_primary_is_rejected_with_reason(self):
        for colour in ("#FFFFFF", "#FFFF00", "#39FF14", "#FFE680"):
            with self.subTest(colour), self.assertRaises(BrandingError) as ctx:
                resolve_document_branding({"primary_color": colour})
            self.assertIn("contrast", str(ctx.exception).lower())

    def test_reject_policy_never_adjusts(self):
        with self.assertRaises(BrandingError) as ctx:
            resolve_document_branding({"primary_color": "#F59E0B", "contrast_policy": "reject"})
        self.assertRegex(str(ctx.exception), r"\d+\.\d+:1")
        with self.assertRaises(BrandingError):
            resolve_document_branding({"primary_color": "#0B5FA5", "contrast_policy": "bogus"})

    def test_accent_needs_3_to_1_and_is_adjusted_or_rejected(self):
        ok = resolve_document_branding({"primary_color": "#0B5FA5", "accent_color": "#B43200"})
        self.assertEqual(ok.accent_color.lower(), "#b43200")
        adjusted = resolve_document_branding({"primary_color": "#0B5FA5", "accent_color": "#FFD966"})
        for surface in PRINT_SURFACES:
            self.assertGreaterEqual(contrast_ratio(adjusted.accent_color, surface), 3.0)
        with self.assertRaises(BrandingError):
            resolve_document_branding({"primary_color": "#0B5FA5", "accent_color": "#FFFFFF"})

    def test_invalid_or_injected_colours_rejected(self):
        for bad in ("red", "#fff", "#12345g", "javascript:alert(1)", "#000000;}body{display:none",
                    "#0B5FA5\n", "url(https://evil.example)", "#0B5FA5}", 12345, ["#0B5FA5"]):
            with self.subTest(bad), self.assertRaises(BrandingError):
                resolve_document_branding({"primary_color": bad})
        with self.assertRaises(BrandingError):
            resolve_document_branding({"primary_color": "#0B5FA5", "accent_color": "red;}"})

    def test_display_name_rules(self):
        names = resolve_document_branding(TENANT_BRANDING)
        self.assertEqual(names.display_name_ar, "النخلة للتجارة")
        self.assertEqual(names.display_name_en, "Al Nakhla Trading")
        one = resolve_document_branding({"display_name": "Acme"})
        self.assertEqual((one.display_name_ar, one.display_name_en), ("Acme", "Acme"))
        for bad in ("x" * 41, "a‮b", "a\x00b", "a\nb", {"en": "x" * 41}, 7):
            with self.subTest(bad), self.assertRaises(BrandingError):
                resolve_document_branding({"display_name": bad})

    def test_forbidden_and_unknown_keys_are_rejected_fail_closed(self):
        for key in ("custom_css", "css", "style", "font_family", "font", "status_colors",
                    "danger_color", "hide_qr", "layout", "template_html", "direction",
                    "rtl", "unknown_thing"):
            with self.subTest(key), self.assertRaises(BrandingError):
                resolve_document_branding({"primary_color": "#0B5FA5", key: "x"})

    def test_powered_by_follows_entitlement_only(self):
        wants_removal = {"show_powered_by": False}
        self.assertTrue(resolve_document_branding(wants_removal).show_powered_by)
        self.assertTrue(resolve_document_branding(wants_removal, entitlements={}).show_powered_by)
        for not_true in ("yes", 1, "true", None, [True]):
            resolved = resolve_document_branding(
                wants_removal, entitlements={ENTITLEMENT_REMOVE_POWERED_BY: not_true}
            )
            self.assertTrue(resolved.show_powered_by, not_true)
        entitled = resolve_document_branding(
            wants_removal, entitlements={ENTITLEMENT_REMOVE_POWERED_BY: True}
        )
        self.assertFalse(entitled.show_powered_by)
        # Entitlement alone never hides the mark; the tenant must also ask.
        self.assertTrue(
            resolve_document_branding({}, entitlements={ENTITLEMENT_REMOVE_POWERED_BY: True})
            .show_powered_by
        )
        # Legacy key from InvoiceBranding mappings maps to the same rule.
        legacy = resolve_document_branding(
            {"remove_powered_by": True}, entitlements={ENTITLEMENT_REMOVE_POWERED_BY: True}
        )
        self.assertFalse(legacy.show_powered_by)
        with self.assertRaises(BrandingError):
            resolve_document_branding({"show_powered_by": True, "remove_powered_by": True})

    def test_dataclass_input_and_logo_validation(self):
        resolved = resolve_document_branding(
            DocumentBranding(display_name="Acme", primary_color="#0B5FA5", logo=GOOD_SVG)
        )
        self.assertEqual(resolved.logo.mime, "image/svg+xml")
        with self.assertRaises(BrandingError):
            resolve_document_branding({"logo": _uri(b"GIF89a....", "image/gif")})
        with self.assertRaises(BrandingError):
            resolve_document_branding(["not", "a", "mapping"])


# --------------------------------------------------------------------------------------
# Rendering: common guarantees for every template
# --------------------------------------------------------------------------------------
class TestAllTemplates(unittest.TestCase):
    def test_structure_bilingual_rtl_and_locked_layout_verify_clean(self):
        for kind in ALL_KINDS:
            with self.subTest(kind):
                doc = _render(kind, branding=TENANT_BRANDING)
                self.assertTrue(doc.startswith("<!DOCTYPE html>"))
                self.assertIn('<html lang="ar" dir="rtl">', doc)
                self.assertIn('<body dir="rtl">', doc)
                self.assertEqual(verify_locked_layout(doc, LAYOUT_KIND[kind]), [])
                assert_locked_layout(doc, LAYOUT_KIND[kind])
                self.assertIn("size: A4 portrait", doc)
                self.assertIn("النخلة للتجارة", doc)
                self.assertIn("Al Nakhla Trading", doc)

    def test_branding_flows_only_through_css_custom_properties(self):
        for kind in ALL_KINDS:
            with self.subTest(kind):
                doc = _render(kind, branding={"primary_color": "#0B5FA5", "accent_color": "#B43200"})
                style = _style_block(doc)
                self.assertIn("--brand-primary:#0b5fa5", style.lower())
                self.assertIn("--brand-accent:#b43200", style.lower())
                css = _css_outside_root(style)
                self.assertNotRegex(css, r"#[0-9a-fA-F]{3,8}\b")
                self.assertNotRegex(css, r"\b(rgb|hsl)a?\(")
                self.assertIn("var(--brand-primary)", css)
                # Tenant colour never appears outside the token block or element attributes.
                self.assertEqual(doc.lower().count("#0b5fa5"), 1)
                self.assertNotIn("style=", re.sub(r"<style>.*?</style>", "", doc, flags=re.S))

    def test_different_branding_changes_only_the_token_block(self):
        for kind in ALL_KINDS:
            with self.subTest(kind):
                a = _render(kind, branding={"primary_color": "#0B5FA5"})
                b = _render(kind, branding={"primary_color": "#7A1F5C"})
                token = re.compile(r":root\{--brand-primary:#[0-9a-f]{6};[^}]*\}")
                self.assertNotEqual(a, b)
                self.assertEqual(token.sub("", a), token.sub("", b))

    def test_locked_css_has_fixed_typography_status_tokens_and_logo_limits(self):
        css = LOCKED_DOCUMENT_CSS
        self.assertIn("'Readex Pro'", css)
        self.assertIn("print-color-adjust: exact", css)
        for token in ("--status-success", "--status-warning", "--status-danger"):
            self.assertIn(token, css)
        self.assertEqual(set(STATUS_TOKENS), {"success", "warning", "danger"})
        for hex_value in STATUS_TOKENS.values():
            self.assertGreaterEqual(contrast_ratio(hex_value, "#FFFFFF"), 4.5)
        self.assertRegex(css, r"\.brand-logo\s*\{[^}]*max-height:\s*16mm")
        self.assertRegex(css, r"\.brand-logo\s*\{[^}]*max-width:\s*60mm")
        self.assertRegex(css, r"\.qr-clear-zone\s*\{[^}]*padding:\s*4\.5mm")
        # Accent is graphics-only: never a text colour.
        for match in re.finditer(r"([a-z-]+)\s*:\s*[^;{}]*var\(--brand-accent\)", css):
            self.assertRegex(match.group(1), r"^(border|background|outline)")
        self.assertNotRegex(css, r"(?<![a-z-])color\s*:\s*var\(--brand-accent\)")

    def test_logo_svg_embedded_as_img_only_in_header_never_inline(self):
        for kind in ALL_KINDS:
            with self.subTest(kind):
                doc = _render(kind, branding={"primary_color": "#0B5FA5", "logo": EVIL_SVG})
                self.assertEqual(verify_locked_layout(doc, LAYOUT_KIND[kind]), [])
                imgs = [a for t, a in _tags(doc) if t == "img"]
                self.assertEqual(len(imgs), 1)
                self.assertTrue(imgs[0]["src"].startswith("data:image/svg+xml;base64,"))
                self.assertNotIn("evil.example", doc)
                self.assertNotIn("<script", doc.lower())
                header = doc.split('data-locked-region="header"', 1)[1].split(
                    'data-locked-region="', 1)[0]
                self.assertIn("brand-logo", header)
                expected_svgs = 1 if kind == "tax" else 0  # only the ZATCA QR is inline SVG
                self.assertEqual(doc.count("<svg"), expected_svgs)

    def test_png_logo_and_mono_flag(self):
        doc = _render("quote", branding={"logo": _uri(_png(), "image/png"), "mono_logo": True})
        self.assertIn("logo-mono", doc)
        self.assertIn("data:image/png;base64,", doc)
        with self.assertRaises(BrandingError):
            _render("quote", branding={"logo": _uri(b"GIF89a....", "image/gif")})

    def test_powered_by_footer_and_entitlement(self):
        for kind in ALL_KINDS:
            with self.subTest(kind):
                shown = _render(kind, branding={"show_powered_by": False})
                self.assertIn("powered-by", shown)  # no entitlement: mark stays
                self.assertEqual(verify_locked_layout(shown, LAYOUT_KIND[kind]), [])
                hidden = _render(
                    kind, branding={"show_powered_by": False},
                    entitlements={ENTITLEMENT_REMOVE_POWERED_BY: True},
                )
                self.assertNotIn("Powered by", hidden)
                self.assertNotIn("مدعوم من", hidden)
                self.assertEqual(verify_locked_layout(hidden, LAYOUT_KIND[kind]), [])
                self.assertIn('data-locked-region="footer"', hidden)

    def test_zero_engine_markers_in_output(self):
        for kind in ALL_KINDS:
            with self.subTest(kind):
                doc = _render(kind, branding=TENANT_BRANDING)
                body = doc.replace("<!DOCTYPE html>", "", 1).lower()
                for marker in ("frappe", "erpnext", "doctype", "tabsales", "/api/method",
                               "frappe-", "bench", "csrf_token"):
                    self.assertNotIn(marker, body, marker)

    def test_xss_in_every_text_field_is_escaped(self):
        payload = '"><script>alert(1)</script><img src=x onerror=alert(2)>'
        # display_name is limited to 40 characters, so it gets a shorter payload
        branding = {"display_name": '"><img src=x onerror=a()>'}
        for kind in ALL_KINDS:
            with self.subTest(kind):
                if kind == "tax":
                    data = _tax_invoice_data()
                    data["seller"]["name"] = payload
                    data["notes"] = payload
                    data["lines"][0]["description"] = payload
                    doc = render_branded_tax_invoice_html(data, mode="zatca_sa", branding=branding)
                elif kind == "neutral":
                    data = _neutral_invoice_data()
                    data["buyer"]["name"] = payload
                    data["lines"][0]["description_ar"] = payload
                    doc = render_branded_tax_invoice_html(data, mode="neutral", branding=branding)
                elif kind == "quote":
                    data = _quote_data()
                    data["reference"] = payload
                    data["terms"] = [payload]
                    data["notes"] = payload
                    data["buyer"]["name"] = payload
                    doc = render_branded_quote_html(data, branding=branding)
                else:
                    data = _po_data()
                    data["payment_terms"] = payload
                    data["delivery"]["name"] = payload
                    data["terms"] = payload
                    data["supplier"]["name_ar"] = payload
                    doc = render_branded_purchase_order_html(data, branding=branding)
                self.assertNotIn("<script", doc.lower())
                self.assertNotIn("<img src=x", doc.lower())
                for tag, attrs in _tags(doc):
                    self.assertFalse([a for a in attrs if a.startswith("on")], (tag, attrs))
                self.assertIn("&lt;script&gt;", doc)
                self.assertEqual(verify_locked_layout(doc, LAYOUT_KIND[kind]), [])

    def test_ltr_values_isolated_inside_rtl_page(self):
        for kind in ALL_KINDS:
            with self.subTest(kind):
                doc = _render(kind)
                self.assertGreater(doc.count('<bdi dir="ltr">'), 5)
                self.assertRegex(doc, r"bdi\s*\{[^}]*unicode-bidi:\s*isolate")

    def test_tenant_cannot_pass_layout_overrides_to_any_template(self):
        for kind in ALL_KINDS:
            for key in ("custom_css", "hide_qr", "layout"):
                with self.subTest(kind=kind, key=key), self.assertRaises(BrandingError):
                    _render(kind, branding={key: "display:none"})

    def test_new_arabic_copy_is_marked_unreviewed(self):
        self.assertTrue(UNREVIEWED_ARABIC_LABELS)
        self.assertIn("quote_title", UNREVIEWED_ARABIC_LABELS)
        self.assertIn("po_title", UNREVIEWED_ARABIC_LABELS)
        for key in UNREVIEWED_ARABIC_LABELS:
            self.assertNotIn(key, BILINGUAL_LABELS)  # reviewed ERP-007 labels are not re-marked


# --------------------------------------------------------------------------------------
# Tax invoice specifics
# --------------------------------------------------------------------------------------
class TestBrandedTaxInvoice(unittest.TestCase):
    def test_zatca_invoice_has_all_locked_regions_in_order_with_tlv_qr(self):
        doc = render_branded_tax_invoice_html(_tax_invoice_data(), mode="zatca_sa",
                                              branding=TENANT_BRANDING)
        self.assertEqual(
            _regions(doc), ["header", "seller", "buyer", "lines", "totals", "qr", "footer"]
        )
        for text in ("فاتورة ضريبية", "Tax Invoice", "الرقم الضريبي", "السجل التجاري",
                     "نسبة الضريبة", "فئة الضريبة", "الإجمالي الخاضع للضريبة",
                     "إجمالي ضريبة القيمة المضافة", "الإجمالي النهائي",
                     "رمز الاستجابة السريعة للفاتورة الإلكترونية"):
            self.assertIn(text, doc)
        self.assertIn('<bdi dir="ltr">300000000000003</bdi>', doc)
        self.assertIn('<bdi dir="ltr">1010123456</bdi>', doc)
        self.assertIn('<bdi dir="ltr">230.00 SAR</bdi>', doc)
        self.assertIn('class="qr-clear-zone"', doc)
        tlv = doc.split('data-zatca-tlv="', 1)[1].split('"', 1)[0]
        decoded = decode_phase1_tlv(tlv)
        self.assertEqual(decoded[2], "300000000000003")
        self.assertEqual(decoded[4], "230.00")
        self.assertEqual(decoded[5], "30.00")

    def test_branding_cannot_change_legal_content_of_invoice(self):
        plain = render_branded_tax_invoice_html(_tax_invoice_data(), mode="zatca_sa")
        branded = render_branded_tax_invoice_html(
            _tax_invoice_data(), mode="zatca_sa",
            branding={"primary_color": "#7A1F5C", "display_name": "Acme", "logo": GOOD_SVG},
        )
        def region(doc: str, name: str) -> str:
            part = doc.split(f'data-locked-region="{name}"', 1)[1]
            return re.split(r'data-locked-region="', part, maxsplit=1)[0]
        for name in ("seller", "buyer", "lines", "totals"):
            self.assertEqual(region(plain, name), region(branded, name), name)
        self.assertEqual(
            plain.split('data-zatca-tlv="', 1)[1].split('"', 1)[0],
            branded.split('data-zatca-tlv="', 1)[1].split('"', 1)[0],
        )

    def test_neutral_mode_has_no_qr_region_and_needs_no_compliance_module(self):
        doc = render_branded_tax_invoice_html(_neutral_invoice_data(), mode="neutral")
        self.assertEqual(_regions(doc), ["header", "seller", "buyer", "lines", "totals", "footer"])
        self.assertNotIn("data-zatca-tlv", doc)
        self.assertEqual(verify_locked_layout(doc, "tax_invoice_neutral"), [])

    def test_fails_closed_on_bad_input(self):
        data = _tax_invoice_data()
        data["totals"]["grand_total"] = "999.00"
        with self.assertRaises(ZatcaValidationError):
            render_branded_tax_invoice_html(data, mode="zatca_sa")
        neutral = _neutral_invoice_data()
        neutral["totals"]["grand_total"] = "1.00"
        with self.assertRaises(ValueError):
            render_branded_tax_invoice_html(neutral, mode="neutral")
        with self.assertRaises(ValueError):
            render_branded_tax_invoice_html(_tax_invoice_data(), mode="bogus")

    def test_credit_note_shows_adjustment_reference(self):
        data = _tax_invoice_data()
        data.update(transaction_type="credit_note", invoice_id="CN-1",
                    preceding_invoice_reference="INV-2026-0001", amendment_reason="Returned")
        doc = render_branded_tax_invoice_html(data, mode="zatca_sa")
        self.assertIn("إشعار دائن ضريبي", doc)
        self.assertIn('<bdi dir="ltr">INV-2026-0001</bdi>', doc)
        self.assertEqual(verify_locked_layout(doc, "tax_invoice_zatca_sa"), [])


# --------------------------------------------------------------------------------------
# Compliance lock: tamper attempts against rendered output must be detected
# --------------------------------------------------------------------------------------
class TestComplianceLockTamper(unittest.TestCase):
    KIND = "tax_invoice_zatca_sa"

    def setUp(self) -> None:
        self.doc = render_branded_tax_invoice_html(_tax_invoice_data(), mode="zatca_sa",
                                                   branding=TENANT_BRANDING)

    def assert_flagged(self, tampered: str, *, kind: str | None = None):
        self.assertNotEqual(tampered, self.doc)
        self.assertTrue(verify_locked_layout(tampered, kind or self.KIND))
        with self.assertRaises(LockedLayoutViolation):
            assert_locked_layout(tampered, kind or self.KIND)

    def test_untampered_is_clean(self):
        self.assertEqual(verify_locked_layout(self.doc, self.KIND), [])

    def test_extra_style_block_hiding_qr(self):
        self.assert_flagged(self.doc.replace(
            "</head>", "<style>[data-locked-region=qr]{display:none!important}</style></head>"))

    def test_appended_rule_in_existing_style(self):
        self.assert_flagged(self.doc.replace(
            "</style>", ".qr-clear-zone{padding:0}.brand-logo{position:absolute}</style>", 1))

    def test_tenant_token_block_cannot_carry_extra_declarations(self):
        self.assert_flagged(re.sub(r"(:root\{--brand-primary:#[0-9a-f]{6};)",
                                   r"\1--status-danger:#00ff00;display:none;", self.doc, count=1))
        self.assert_flagged(re.sub(r"--brand-primary:#[0-9a-f]{6}", "--brand-primary:red", self.doc, count=1))

    def test_removed_or_renamed_regions(self):
        for name in ("header", "seller", "buyer", "lines", "totals", "qr", "footer"):
            with self.subTest(name):
                self.assert_flagged(self.doc.replace(f'data-locked-region="{name}"', "data-x=\"1\""))

    def test_duplicate_region(self):
        self.assert_flagged(self.doc.replace('data-locked-region="footer"',
                                             'data-locked-region="totals"', 1))

    def test_reordered_regions(self):
        self.assert_flagged(
            self.doc.replace('data-locked-region="lines"', 'data-locked-region="@@"')
            .replace('data-locked-region="totals"', 'data-locked-region="lines"')
            .replace('data-locked-region="@@"', 'data-locked-region="totals"')
        )

    def test_direction_and_language_tampering(self):
        self.assert_flagged(self.doc.replace('<html lang="ar" dir="rtl">', '<html lang="en" dir="ltr">'))
        self.assert_flagged(self.doc.replace('<body dir="rtl">', '<body dir="ltr">'))
        self.assert_flagged(self.doc.replace('<html lang="ar" dir="rtl">', '<html>'))

    def test_inline_style_hidden_on_event_and_scripts(self):
        self.assert_flagged(self.doc.replace('data-locked-region="totals"',
                                             'data-locked-region="totals" style="display:none"'))
        self.assert_flagged(self.doc.replace('data-locked-region="qr"',
                                             'data-locked-region="qr" hidden'))
        self.assert_flagged(self.doc.replace('data-locked-region="qr"',
                                             'data-locked-region="qr" onclick="x()"'))
        self.assert_flagged(self.doc.replace("</body>", "<script>document.body.dir='ltr'</script></body>"))
        self.assert_flagged(self.doc.replace("</head>", '<link rel="stylesheet" href="x.css"></head>'))
        self.assert_flagged(self.doc.replace("</body>", '<iframe src="x"></iframe></body>'))

    def test_remote_resources_flagged(self):
        self.assert_flagged(self.doc.replace("</body>", '<img src="https://evil.example/t.png"></body>'))
        self.assert_flagged(self.doc.replace("<head>", '<head><base href="https://evil.example/">'))

    def test_missing_mandatory_arabic_labels_and_fields(self):
        self.assert_flagged(self.doc.replace("الرقم الضريبي", "VAT"))
        self.assert_flagged(self.doc.replace("الإجمالي النهائي", "Total"))
        self.assert_flagged(self.doc.replace("نسبة الضريبة", ""))

    def test_qr_without_payload_or_with_overlapping_logo(self):
        self.assert_flagged(re.sub(r'data-zatca-tlv="[^"]*"', 'data-zatca-tlv=""', self.doc))
        logo_in_qr = self.doc.replace(
            '<div class="qr-clear-zone">',
            '<div class="qr-clear-zone"><img class="brand-logo" src="data:image/png;base64,AAAA">', 1)
        self.assert_flagged(logo_in_qr)

    def test_logo_outside_header_flagged(self):
        logo = '<img class="brand-logo" src="data:image/png;base64,AAAA">'
        self.assert_flagged(self.doc.replace("</body>", logo + "</body>"))

    def test_wrong_kind_downgrade_does_not_hide_missing_qr(self):
        no_qr = self.doc.replace('data-locked-region="qr"', 'data-x="1"')
        self.assertTrue(verify_locked_layout(no_qr, "tax_invoice_zatca_sa"))
        # A neutral document is not a ZATCA one: claiming ZATCA mode must still need the QR,
        # and the document-kind marker in the page must match what the caller expects.
        neutral = render_branded_tax_invoice_html(_neutral_invoice_data(), mode="neutral")
        self.assertTrue(verify_locked_layout(neutral, "tax_invoice_zatca_sa"))

    def test_quote_and_po_locks_also_detect_tampering(self):
        quote = render_branded_quote_html(_quote_data())
        po = render_branded_purchase_order_html(_po_data())
        for doc, kind, regions in (
            (quote, "quote", ("header", "seller", "buyer", "lines", "totals", "terms", "footer")),
            (po, "purchase_order", ("header", "buyer", "supplier", "delivery", "lines", "totals",
                                    "terms", "footer")),
        ):
            self.assertEqual(verify_locked_layout(doc, kind), [])
            self.assertEqual(_regions(doc), list(regions))
            self.assertTrue(verify_locked_layout(doc.replace("</style>", "x{display:none}</style>", 1), kind))
            self.assertTrue(verify_locked_layout(doc.replace('dir="rtl"', 'dir="ltr"', 1), kind))
            self.assertTrue(verify_locked_layout(
                doc.replace('data-locked-region="totals"', 'data-x="1"'), kind))
        self.assertTrue(verify_locked_layout(quote, "purchase_order"))
        self.assertTrue(verify_locked_layout(po, "quote"))

    def test_pathologically_nested_markup_fails_closed(self):
        nested = self.doc.replace("</body>", "<div>" * 20000 + "</body>")
        self.assert_flagged(nested)

    def test_unknown_kind_raises(self):
        with self.assertRaises(ValueError):
            verify_locked_layout(self.doc, "receipt")


# --------------------------------------------------------------------------------------
# Quote
# --------------------------------------------------------------------------------------
class TestBrandedQuote(unittest.TestCase):
    def test_quote_content_bilingual(self):
        doc = render_branded_quote_html(_quote_data(), branding=TENANT_BRANDING)
        for text in ("عرض سعر", "Quotation", "رقم العرض", "Quote Number", "صالح حتى", "Valid Until",
                     "مرجع العميل", "Customer Reference", "الشروط والأحكام", "Terms &amp; Conditions",
                     "Prices valid for 30 days", "Payment within 30 days of invoice",
                     "كرسي مكتب", "Office Desk Chair", "الإجمالي النهائي", "Delivery included"):
            self.assertIn(text, doc)
        for ltr in ("QTN-2026-0007", "2026-12-17", "RFQ-5521", "230.00 SAR", "300000000000003"):
            self.assertIn(f'<bdi dir="ltr">{ltr}</bdi>', doc)
        self.assertNotIn("data-zatca-tlv", doc)
        self.assertNotIn("فاتورة ضريبية", doc)  # a quote is never presented as a tax invoice

    def test_status_pill_has_icon_and_label_with_fixed_colour(self):
        for status, token in (("pending", "warning"), ("accepted", "success"), ("expired", "danger")):
            data = _quote_data()
            data["status"] = status
            doc = render_branded_quote_html(data, branding={"primary_color": "#7A1F5C"})
            self.assertIn(f"status-{token}", doc)
            self.assertRegex(doc, rf'class="status-pill status-{token}"[^>]*>\s*<span class="status-icon"')
        data = _quote_data()
        data["status"] = "<script>"
        with self.assertRaises(ValueError):
            render_branded_quote_html(data)

    def test_status_and_terms_optional(self):
        data = _quote_data()
        del data["status"], data["terms"], data["reference"], data["notes"]
        doc = render_branded_quote_html(data)
        self.assertEqual(verify_locked_layout(doc, "quote"), [])
        self.assertIn('data-locked-region="terms"', doc)

    def test_validation_fails_closed(self):
        cases = {
            "missing valid_until": lambda d: d.pop("valid_until"),
            "valid_until before issue": lambda d: d.update(valid_until="2026-11-01"),
            "bad date": lambda d: d.update(valid_until="17/12/2026"),
            "totals mismatch": lambda d: d["totals"].update(grand_total="1.00"),
            "no lines": lambda d: d.update(lines=[]),
            "no seller name": lambda d: d["seller"].update(name=""),
            "negative qty": lambda d: d["lines"][0].update(quantity="-1"),
            "missing id": lambda d: d.pop("quote_id"),
        }
        for name, mutate in cases.items():
            data = _quote_data()
            mutate(data)
            with self.subTest(name), self.assertRaises(ValueError):
                render_branded_quote_html(data)


# --------------------------------------------------------------------------------------
# Purchase order
# --------------------------------------------------------------------------------------
class TestBrandedPurchaseOrder(unittest.TestCase):
    def test_po_content_bilingual(self):
        doc = render_branded_purchase_order_html(_po_data(), branding=TENANT_BRANDING)
        for text in ("أمر شراء", "Purchase Order", "رقم أمر الشراء", "PO Number",
                     "المورّد", "Supplier", "المشتري", "Buyer", "عنوان التسليم", "Delivery Address",
                     "تاريخ التسليم المطلوب", "Required Delivery Date", "شروط الدفع", "Payment Terms",
                     "الشروط والأحكام", "Main Warehouse", "المستودع الرئيسي", "Net 30",
                     "Gulf Supplies LLC", "شركة الخليج للتوريدات", "ألواح فولاذ 2 مم",
                     "Goods must be delivered"):
            self.assertIn(text, doc)
        for ltr in ("PO-2026-0042", "2026-12-01", "575.00 SAR", "310122393500003"):
            self.assertIn(f'<bdi dir="ltr">{ltr}</bdi>', doc)
        self.assertNotIn("data-zatca-tlv", doc)

    def test_validation_fails_closed(self):
        cases = {
            "missing po id": lambda d: d.pop("po_id"),
            "missing supplier": lambda d: d.pop("supplier"),
            "missing buyer": lambda d: d.pop("buyer"),
            "required_by before issue": lambda d: d.update(required_by="2026-11-01"),
            "bad required_by": lambda d: d.update(required_by="soon"),
            "totals mismatch": lambda d: d["totals"].update(total_vat_amount="1.00"),
            "unrounded total": lambda d: d["totals"].update(
                total_taxable_amount="500.001", grand_total="575.001"),
            "empty lines": lambda d: d.update(lines=[]),
        }
        for name, mutate in cases.items():
            data = _po_data()
            mutate(data)
            with self.subTest(name), self.assertRaises(ValueError):
                render_branded_purchase_order_html(data)

    def test_delivery_optional_falls_back_but_region_stays(self):
        data = _po_data()
        del data["delivery"]
        doc = render_branded_purchase_order_html(data)
        self.assertIn('data-locked-region="delivery"', doc)
        self.assertEqual(verify_locked_layout(doc, "purchase_order"), [])


# --------------------------------------------------------------------------------------
# Review fixes: tokens only, line reconciliation, footer wording, unreviewed Arabic
# --------------------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[5]
_TOKENS_JSON = _REPO_ROOT / "docs" / "brand" / "tokens" / "tokens.json"
_PRINT_FORMATS = Path(__file__).resolve().parents[1] / "print_formats"

# Each print variable and the light-theme token it must equal. Print-only neutrals that are not
# brand tokens map to the closest existing token (ERP-016 review fix, ADR-0014).
_ROLE_TO_TOKEN = {
    "--doc-surface": "surface",
    "--doc-panel": "background",
    "--doc-panel-subtle": "surface",
    "--doc-text": "text",
    "--doc-text-secondary": "text",
    "--doc-text-muted": "text",
    "--doc-border": "background",
    "--doc-border-soft": "background",
    "--status-success": "success",
    "--status-warning": "warning",
    "--status-danger": "danger",
}


def _light_tokens() -> dict:
    return json.loads(_TOKENS_JSON.read_text(encoding="utf-8"))


def _locked_root_vars(css: str) -> dict[str, str]:
    block = re.search(r":root\s*\{([^}]*)\}", css).group(1)
    return {k.strip(): v.strip() for k, v in re.findall(r"(--[a-z-]+)\s*:\s*([^;]+);", block)}


class TestLayoutReadsTokenSource(unittest.TestCase):
    def test_rendered_css_values_equal_tokens_json(self):
        tokens = _light_tokens()
        light = tokens["color"]["light"]
        for kind in ALL_KINDS:
            with self.subTest(kind):
                # The locked block is the second :root in the document (first is the tenant one).
                style = _style_block(_render(kind))
                root_vars = _locked_root_vars(_css_without_first_root(style))
                for var, token in _ROLE_TO_TOKEN.items():
                    self.assertEqual(root_vars[var].lower(), light[token]["hex"].lower(), var)
        body = tokens["typography"]["families"]["body"]
        font = _locked_root_vars(LOCKED_DOCUMENT_CSS)["--font-doc"]
        self.assertEqual(font, f"'{body['family']}', {body['fallback']}")

    def test_layout_constants_follow_tokens_json(self):
        from change_engine.print_formats import document_layout

        light = _light_tokens()["color"]["light"]
        self.assertEqual(document_layout.DEFAULT_PRIMARY.lower(), light["primary"]["hex"].lower())
        self.assertEqual(
            tuple(h.lower() for h in PRINT_SURFACES),
            tuple(light[t]["hex"].lower() for t in ("surface", "background", "surface")),
        )
        self.assertEqual(
            {k: v.lower() for k, v in STATUS_TOKENS.items()},
            {k: light[k]["hex"].lower() for k in ("success", "warning", "danger")},
        )

    def test_no_colour_or_font_literals_outside_the_token_loader(self):
        modules = ("document_layout.py", "branded_documents.py", "brand_tokens.py",
                   "brand_assets.py", "document_labels.py")
        font_names = ("Readex", "Alexandria", "DejaVu", "Noto", "Arial", "Helvetica", "Tahoma")
        for name in modules:
            with self.subTest(name):
                src = (_PRINT_FORMATS / name).read_text(encoding="utf-8")
                self.assertNotRegex(src, r"#[0-9a-fA-F]{3,8}\b", name)
                self.assertNotRegex(src, r"\b(rgb|hsl)a?\(", name)
                self.assertNotRegex(src, r"font-family\s*:[ \t]*(?![ \t]|var\()", name)  # var(--font-doc) only
                for font in font_names:
                    self.assertNotIn(font, src, name)

    def test_loader_fails_closed(self):
        from change_engine.print_formats.document_tokens import (
            DocumentTokenError,
            load_document_tokens,
        )

        good = _light_tokens()

        def written(tmp, data) -> Path:
            path = Path(tmp) / "tokens.json"
            path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
            return path

        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_document_tokens(written(tmp, good)).primary.lower(),
                             good["color"]["light"]["primary"]["hex"].lower())
            with self.assertRaises(DocumentTokenError):
                load_document_tokens(Path(tmp) / "missing.json")
            with self.assertRaises(DocumentTokenError):
                load_document_tokens(written(tmp, "{not json"))
            for mutate in (
                lambda d: d["color"]["light"].pop("text"),
                lambda d: d["color"]["light"]["surface"].update(hex="white"),
                lambda d: d["color"]["light"]["danger"].update(hex="#C21F3A; x"),
                lambda d: d["typography"]["families"]["body"].pop("family"),
                lambda d: d["typography"]["families"]["body"].update(family="x}"),
                lambda d: d["typography"]["families"]["body"].update(fallback="a;b"),
                lambda d: d["typography"]["families"]["body"].update(fallback=","),
                lambda d: d["typography"]["families"]["body"].update(fallback=""),
                lambda d: d["typography"]["families"]["body"].update(fallback=" "),
                lambda d: d["typography"]["families"]["body"].update(fallback="system-ui,"),
                lambda d: d["typography"]["families"]["body"].update(fallback=",sans-serif"),
                lambda d: d["typography"]["families"]["body"].update(fallback="a,,b"),
                lambda d: d["typography"]["families"]["body"].update(fallback="a, 9bad"),
                lambda d: d["typography"]["families"]["body"].update(fallback="a b,\n"),
                lambda d: d["typography"]["families"]["body"].update(fallback=None),
                lambda d: d["typography"]["families"]["body"].update(family=" "),
                lambda d: d["typography"]["families"]["body"].update(family="-"),
                lambda d: d["typography"]["families"]["body"].update(family=""),
                lambda d: d.pop("typography"),
            ):
                broken = json.loads(json.dumps(good))
                mutate(broken)
                with self.subTest(mutate=mutate), self.assertRaises(DocumentTokenError):
                    load_document_tokens(written(tmp, broken))

    def test_font_names_are_normalised_and_safe(self):
        from change_engine.print_formats.document_tokens import load_document_tokens

        good = _light_tokens()
        good["typography"]["families"]["body"].update(
            family="Readex Pro", fallback="system-ui,  Helvetica Neue ,sans-serif")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tokens.json"
            path.write_text(json.dumps(good), encoding="utf-8")
            stack = load_document_tokens(path).font_stack
        self.assertEqual(stack, "'Readex Pro', system-ui, Helvetica Neue, sans-serif")

    def test_missing_token_file_fails_render_closed_not_import(self):
        # Importing the package must keep working without the token file (the engine app is
        # mounted without docs/ in the dev bench); the first branded render must refuse.
        from change_engine.print_formats import document_tokens
        from change_engine.print_formats.document_tokens import DocumentTokenError

        with mock.patch.object(document_tokens, "_candidate_paths", return_value=[]):
            document_tokens.document_tokens.cache_clear()
            try:
                with self.assertRaises(DocumentTokenError):
                    document_tokens.document_tokens()
            finally:
                document_tokens.document_tokens.cache_clear()


def _css_without_first_root(css: str) -> str:
    return re.sub(r":root\s*\{[^}]*\}", "", css, count=1)


# --------------------------------------------------------------------------------------
# Line amounts reconcile to totals (ADR-0031, rule 6): compare, never recompute
# --------------------------------------------------------------------------------------
class TestLineReconciliation(unittest.TestCase):
    def _quote(self, **line):
        data = _quote_data()
        data["lines"][0].update(line)
        return data

    def test_matching_document_with_supplied_line_total_renders(self):
        for builder, render in (
            (lambda: self._quote(line_total="200.00"), render_branded_quote_html),
            (lambda: _po_with(line_total="500.00"), render_branded_purchase_order_html),
        ):
            with self.subTest(render.__name__):
                self.assertIn("200.00" if "quote" in render.__name__ else "500.00",
                              render(builder()))

    def test_mismatched_line_total_is_refused_not_corrected(self):
        with self.assertRaisesRegex(ValueError, r"Line 1.*line_total 210\.00.*200\.00"):
            render_branded_quote_html(self._quote(line_total="210.00"))
        with self.assertRaisesRegex(ValueError, r"Line 1.*line_total"):
            render_branded_purchase_order_html(_po_with(line_total="499.99"))

    def test_discount_is_part_of_the_line_check(self):
        data = self._quote(discount="10.00", line_total="190.00")
        data["totals"] = {"total_taxable_amount": "190.00", "total_vat_amount": "28.50",
                          "grand_total": "218.50"}
        self.assertIn("190.00", render_branded_quote_html(data))
        data["lines"][0]["line_total"] = "200.00"  # ignores the discount
        with self.assertRaisesRegex(ValueError, r"Line 1.*line_total"):
            render_branded_quote_html(data)

    def test_computed_amount_uses_commercial_rounding_per_adr_0033(self):
        # 3 x 33.335 = 100.005 -> 100.01 (half away from zero), not 100.00 (half-even)
        data = self._quote(quantity="3", unit_price="33.335", line_total="100.01")
        data["totals"] = {"total_taxable_amount": "100.01", "total_vat_amount": "15.00",
                          "grand_total": "115.01"}
        self.assertIn("100.01", render_branded_quote_html(data))
        data["lines"][0]["line_total"] = "100.00"  # the half-even answer is refused
        with self.assertRaisesRegex(ValueError, r"Line 1.*line_total 100\.00.*100\.01"):
            render_branded_quote_html(data)
        # no supplied amount: the printed amount is the commercially rounded one
        del data["lines"][0]["line_total"]
        doc = render_branded_quote_html(data)
        self.assertIn('<bdi dir="ltr">100.01</bdi>', doc)
        self.assertNotIn('<bdi dir="ltr">100.00</bdi>', doc)

    def test_invoice_refuses_a_computed_amount_it_would_print_half_even(self):
        # ERP-007 prints an unsupplied amount half-even; never let that differ from the check.
        data = _neutral_invoice_data()
        data["lines"][0].update(quantity="0.5", unit_price="200.01")  # 100.005
        data["totals"] = {"total_taxable_amount": "100.01", "total_vat_amount": "0.00",
                          "grand_total": "100.01"}
        with self.assertRaisesRegex(ValueError, r"Line 1.*rounding.*line_net_amount"):
            render_branded_tax_invoice_html(data, mode="neutral")
        data["lines"][0]["line_net_amount"] = "100.01"  # the engine's amount is printed as given
        self.assertIn("100.01", render_branded_tax_invoice_html(data, mode="neutral"))

    def test_sum_of_lines_must_equal_total_taxable_amount(self):
        data = _quote_data()  # lines sum to 200.00; totals say 300.00 / 45.00 / 345.00
        data["totals"] = {"total_taxable_amount": "300.00", "total_vat_amount": "45.00",
                          "grand_total": "345.00"}
        with self.assertRaisesRegex(ValueError, r"Lines total 200\.00.*total_taxable_amount 300\.00"):
            render_branded_quote_html(data)
        po = _po_data()
        po["lines"].append({"description": "Bolt", "quantity": "10", "unit_price": "1.00",
                            "vat_rate": "0.15"})  # 500 + 10 = 510 but totals say 500
        with self.assertRaisesRegex(ValueError, r"Lines total 510\.00"):
            render_branded_purchase_order_html(po)

    def test_multiple_lines_sum_matches(self):
        po = _po_data()
        po["lines"].append({"description": "Bolt", "quantity": "10", "unit_price": "1.00",
                            "vat_rate": "0.15", "line_total": "10.00"})
        po["totals"] = {"total_taxable_amount": "510.00", "total_vat_amount": "76.50",
                        "grand_total": "586.50"}
        self.assertIn("586.50", render_branded_purchase_order_html(po))

    def test_tax_invoice_lines_are_reconciled_in_both_modes(self):
        neutral = _neutral_invoice_data()
        neutral["lines"][0]["line_total"] = "151.00"
        with self.assertRaisesRegex(ValueError, r"Line 1.*line_total 151\.00.*150\.00"):
            render_branded_tax_invoice_html(neutral, mode="neutral")
        neutral["lines"][0]["line_total"] = "150.00"
        self.assertIn("150.00", render_branded_tax_invoice_html(neutral, mode="neutral"))
        neutral = _neutral_invoice_data()
        neutral["totals"] = {"total_taxable_amount": "160.00", "total_vat_amount": "0.00",
                             "grand_total": "160.00"}
        with self.assertRaisesRegex(ValueError, r"Lines total 150\.00.*total_taxable_amount 160\.00"):
            render_branded_tax_invoice_html(neutral, mode="neutral")
        zatca = _tax_invoice_data()
        zatca["lines"][0]["line_total"] = "201.00"
        with self.assertRaisesRegex(ValueError, r"Line 1.*line_total 201\.00"):
            render_branded_tax_invoice_html(zatca, mode="zatca_sa")


# --------------------------------------------------------------------------------------
# Round 2 (review of d29cc56): input shape, document discounts, negative discounts,
# currency precision, unit price display. Compare and refuse; never recompute what is printed.
# --------------------------------------------------------------------------------------
_KINDS = {
    "tax": (_tax_invoice_data,
            lambda d: render_branded_tax_invoice_html(d, mode="zatca_sa")),
    "neutral": (_neutral_invoice_data,
                lambda d: render_branded_tax_invoice_html(d, mode="neutral")),
    "quote": (_quote_data, render_branded_quote_html),
    "po": (_po_data, render_branded_purchase_order_html),
}
_INVOICE_KINDS = ("tax", "neutral")


def _build(kind, *, qty="2", price="100.00", line=None, totals=None, **top):
    """A document of ``kind`` whose first line is ``qty x price`` (default 200.00 gross)."""
    data = _KINDS[kind][0]()
    data["lines"][0].update({"quantity": qty, "unit_price": price, "discount": "0.00",
                             **(line or {})})
    data["totals"] = dict(totals) if totals else {
        "total_taxable_amount": "200.00", "total_vat_amount": "30.00", "grand_total": "230.00"}
    data.update(top)
    return data


def _go(kind, data):
    return _KINDS[kind][1](data)


class TestLineInputShape(unittest.TestCase):
    def test_tuple_lines_are_checked_not_skipped_in_every_document(self):
        for kind in _KINDS:
            with self.subTest(kind, case="mismatch"):
                data = _build(kind)
                data["lines"] = tuple([{**data["lines"][0], "line_total": "999.99"}])
                with self.assertRaisesRegex(ValueError, r"Line 1.*line_total 999\.99"):
                    _go(kind, data)
            with self.subTest(kind, case="sum"):
                data = _build(kind, totals={"total_taxable_amount": "300.00",
                                            "total_vat_amount": "45.00", "grand_total": "345.00"})
                data["lines"] = tuple(data["lines"])
                with self.assertRaisesRegex(ValueError, r"Lines total 200\.00"):
                    _go(kind, data)
            with self.subTest(kind, case="valid tuple renders like the list"):
                as_list = _build(kind)
                as_tuple = _build(kind)
                as_tuple["lines"] = tuple(as_tuple["lines"])
                self.assertEqual(_go(kind, as_list), _go(kind, as_tuple))

    def test_non_sequence_lines_are_refused(self):
        for kind in _KINDS:
            for bad in ((x for x in [{}]), {"a": 1}, "abc", {1}, 5, b"x"):
                with self.subTest(kind, type=type(bad).__name__):
                    data = _build(kind)
                    data["lines"] = bad
                    with self.assertRaises(ValueError):
                        _go(kind, data)

    def test_a_non_mapping_line_in_a_tuple_is_refused(self):
        for kind in _KINDS:
            with self.subTest(kind):
                data = _build(kind)
                data["lines"] = ("not a mapping",)
                with self.assertRaises(ValueError):
                    _go(kind, data)

    def test_the_caller_input_is_not_mutated_by_normalising(self):
        data = _build("quote")
        data["lines"] = tuple(data["lines"])
        render_branded_quote_html(data)
        self.assertIsInstance(data["lines"], tuple)


_DISCOUNT_TOTALS = {"total_taxable_amount": "180.00", "total_vat_amount": "27.00",
                    "grand_total": "207.00"}


def _printed_lines(doc: str) -> list[dict]:
    """Quantity, unit price, discount and amount of each line, parsed from the printed HTML."""
    table = re.search(r'<table class="lines-table".*?</table>', doc, re.S).group(0)
    rows = []
    for row in re.findall(r"<tr>(.*?)</tr>", table.split("</thead>", 1)[1], re.S):
        cells = re.findall(r'<td class="num-col"><bdi dir="ltr">(.*?)</bdi></td>', row)
        # num-col cells in every document: no, quantity, unit price, discount, vat rate, amount
        rows.append({"qty": Decimal(cells[1]), "price": Decimal(cells[2].replace(",", "")),
                     "discount": Decimal(cells[3].replace(",", "")),
                     "amount": Decimal(cells[5].replace(",", ""))})
    return rows


def _printed_totals(doc: str) -> dict[str, Decimal]:
    """The English label -> amount of each totals row, parsed from the printed HTML."""
    table = re.search(r'<table class="totals-table">.*?</table>', doc, re.S).group(0)
    out = {}
    for amount, label in re.findall(
            r'<td class="tot-val"><bdi dir="ltr">([-0-9.,]+) [A-Z]{3}</bdi></td>'
            r'<th class="tot-en">(.*?)</th>', table):
        out[label] = Decimal(amount.replace(",", ""))
    return out


def _assert_printed_numbers_add_up(test, doc: str, *, taxable: str, discount_row: str | None):
    """Sum the PRINTED numbers: lines - discount row = taxable, taxable + VAT = grand total."""
    lines, totals = _printed_lines(doc), _printed_totals(doc)
    for line in lines:  # each printed line adds up on its own too
        test.assertEqual(line["qty"] * line["price"] - line["discount"], line["amount"])
    shown = totals.get("Discount")
    test.assertEqual(None if shown is None else f"{shown:.2f}", discount_row)
    test.assertEqual(sum(line["amount"] for line in lines) - (shown or Decimal(0)),
                     totals["Total Taxable Amount"])
    test.assertEqual(f"{totals['Total Taxable Amount']:.2f}", taxable)
    test.assertEqual(totals["Total Taxable Amount"] + totals["Total VAT"], totals["Grand Total"])


class TestDocumentDiscountPrinting(unittest.TestCase):
    """Round 4: a document discount is printed end to end and the printed numbers add up.

    The engine's document discount is ``discount_amount`` (top level or in totals; both must
    agree). Its per-line spread is ``distributed_discount_amount``, which comes with the engine's
    net line amount. The line amount column prints that engine amount (gross less the line
    discount less the allocation; the line's Discount column shows both), and the totals' Discount
    row prints exactly the part of the document discount the lines do not already carry.
    Everything is compared and refused on a mismatch, never recomputed.
    """

    def _doc(self, kind, *, doc_discount="20.00", where="totals", alloc=None, net=None,
             totals=None):
        line = {}
        if alloc is not None:
            line["distributed_discount_amount"] = alloc
        if net is not None:
            line["line_net_amount"] = net
        data = _build(kind, line=line, totals=totals or _DISCOUNT_TOTALS)
        if doc_discount is not None:
            # Round 5: the engine refuses a discount without apply_discount_on; these cases are
            # the Net Total kind (the discount comes off the net, the VAT follows it).
            data["totals"]["apply_discount_on"] = "Net Total"
            if where in ("totals", "both"):
                data["totals"]["discount_amount"] = doc_discount
            if where in ("top", "both"):
                data["discount_amount"] = doc_discount
        return data

    def test_unallocated_discount_prints_a_discount_row_that_adds_up(self):
        for kind in _KINDS:
            for where in ("totals", "top", "both"):
                with self.subTest(kind=kind, where=where):
                    doc = _go(kind, self._doc(kind, where=where, net="200.00"))
                    _assert_printed_numbers_add_up(self, doc, taxable="180.00",
                                                   discount_row="20.00")
                    self.assertEqual([line["amount"] for line in _printed_lines(doc)],
                                     [Decimal("200.00")])

    def test_unallocated_discount_without_a_supplied_line_amount(self):
        for kind in ("quote", "po", "neutral"):  # tax mode prints a computed amount half-even
            with self.subTest(kind):
                _assert_printed_numbers_add_up(self, _go(kind, self._doc(kind)),
                                               taxable="180.00", discount_row="20.00")

    def test_fully_allocated_discount_is_in_the_lines_and_prints_no_remainder_row(self):
        for kind in _KINDS:
            with self.subTest(kind):
                doc = _go(kind, self._doc(kind, alloc="20.00", net="180.00"))
                _assert_printed_numbers_add_up(self, doc, taxable="180.00", discount_row=None)
                line = _printed_lines(doc)[0]
                self.assertEqual((line["discount"], line["amount"]),
                                 (Decimal("20.00"), Decimal("180.00")))

    def test_partly_allocated_discount_prints_only_the_remainder(self):
        for kind in _KINDS:
            for where in ("totals", "top"):
                with self.subTest(kind=kind, where=where):
                    doc = _go(kind, self._doc(kind, where=where, alloc="12.00", net="188.00"))
                    _assert_printed_numbers_add_up(self, doc, taxable="180.00",
                                                   discount_row="8.00")
                    line = _printed_lines(doc)[0]
                    self.assertEqual((line["discount"], line["amount"]),
                                     (Decimal("12.00"), Decimal("188.00")))

    def test_line_discount_and_allocation_and_remainder_all_reconcile(self):
        # 200.00 gross - 10.00 line discount - 12.00 allocated = 178.00; 8.00 left = 170.00.
        totals = {"total_taxable_amount": "170.00", "total_vat_amount": "25.50",
                  "grand_total": "195.50"}
        for kind in _KINDS:
            with self.subTest(kind):
                data = self._doc(kind, alloc="12.00", net="178.00", totals=totals)
                data["lines"][0]["discount"] = "10.00"
                doc = _go(kind, data)
                _assert_printed_numbers_add_up(self, doc, taxable="170.00", discount_row="8.00")
                self.assertEqual(_printed_lines(doc)[0]["discount"], Decimal("22.00"))

    def test_two_lines_share_one_document_discount(self):
        totals = {"total_taxable_amount": "270.00", "total_vat_amount": "40.50",
                  "grand_total": "310.50"}
        for kind in _KINDS:
            with self.subTest(kind):
                data = self._doc(kind, doc_discount="30.00", alloc="20.00", net="180.00",
                                 totals=totals)
                data["lines"].append({**data["lines"][0], "item_code": "ITEM-002",
                                      "distributed_discount_amount": "10.00",
                                      "line_net_amount": "90.00", "quantity": "1",
                                      "unit_price": "100.00"})
                doc = _go(kind, data)
                _assert_printed_numbers_add_up(self, doc, taxable="270.00", discount_row=None)

    def test_wrong_allocations_and_discounts_are_refused_never_corrected(self):
        cases = {
            "net does not carry the allocation": (
                dict(alloc="12.00", net="200.00"), r"Line 1: line_net_amount 200\.00 != .*188\.00"),
            "net carries more than the allocation": (
                dict(alloc="12.00", net="180.00"), r"Line 1: line_net_amount 180\.00 != .*188\.00"),
            "allocation without the engine's net amount": (
                dict(alloc="12.00"), r"Line 1: distributed_discount_amount 12\.00 needs"),
            "allocation larger than the document discount": (
                dict(alloc="25.00", net="175.00"), r"carry 25\.00 of the document discount"),
            "allocation without a document discount": (
                dict(doc_discount=None, alloc="12.00", net="188.00"),
                r"carry 12\.00 of the document discount"),
            "document discount does not reach the taxable total": (
                dict(doc_discount="15.00", net="200.00"), r"Lines total 200\.00 less.*15\.00"),
            "document discount larger than the lines": (
                dict(doc_discount="250.00", net="200.00"), r"Lines total 200\.00 less.*250\.00"),
            "negative document discount": (
                dict(doc_discount="-20.00", net="200.00"), r"discount_amount -20\.00 cannot be neg"),
            "negative allocation": (
                dict(alloc="-12.00", net="212.00"), r"distributed_discount_amount -12\.00 cannot"),
            "document discount beyond the currency precision": (
                dict(doc_discount="20.001", net="200.00"), r"more than 2 decimals"),
            "boolean document discount": (
                dict(doc_discount=True, net="200.00"), r"discount_amount must be Decimal"),
            "unparsable document discount": (
                dict(doc_discount="ten", net="200.00"), r"discount_amount 'ten' is not a valid"),
        }
        for kind in _KINDS:
            for name, (params, reason) in cases.items():
                with self.subTest(kind=kind, case=name):
                    with self.assertRaisesRegex(ValueError, reason):
                        _go(kind, self._doc(kind, **params))

    def test_top_level_and_totals_discount_must_agree(self):
        for kind in _KINDS:
            with self.subTest(kind):
                data = self._doc(kind, net="200.00")
                data["discount_amount"] = "19.00"
                with self.assertRaisesRegex(ValueError, r"discount_amount.*(disagree|differ)"):
                    _go(kind, data)
                data["discount_amount"] = "20.0"  # the same number written differently
                self.assertIn("180.00", _go(kind, data))

    def test_other_discount_names_are_refused_not_guessed(self):
        cases = {
            "additional_discount_amount": lambda d: d["totals"].update(
                additional_discount_amount="20.00"),
            "allocated_discount_amount": lambda d: d["lines"][0].update(
                allocated_discount_amount="12.00"),
            "discount_allocation": lambda d: d["lines"][0].update(discount_allocation="12.00"),
        }
        for kind in _KINDS:
            for name, mutate in cases.items():
                with self.subTest(kind=kind, case=name):
                    data = self._doc(kind, net="200.00")
                    mutate(data)
                    with self.assertRaisesRegex(ValueError, rf"{name}.*discount_amount"):
                        _go(kind, data)

    def test_a_zero_or_empty_discount_is_not_a_discount(self):
        for kind in _KINDS:
            for value in (None, "", "0", "0.00", 0):
                with self.subTest(kind=kind, value=value):
                    data = _build(kind)
                    data["totals"]["discount_amount"] = value
                    data["lines"][0]["distributed_discount_amount"] = value
                    doc = _go(kind, data)
                    self.assertIn("230.00", doc)
                    self.assertNotIn("Discount</th>", doc.split('class="totals-table"', 1)[1])

    def test_no_discount_row_without_a_document_discount(self):
        for kind in _KINDS:
            with self.subTest(kind):
                totals = _printed_totals(_go(kind, _build(kind)))
                self.assertNotIn("Discount", totals)

    def test_the_ten_percent_discount_document_agrees_in_every_document(self):
        printed = {}
        for kind in _KINDS:
            doc = _go(kind, self._doc(kind, net="200.00"))
            totals = _printed_totals(doc)
            printed[kind] = (totals["Total Taxable Amount"], totals["Total VAT"],
                             totals["Grand Total"])
        self.assertEqual(set(printed.values()),
                         {(Decimal("180.00"), Decimal("27.00"), Decimal("207.00"))})

    def test_the_discount_row_label_is_bilingual_and_reuses_the_reviewed_discount_label(self):
        from change_engine.print_formats import BILINGUAL_LABELS

        ar, en = BILINGUAL_LABELS["discount"]
        for kind in _KINDS:
            with self.subTest(kind):
                totals = _go(kind, self._doc(kind, net="200.00")).split(
                    'class="totals-table"', 1)[1]
                self.assertIn(f'<th class="tot-ar">{ar}</th>', totals)
                self.assertIn(f'<th class="tot-en">{en}</th>', totals)

    def test_the_caller_amounts_are_never_replaced_to_make_a_document_pass(self):
        for kind in _KINDS:
            with self.subTest(kind):
                data = self._doc(kind, alloc="12.00", net="188.00")
                snapshot = json.dumps(data, sort_keys=True)
                _go(kind, data)
                self.assertEqual(json.dumps(data, sort_keys=True), snapshot)


class TestLineDiscountsStillReconcile(unittest.TestCase):
    """Line discounts (``qty x price - discount``) reconcile in every document."""

    def test_line_discounts_still_reconcile_in_every_document(self):
        totals = {"total_taxable_amount": "190.00", "total_vat_amount": "28.50",
                  "grand_total": "218.50"}
        for kind in _KINDS:
            with self.subTest(kind, case="matching"):
                doc = _go(kind, _build(kind, line={"discount": "10.00", "line_net_amount": "190.00"},
                                       totals=totals))
                self.assertIn("190.00", doc)
                self.assertIn('<bdi dir="ltr">10.00</bdi>', doc)  # the line discount column
            with self.subTest(kind, case="ignores the discount"):
                with self.assertRaisesRegex(ValueError, r"Line 1.*line_net_amount 200\.00"):
                    _go(kind, _build(kind, line={"discount": "10.00", "line_net_amount": "200.00"},
                                     totals=totals))

    def test_both_amount_fields_must_agree_when_both_are_supplied(self):
        for kind in _KINDS:
            with self.subTest(kind):
                with self.assertRaisesRegex(ValueError, r"line_total.*line_net_amount"):
                    _go(kind, _build(kind, line={"line_total": "200.00",
                                                 "line_net_amount": "199.00"}))


class TestNegativeDiscountsRefused(unittest.TestCase):
    def test_negative_discounts_are_refused_in_every_document_type(self):
        cases = {
            "line discount": lambda d: d["lines"][0].update(discount="-5.00"),
        }
        for kind in _KINDS:
            for name, mutate in cases.items():
                with self.subTest(kind=kind, case=name):
                    data = _build(kind, totals={"total_taxable_amount": "205.00",
                                                "total_vat_amount": "30.75",
                                                "grand_total": "235.75"})
                    mutate(data)
                    with self.assertRaisesRegex(ValueError, r"discount.*negative|negative.*discount"):
                        _go(kind, data)

    def test_a_discount_larger_than_the_line_is_refused(self):
        for kind in _KINDS:
            with self.subTest(kind):
                data = _build(kind, line={"discount": "200.01"},
                              totals={"total_taxable_amount": "0.00", "total_vat_amount": "0.00",
                                      "grand_total": "0.00"})
                with self.assertRaisesRegex(ValueError, r"Line 1"):
                    _go(kind, data)


class TestCurrencyPrecision(unittest.TestCase):
    KWD_TOTALS = {"total_taxable_amount": "1.234", "total_vat_amount": "0.000",
                  "grand_total": "1.234"}

    def _kwd(self, kind, **top):
        return _build(kind, qty="1", price="1.234", totals=self.KWD_TOTALS,
                      line={"vat_rate": "0"}, **{"currency": "KWD", **top})

    def test_three_decimal_currency_checks_and_prints_three_decimals(self):
        for kind in ("quote", "po"):
            with self.subTest(kind):
                doc = _go(kind, self._kwd(kind, currency_precision=3))
                self.assertIn('<bdi dir="ltr">1.234 KWD</bdi>', doc)
                self.assertIn('<bdi dir="ltr">0.000 KWD</bdi>', doc)
                self.assertNotIn('<bdi dir="ltr">1.23 KWD</bdi>', doc)

    def test_precision_string_is_accepted(self):
        self.assertIn("1.234 KWD", _go("quote", self._kwd("quote", currency_precision="3")))

    def test_a_two_decimal_currency_refuses_three_decimal_amounts(self):
        for kind in _KINDS:
            for explicit in ({}, {"currency_precision": 2}):
                with self.subTest(kind, explicit=bool(explicit)):
                    with self.assertRaisesRegex(ValueError, r"2 decimals"):
                        _go(kind, self._kwd(kind, currency="SAR", **explicit))

    def test_precision_must_match_the_iso_4217_minor_units_of_the_currency(self):
        sar = self._kwd("quote", currency="SAR", currency_precision=3)  # 1.234 SAR
        with self.assertRaisesRegex(ValueError, r"currency_precision 3.*SAR.*2"):
            render_branded_quote_html(sar)
        with self.assertRaisesRegex(ValueError, r"currency_precision 3.*SAR.*2"):
            render_branded_purchase_order_html(self._kwd("po", currency="SAR",
                                                         currency_precision=3))
        with self.assertRaisesRegex(ValueError, r"currency_precision 2.*KWD.*3"):
            render_branded_quote_html(self._kwd("quote", currency_precision=2))
        self.assertIn("1.234 KWD", render_branded_quote_html(
            self._kwd("quote", currency_precision=3)))

    def test_known_currency_table_and_default_precision_follow_the_currency(self):
        for code, places in (("SAR", 2), ("AED", 2), ("EGP", 2), ("QAR", 2), ("USD", 2),
                             ("EUR", 2), ("KWD", 3), ("BHD", 3), ("OMR", 3)):
            for kind in ("quote", "po"):
                with self.subTest(code, kind=kind):
                    amount = "1." + "2" * places
                    zero = "0." + "0" * places
                    data = _build(kind, qty="1", price=amount, currency=code,
                                  line={"vat_rate": "0"},
                                  totals={"total_taxable_amount": amount,
                                          "total_vat_amount": zero, "grand_total": amount})
                    self.assertIn(f"{amount} {code}", _go(kind, data))  # default follows currency
                    data["currency_precision"] = places  # the explicit, matching value
                    self.assertIn(f"{amount} {code}", _go(kind, data))
                    data["currency_precision"] = 2 if places == 3 else 3
                    with self.assertRaisesRegex(ValueError, r"currency_precision"):
                        _go(kind, data)

    def test_unknown_or_malformed_currency_is_refused(self):
        for bad in ("XYZ", "sar", "SA", "", " ", "SAR2", "Riyal"):
            for kind in _KINDS:
                with self.subTest(kind, currency=bad):
                    with self.assertRaisesRegex(ValueError, r"currency"):
                        _go(kind, _build(kind, currency=bad))

    def test_amounts_beyond_the_currency_precision_are_refused(self):
        data = self._kwd("quote", currency_precision=3)
        data["totals"] = {"total_taxable_amount": "1.2345", "total_vat_amount": "0.0000",
                          "grand_total": "1.2345"}
        with self.assertRaisesRegex(ValueError, r"3 decimals"):
            render_branded_quote_html(data)
        data = self._kwd("po", currency_precision=3)
        data["lines"][0]["line_total"] = "1.2340001"
        with self.assertRaises(ValueError):
            render_branded_purchase_order_html(data)

    def test_invalid_precision_is_refused(self):
        for bad in (True, False, -1, 5, 9, "x", "", 2.5, "2.5", [], {}):
            for kind in _KINDS:
                with self.subTest(kind, bad=bad):
                    with self.assertRaisesRegex(ValueError, r"currency_precision"):
                        _go(kind, _build(kind, currency_precision=bad))

    def test_tax_invoices_print_two_decimals_only_so_other_precision_is_refused(self):
        for kind in _INVOICE_KINDS:
            with self.subTest(kind, case="three decimals"):
                with self.assertRaisesRegex(ValueError, r"currency_precision.*2 decimals"):
                    _go(kind, self._kwd(kind, currency_precision=3))
            with self.subTest(kind, case="explicit two"):
                self.assertIn("230.00", _go(kind, _build(kind, currency_precision=2))
                              if kind == "tax" else "230.00")
                _go(kind, _build(kind, currency_precision="2"))


class TestUnitPriceDisplay(unittest.TestCase):
    """A unit price is never printed below the precision the check used (10 x 1.004)."""

    TOTALS = {"total_taxable_amount": "10.04", "total_vat_amount": "1.51", "grand_total": "11.55"}

    def test_quote_and_po_print_the_unit_price_at_its_supplied_precision(self):
        for kind in ("quote", "po"):
            with self.subTest(kind):
                doc = _go(kind, _build(kind, qty="10", price="1.004", totals=self.TOTALS))
                self.assertIn('<bdi dir="ltr">1.004</bdi>', doc)
                self.assertNotIn('<bdi dir="ltr">1.00</bdi>', doc)
                self.assertIn('<bdi dir="ltr">10.04</bdi>', doc)  # 10 x 1.004, line amount
                # a two decimal price still prints with two decimals
                self.assertIn('<bdi dir="ltr">1.00</bdi>',
                              _go(kind, _build(kind, qty="10", price="1.00", totals={
                                  "total_taxable_amount": "10.00", "total_vat_amount": "1.50",
                                  "grand_total": "11.50"})))

    def test_a_price_with_more_than_six_decimals_is_refused(self):
        with self.assertRaisesRegex(ValueError, r"unit_price.*6 decimals"):
            _go("quote", _build("quote", qty="1", price="1.0000001",
                                totals={"total_taxable_amount": "1.00", "total_vat_amount": "0.15",
                                        "grand_total": "1.15"}))

    def test_tax_invoices_refuse_a_price_the_fixed_two_decimal_print_would_round(self):
        # ERP-007 prints unit prices with two decimals and is not changed here, so 1.004 would
        # print as 1.00 next to a 10.04 amount: refuse instead of printing a sheet that disagrees.
        for kind in _INVOICE_KINDS:
            with self.subTest(kind):
                with self.assertRaisesRegex(ValueError, r"unit_price 1\.004.*2 decimals"):
                    _go(kind, _build(kind, qty="10", price="1.004",
                                     line={"line_total": "10.04"}, totals=self.TOTALS))

    def test_a_discount_the_print_would_round_is_refused(self):
        for kind in _KINDS:
            with self.subTest(kind):
                with self.assertRaisesRegex(ValueError, r"discount 5\.005.*2 decimals"):
                    _go(kind, _build(kind, line={"discount": "5.005"}))


class TestFontFallbackKeywords(unittest.TestCase):
    """CSS-wide and reserved keywords are not valid family names in the fallback list."""

    def _stack(self, family="Readex Pro", fallback="sans-serif"):
        from change_engine.print_formats.document_tokens import load_document_tokens

        data = _light_tokens()
        data["typography"]["families"]["body"].update(family=family, fallback=fallback)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tokens.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return load_document_tokens(path).font_stack

    def test_css_wide_and_reserved_keywords_are_refused(self):
        from change_engine.print_formats.document_tokens import DocumentTokenError

        for keyword in ("inherit", "initial", "unset", "revert", "revert-layer", "default",
                        "INHERIT", "Default"):
            for fallback in (f"{keyword}, sans-serif", f"sans-serif, {keyword}", keyword):
                with self.subTest(fallback=fallback), self.assertRaises(DocumentTokenError):
                    self._stack(fallback=fallback)
            with self.subTest(family=keyword), self.assertRaises(DocumentTokenError):
                self._stack(family=keyword)

    def test_generic_families_are_allowed_only_as_generics(self):
        from change_engine.print_formats.document_tokens import DocumentTokenError

        self.assertEqual(self._stack(fallback="serif, sans-serif, system-ui, monospace"),
                         "'Readex Pro', serif, sans-serif, system-ui, monospace")
        for generic in ("serif", "sans-serif", "system-ui", "monospace"):
            # a quoted primary family named like a generic would be a different font, not the generic
            with self.subTest(family=generic), self.assertRaises(DocumentTokenError):
                self._stack(family=generic)

    def test_keyword_like_prefixes_in_real_names_stay_valid(self):
        self.assertEqual(self._stack(fallback="Initial Sans, Defaulter, sans-serif"),
                         "'Readex Pro', Initial Sans, Defaulter, sans-serif")


_ZERO_TOTALS = {"total_taxable_amount": "0.00", "total_vat_amount": "0.00", "grand_total": "0.00"}


def _boom_free(kind, qty, line=None, totals=None):
    return _build(kind, qty=qty, price="1.00", line=line,
                  totals=totals or _ZERO_TOTALS)


class TestCheckedSnapshotIsWhatPrints(unittest.TestCase):
    """The renderers print from the snapshot the check built, never from the caller's input again."""

    @staticmethod
    def _after_check(real, mutate):
        def wrapper(*args, **kwargs):
            result = real(*args, **kwargs)
            mutate()  # the caller changes its own nested objects once the check has passed
            return result
        return wrapper

    def test_nested_input_mutated_after_validation_cannot_change_the_print(self):
        from change_engine.print_formats import branded_documents

        for kind in _KINDS:
            with self.subTest(kind):
                expected = _go(kind, _build(kind))
                data = _build(kind)

                def mutate(data=data):
                    data["totals"]["total_taxable_amount"] = "999.99"
                    data["totals"]["grand_total"] = "999.99"
                    data["lines"][0]["unit_price"] = "999.99"
                    data["lines"][0]["quantity"] = "9"
                    data["lines"][0]["discount"] = "1.00"
                    data["lines"][0]["vat_rate"] = "0.99"
                    data["lines"][0]["line_total"] = "999.99"
                    data["lines"][0]["description"] = "TAMPERED"
                    data["buyer"]["name"] = "TAMPERED"

                real = branded_documents.check_amounts
                with mock.patch.object(branded_documents, "check_amounts",
                                       self._after_check(real, mutate)):
                    printed = _go(kind, data)
                self.assertEqual(printed, expected)
                self.assertNotIn("999.99", printed)
                self.assertNotIn("TAMPERED", printed)

    def test_a_mapping_that_changes_between_reads_prints_what_the_check_saw(self):
        from collections.abc import Mapping

        class Flip(Mapping):
            """Answers truthfully once per key, then lies (a nested view changed under us)."""

            def __init__(self, good, bad):
                self._good, self._bad, self._reads = dict(good), dict(bad), {}

            def __getitem__(self, key):
                n = self._reads[key] = self._reads.get(key, 0) + 1
                return (self._good if n == 1 else self._bad)[key]

            def __iter__(self):
                return iter(self._good)

            def __len__(self):
                return len(self._good)

        for kind in _KINDS:
            with self.subTest(kind):
                expected = _go(kind, _build(kind))
                data = _build(kind)
                data["totals"] = Flip(data["totals"], {k: "999.99" for k in data["totals"]})
                data["lines"][0] = Flip(data["lines"][0], {**data["lines"][0], "unit_price": "999.99",
                                                           "quantity": "9"})
                try:
                    printed = _go(kind, data)
                except ValueError:
                    continue  # refusing is acceptable; printing a re-read figure is not
                self.assertEqual(printed, expected)
                self.assertNotIn("999.99", printed)


class TestPrintBoundaryPrecision(unittest.TestCase):
    def test_a_small_quantity_prints_at_its_supplied_precision_in_any_context(self):
        # Chosen rule: print the quantity exactly as supplied (no rounding to a different visible
        # value than the one the check used); 0.0049 x 1.00 = 0.00 on a two decimal grid.
        from decimal import localcontext

        for kind in _KINDS:
            for prec in (28, 3, 1):
                with self.subTest(kind=kind, prec=prec), localcontext() as ctx:
                    ctx.prec = prec
                    doc = _go(kind, _boom_free(kind, "0.0049", {"line_net_amount": "0.00"}))
                    self.assertIn('<bdi dir="ltr">0.0049</bdi>', doc)
                    self.assertNotIn('<bdi dir="ltr">0.005</bdi>', doc)

    def test_a_wide_quantity_is_not_shortened_by_the_caller_context(self):
        from decimal import localcontext

        for kind in ("quote", "po"):
            with self.subTest(kind), localcontext() as ctx:
                ctx.prec = 4
                doc = _go(kind, _build(kind, qty="1234567.5", price="0.00",
                                       totals=_ZERO_TOTALS))
                self.assertIn('<bdi dir="ltr">1234567.5</bdi>', doc)

    def test_reconciliation_does_not_depend_on_the_callers_decimal_context(self):
        from decimal import localcontext

        def two_lines(kind, taxable, vat, grand):
            data = _build(kind, qty="1", price="9999.99", line={"vat_rate": "0"},
                          totals={"total_taxable_amount": taxable, "total_vat_amount": vat,
                                  "grand_total": grand})
            data["lines"].append({"item_code": "ITEM-002", "description": "Extra", "quantity": "1",
                                  "unit_price": "0.02", "discount": "0.00", "vat_rate": "0",
                                  "vat_category": "Z" if kind in _INVOICE_KINDS else ""})
            return data

        for kind in ("neutral", "quote", "po"):
            with self.subTest(kind), localcontext() as ctx:
                ctx.prec = 6
                with self.assertRaisesRegex(ValueError, r"Lines total 10000\.01.*10000\.00"):
                    _go(kind, two_lines(kind, "10000.00", "0.00", "10000.00"))
                doc = _go(kind, two_lines(kind, "10000.01", "0.00", "10000.01"))
                self.assertIn("10,000.01", doc)
                self.assertNotIn("10,000.00", doc)

    def test_booleans_are_refused_as_money_values(self):
        for kind in _KINDS:
            for field in ("discount", "unit_price", "quantity", "line_total", "line_net_amount"):
                for value in (False, True):
                    with self.subTest(kind=kind, field=field, value=value):
                        data = _build(kind)
                        data["lines"][0][field] = value
                        with self.assertRaisesRegex(ValueError, rf"Line 1.*{field}|{field}"):
                            _go(kind, data)
            for field in ("total_taxable_amount", "total_vat_amount", "grand_total"):
                with self.subTest(kind=kind, total=field):
                    data = _build(kind)
                    data["totals"][field] = False
                    with self.assertRaises(ValueError):
                        _go(kind, data)


class TestExactNumbersAtTheSnapshotBoundary(unittest.TestCase):
    """Round 4: a numeric subclass cannot reach the printer; every number is a built-in copy."""

    class EvilDecimal(Decimal):
        armed = False

        def normalize(self, *args, **kwargs):
            return Decimal(9) if type(self).armed else Decimal.normalize(self, *args, **kwargs)

        def __str__(self):
            return "9" if type(self).armed else Decimal.__str__(self)

        def __format__(self, spec):
            return "9" if type(self).armed else Decimal.__format__(self, spec)

    class EvilInt(int):
        armed = False

        def __str__(self):
            return "9" if type(self).armed else int.__str__(self)

        def __int__(self):
            return 9 if type(self).armed else int.__int__(self)

    @classmethod
    def _wrap(cls, data, factory):
        """The same document with every number of the checked lines and totals subclassed."""
        for line in data["lines"]:
            for field in ("quantity", "unit_price", "discount", "vat_rate", "line_net_amount",
                          "distributed_discount_amount"):
                if line.get(field) not in (None, ""):
                    line[field] = factory(line[field])
        for field, value in list(data["totals"].items()):
            data["totals"][field] = factory(value)
        return data

    def test_a_decimal_subclass_that_changes_after_validation_prints_the_checked_value(self):
        from change_engine.print_formats import branded_documents

        evil = self.EvilDecimal
        for kind in _KINDS:
            with self.subTest(kind):
                expected = _go(kind, _build(kind, qty="2.50", price="80.00",
                                            totals=_DISCOUNT_TOTALS | {
                                                "total_taxable_amount": "200.00",
                                                "total_vat_amount": "30.00",
                                                "grand_total": "230.00"}))
                data = self._wrap(_build(kind, qty="2.50", price="80.00", totals={
                    "total_taxable_amount": "200.00", "total_vat_amount": "30.00",
                    "grand_total": "230.00"}), evil)
                real = branded_documents.check_amounts

                def arm_after_check(*args, **kwargs):
                    result = real(*args, **kwargs)
                    evil.armed = True  # the subclass starts lying once validation has passed
                    return result

                try:
                    with mock.patch.object(branded_documents, "check_amounts", arm_after_check):
                        printed = _go(kind, data)
                finally:
                    evil.armed = False
                self.assertEqual(printed, expected)
                self.assertIn("2.5", printed)

    def test_the_subclass_is_never_asked_anything_even_from_the_start(self):
        for subclass_kind, evil in (("decimal", self.EvilDecimal), ("int", self.EvilInt)):
            for kind in _KINDS:
                with self.subTest(number=subclass_kind, kind=kind):
                    expected = _go(kind, _build(kind))
                    data = _build(kind)
                    if subclass_kind == "decimal":
                        data["lines"][0]["quantity"] = evil("2")
                        data["lines"][0]["unit_price"] = evil("100.00")
                        data["totals"] = {k: evil(v) for k, v in data["totals"].items()}
                    else:
                        data["lines"][0]["quantity"] = evil(2)
                        data["lines"][0]["unit_price"] = evil(100)
                        data["totals"] = {"total_taxable_amount": evil(200),
                                          "total_vat_amount": evil(30), "grand_total": evil(230)}
                    evil.armed = True
                    try:
                        printed = _go(kind, data)
                    finally:
                        evil.armed = False
                    self.assertEqual(printed, expected)

    def test_snapshot_numbers_are_exact_builtin_types(self):
        from change_engine.print_formats.document_reconciliation import snapshot_document

        data = _build("quote")
        data["lines"][0]["quantity"] = self.EvilDecimal("2")
        data["lines"][0]["discount"] = self.EvilInt(0)
        snap = snapshot_document(data)
        self.assertIs(type(snap["lines"][0]["quantity"]), Decimal)
        self.assertIs(type(snap["lines"][0]["discount"]), int)
        self.assertEqual(snap["lines"][0]["quantity"], Decimal("2"))

    def test_non_finite_and_float_values_stay_refused(self):
        for kind in _KINDS:
            for bad in (Decimal("NaN"), Decimal("Infinity"), 2.0):
                with self.subTest(kind=kind, bad=bad):
                    data = _build(kind)
                    data["lines"][0]["quantity"] = bad
                    with self.assertRaises(ValueError):
                        _go(kind, data)


class TestIntegerDigitCap(unittest.TestCase):
    def test_a_number_with_more_than_thirty_integer_digits_is_refused(self):
        for kind in _KINDS:
            for field, value in (("quantity", "9E+30"), ("quantity", Decimal("9E+30")),
                                 ("unit_price", "9E+30"), ("line_net_amount", "9E+30"),
                                 ("quantity", "9" * 31)):
                with self.subTest(kind=kind, field=field, value=value):
                    data = _build(kind, totals=_ZERO_TOTALS)
                    data["lines"][0].update(quantity="1", unit_price="0")
                    data["lines"][0][field] = value
                    with self.assertRaisesRegex(ValueError, r"out of range"):
                        _go(kind, data)
            for total in ("total_taxable_amount", "total_vat_amount", "grand_total"):
                with self.subTest(kind=kind, total=total):
                    data = _build(kind, qty="1", price="0", totals=_ZERO_TOTALS)
                    data["totals"][total] = "9E+30"
                    with self.assertRaisesRegex(ValueError, r"out of range"):
                        _go(kind, data)

    def test_the_largest_amounts_that_fit_both_caps_are_still_accepted(self):
        # 28 integer digits + 2 decimals = 30 coefficient digits.
        for kind in ("quote", "po"):
            with self.subTest(kind):
                big = "9" * 28 + ".00"
                doc = _go(kind, _build(kind, qty="1", price=big, totals={
                    "total_taxable_amount": big, "total_vat_amount": "0.00", "grand_total": big}))
                self.assertIn("9,999,999,999,999,999,999,999,999,999.00", doc)

    def test_the_cap_counts_integer_digits_of_the_value(self):
        from change_engine.print_formats.document_reconciliation import _number

        for text, ok in (("9" * 30, True), ("9" * 31, False), ("9E+29", True), ("9E+30", False),
                         ("1E+30", False), ("0.000001", True), ("1E-31", False),
                         ("0E+40", False)):
            with self.subTest(text):
                errors: list[str] = []
                result = _number(text, "x", errors)
                self.assertEqual(result is not None, ok, (result, errors))


class TestAdapterEmitsDiscountFields(unittest.TestCase):
    """The ERP-007 adapter passes the engine's discount through; nothing is lost or recomputed."""

    def _env(self):
        from change_engine.tests import test_erp_007_bilingual_tax_invoice as erp007

        case = erp007.TestFrappeSalesInvoiceIntegration("test_ksa_sales_invoice_maps_and_renders_with_qr")
        return case._mock_ksa_frappe_env()[0]

    @staticmethod
    def _invoice(*, discount=True, allocated=True):
        from types import SimpleNamespace
        import json as _json

        item = dict(
            item_code="ITEM-001", item_name="Office Desk Chair", custom_item_name_ar="كرسي مكتب",
            qty=2, rate=Decimal("100.00"), discount_amount=Decimal("0.00"),
            amount=Decimal("200.00"),
            net_amount=Decimal("180.00") if discount and allocated else Decimal("200.00"),
            item_tax_rate=_json.dumps({"VAT 15%": 15.0}))
        if discount and allocated:
            item["distributed_discount_amount"] = Decimal("20.00")
        return SimpleNamespace(
            name="ACC-SINV-2026-0009", company="Al-Noor Trading Est",
            company_address="ADDR-COMP-1", customer="CUST-GULF",
            customer_name="Gulf Enterprises LLC", customer_address="ADDR-CUST-1",
            posting_date=__import__("datetime").date(2026, 11, 17),
            posting_time=__import__("datetime").timedelta(hours=14, minutes=30),
            currency="SAR", is_pos=0, is_return=0, is_debit_note=0,
            apply_discount_on="Net Total",
            discount_amount=Decimal("20.00") if discount else Decimal("0.00"),
            net_total=Decimal("180.00") if discount else Decimal("200.00"),
            total_taxes_and_charges=Decimal("27.00") if discount else Decimal("30.00"),
            grand_total=Decimal("207.00") if discount else Decimal("230.00"),
            taxes=[SimpleNamespace(rate=15.0)], items=[SimpleNamespace(**item)])

    def test_discount_fields_are_emitted_in_the_names_the_branded_check_reads(self):
        from change_engine.print_formats import sales_invoice_to_zatca_dict

        payload, mode = sales_invoice_to_zatca_dict(self._invoice(), frappe_module=self._env())
        self.assertEqual(mode, "zatca_sa")
        self.assertEqual(payload["totals"]["discount_amount"], "20.00")
        line = payload["lines"][0]
        self.assertEqual(line["distributed_discount_amount"], "20.00")
        self.assertEqual(line["line_net_amount"], "180.00")
        self.assertEqual((line["quantity"], line["unit_price"]), ("2", "100.00"))

    def test_an_undiscounted_invoice_payload_is_unchanged(self):
        from change_engine.print_formats import sales_invoice_to_zatca_dict

        payload, _ = sales_invoice_to_zatca_dict(self._invoice(discount=False),
                                                 frappe_module=self._env())
        self.assertNotIn("discount_amount", payload["totals"])
        self.assertNotIn("discount_amount", payload)
        self.assertNotIn("distributed_discount_amount", payload["lines"][0])
        self.assertEqual(sorted(payload["totals"]),
                         ["grand_total", "total_taxable_amount", "total_vat_amount"])

    def test_a_ten_percent_document_discount_agrees_in_erp_007_and_both_branded_modes(self):
        from change_engine.print_formats import (
            render_tax_invoice_html, sales_invoice_to_zatca_dict)

        for allocated in (True, False):
            with self.subTest(allocated=allocated):
                payload, _ = sales_invoice_to_zatca_dict(
                    self._invoice(allocated=allocated), frappe_module=self._env())
                renders = {
                    "erp-007 zatca": render_tax_invoice_html(payload, mode="zatca_sa"),
                    "erp-007 neutral": render_tax_invoice_html(payload, mode="neutral"),
                    "branded zatca": render_branded_tax_invoice_html(payload, mode="zatca_sa"),
                    "branded neutral": render_branded_tax_invoice_html(payload, mode="neutral"),
                }
                seen = set()
                for name, doc in renders.items():
                    totals = _printed_totals(doc)
                    seen.add((totals["Total Taxable Amount"], totals["Total VAT"],
                              totals["Grand Total"]))
                    with self.subTest(document=name):
                        if name.startswith("branded"):
                            _assert_printed_numbers_add_up(
                                self, doc, taxable="180.00",
                                discount_row=None if allocated else "20.00")
                self.assertEqual(seen, {(Decimal("180.00"), Decimal("27.00"), Decimal("207.00"))})

    def test_the_engine_net_amount_that_does_not_carry_its_allocation_is_refused(self):
        from change_engine.print_formats import sales_invoice_to_zatca_dict

        payload, _ = sales_invoice_to_zatca_dict(self._invoice(), frappe_module=self._env())
        payload["lines"][0]["line_net_amount"] = "200.00"
        for mode in ("zatca_sa", "neutral"):
            with self.subTest(mode), self.assertRaisesRegex(ValueError, r"Line 1"):
                render_branded_tax_invoice_html(payload, mode=mode)

    def test_a_credit_note_keeps_the_discount_fields_as_positive_magnitudes(self):
        from change_engine.print_formats import sales_invoice_to_zatca_dict

        inv = self._invoice()
        inv.is_return = 1
        inv.return_against = "ACC-SINV-2026-0001"
        inv.net_total, inv.total_taxes_and_charges, inv.grand_total = (
            Decimal("-180.00"), Decimal("-27.00"), Decimal("-207.00"))
        inv.discount_amount = Decimal("-20.00")
        item = inv.items[0]
        item.qty, item.amount, item.net_amount = -2, Decimal("-200.00"), Decimal("-180.00")
        item.distributed_discount_amount = Decimal("-20.00")
        payload, _ = sales_invoice_to_zatca_dict(inv, frappe_module=self._env())
        self.assertEqual(payload["totals"]["discount_amount"], "20.00")
        self.assertEqual(payload["lines"][0]["distributed_discount_amount"], "20.00")
        self.assertEqual(payload["lines"][0]["line_net_amount"], "180.00")


def _po_with(**line):
    data = _po_data()
    data["lines"][0].update(line)
    return data


# --------------------------------------------------------------------------------------
# Footer wording and Arabic review marking
# --------------------------------------------------------------------------------------
class TestFooterAndArabicReview(unittest.TestCase):
    def test_footer_has_no_product_name_and_uses_the_localised_label(self):
        from change_engine.print_formats.document_labels import DOCUMENT_LABELS

        ar, en = DOCUMENT_LABELS["powered_by"]
        for kind in ALL_KINDS:
            with self.subTest(kind):
                doc = _render(kind)
                self.assertNotIn("Orrery", doc)
                self.assertNotIn("orrery", doc.lower())
                self.assertIn(en, doc)
                self.assertIn(ar, doc)
                self.assertNotIn("Orrery", _render(kind, branding=TENANT_BRANDING))

    def test_footer_label_is_unreviewed_arabic(self):
        self.assertIn("powered_by", UNREVIEWED_ARABIC_LABELS)

    def test_every_new_label_is_unreviewed_and_not_wired_to_a_customer_path(self):
        from change_engine.print_formats.document_labels import DOCUMENT_LABELS

        self.assertEqual(set(UNREVIEWED_ARABIC_LABELS), set(DOCUMENT_LABELS))
        hooks = (_PRINT_FORMATS.parent / "hooks.py").read_text(encoding="utf-8")
        for name in ("branded_documents", "render_branded", "document_labels"):
            self.assertNotIn(name, hooks)  # no customer-facing hook until the Arabic is reviewed


# --------------------------------------------------------------------------------------
# Round 5 (re-review of f8feffe): the pinned engine's discount semantics. ERPNext
# erpnext/controllers/taxes_and_totals.py at e5cde8c4b9e3f7f567a92ca3e65fd411402b89ce:
# * item values (L193-268): ``rate`` is already net of the item discount (``discount_amount`` is
#   per unit, ``price_list_rate - rate``) and ``amount = rate x qty``;
# * document discount (L858-1002): ``discount_amount`` (from ``additional_discount_percentage`` of
#   the total named by ``apply_discount_on``) is spread onto every line in proportion to its net
#   amount over the Net Total, or over the Grand Total (VAT included) for "Grand Total"; each
#   line's share is ``distributed_discount_amount`` and its ``net_amount`` carries it; then the
#   taxes are recomputed on the discounted nets and grand total = net total + taxes (L771-785).
# --------------------------------------------------------------------------------------
_INFO_ROW_EN = "Invoice discount (included in line amounts)"


def _engine_doc(kind, *, basis, doc_discount, lines, totals, percentage=None, where="totals"):
    """A ``kind`` document shaped like the engine's: ``lines`` are (qty, price, alloc, net)."""
    data = _KINDS[kind][0]()
    template = data["lines"][0]
    data["lines"] = []
    for idx, (qty, price, alloc, net) in enumerate(lines, start=1):
        line = {**template, "item_code": f"ITEM-{idx:03d}", "quantity": qty,
                "unit_price": price, "discount": "0.00"}
        if alloc is not None:
            line["distributed_discount_amount"] = alloc
        if net is not None:
            line["line_net_amount"] = net
        data["lines"].append(line)
    data["totals"] = dict(zip(("total_taxable_amount", "total_vat_amount", "grand_total"), totals))
    target = data["totals"] if where == "totals" else data
    if basis is not None:
        target["apply_discount_on"] = basis
    if doc_discount is not None:
        target["discount_amount"] = doc_discount
    if percentage is not None:
        target["additional_discount_percentage"] = percentage
    return data


# 200.00 + 15% VAT, 10% off: Grand Total -> 23.00 (VAT-inclusive), Net Total -> 20.00; the engine
# spreads 20.00 onto the line either way and posts 180.00 / 27.00 / 207.00.
_GRAND = dict(basis="Grand Total", doc_discount="23.00", percentage="10",
              lines=[("2", "100.00", "20.00", "180.00")], totals=("180.00", "27.00", "207.00"))
_NET = dict(basis="Net Total", doc_discount="20.00", percentage="10",
            lines=[("2", "100.00", "20.00", "180.00")], totals=("180.00", "27.00", "207.00"))


class TestOmittedLineDiscountStillShowsTheAllocation(unittest.TestCase):
    """Item 1: the printed line discount is line discount + allocation, key or no key."""

    def test_no_discount_key_prints_the_allocation_beside_the_net_amount(self):
        for kind in _KINDS:
            for alloc, net, row in (("20.00", "180.00", None), ("12.00", "188.00", "8.00")):
                with self.subTest(kind=kind, alloc=alloc):
                    data = _engine_doc(kind, basis="Net Total", doc_discount="20.00",
                                       lines=[("2", "100.00", alloc, net)],
                                       totals=("180.00", "27.00", "207.00"))
                    del data["lines"][0]["discount"]
                    doc = _go(kind, data)
                    _assert_printed_numbers_add_up(self, doc, taxable="180.00", discount_row=row)
                    line = _printed_lines(doc)[0]
                    self.assertEqual((line["discount"], line["amount"]),
                                     (Decimal(alloc), Decimal(net)))

    def test_no_discount_key_and_no_allocation_still_prints_zero(self):
        for kind in _KINDS:
            with self.subTest(kind):
                data = _build(kind)
                del data["lines"][0]["discount"]
                self.assertEqual(_printed_lines(_go(kind, data))[0]["discount"], Decimal("0.00"))


class TestGrandAndNetTotalDiscounts(unittest.TestCase):
    """Item 2: ``apply_discount_on`` "Grand Total" (VAT-inclusive) and "Net Total"."""

    def test_the_engine_grand_total_discount_prints_and_adds_up_in_every_document(self):
        for kind in _KINDS:
            for where in ("totals", "top"):
                with self.subTest(kind=kind, where=where):
                    doc = _go(kind, _engine_doc(kind, where=where, **_GRAND))
                    _assert_printed_numbers_add_up(self, doc, taxable="180.00",
                                                   discount_row=None)
                    totals = _printed_totals(doc)
                    self.assertEqual((totals["Total VAT"], totals["Grand Total"]),
                                     (Decimal("27.00"), Decimal("207.00")))

    def test_the_net_total_variant_prints_the_same_figures(self):
        for kind in _KINDS:
            with self.subTest(kind):
                grand = _printed_totals(_go(kind, _engine_doc(kind, **_GRAND)))
                net = _printed_totals(_go(kind, _engine_doc(kind, **_NET)))
                self.assertEqual({k: v for k, v in grand.items() if k != _INFO_ROW_EN},
                                 {k: v for k, v in net.items() if k != _INFO_ROW_EN})

    def test_a_grand_total_discount_spread_over_two_lines_with_engine_rounding(self):
        # 100.00 + 33.33 = 133.33 net, VAT 20.00, grand 153.33; 10% = 15.33 spread as 10.00 and
        # 3.33 (15.33 x 33.33 / 153.33 = 3.3324); nets 90.00 + 30.00; VAT 18.00; grand 138.00.
        for kind in _KINDS:
            with self.subTest(kind):
                doc = _go(kind, _engine_doc(
                    kind, basis="Grand Total", doc_discount="15.33", percentage="10",
                    lines=[("1", "100.00", "10.00", "90.00"), ("1", "33.33", "3.33", "30.00")],
                    totals=("120.00", "18.00", "138.00")))
                _assert_printed_numbers_add_up(self, doc, taxable="120.00", discount_row=None)

    def test_figures_that_do_not_follow_the_engine_are_refused_never_corrected(self):
        def grand(**over):
            return {**_GRAND, **over}

        cases = {
            "grand total discount left off the lines": (
                grand(lines=[("2", "100.00", None, "200.00")]), r"Lines total 200\.00 != "
                r"total_taxable_amount 180\.00.*Grand Total"),
            "part of a grand total discount left off the lines": (
                grand(lines=[("2", "100.00", "12.00", "188.00")]), r"Lines total 188\.00"),
            "net total figures labelled grand total": (
                grand(doc_discount="20.00", percentage=None),
                r"carry 20\.00 of the Grand Total discount 20\.00.*17\.62"),
            "VAT not recomputed after the discount": (
                grand(totals=("180.00", "30.00", "210.00"), percentage=None),
                r"carry 20\.00 of the Grand Total discount 23\.00"),
            "no apply_discount_on with a discount": (
                grand(basis=None), r"apply_discount_on is required"),
            "unknown apply_discount_on": (
                grand(basis="Total"), r"apply_discount_on must be 'Grand Total' or 'Net Total'"),
            "boolean apply_discount_on": (
                grand(basis=True), r"apply_discount_on must be"),
            "percentage that does not give the discount": (
                {**_NET, "percentage": "15"}, r"additional_discount_percentage 15 of Net Total "
                r"200\.00 is 30\.00, not discount_amount 20\.00"),
            "grand total percentage that does not give the discount": (
                grand(percentage="5"), r"additional_discount_percentage 5 of Grand Total"),
            "percentage over 100": (grand(percentage="150"), r"from 0 to 100"),
            "percentage without a discount": (
                {**_NET, "doc_discount": None, "lines": [("2", "100.00", None, "200.00")],
                 "totals": ("200.00", "30.00", "230.00")},
                r"additional_discount_percentage 10 needs the engine's discount_amount"),
            "unparsable percentage": (grand(percentage="ten"), r"is not a valid"),
        }
        for kind in _KINDS:
            for name, (params, reason) in cases.items():
                with self.subTest(kind=kind, case=name):
                    with self.assertRaisesRegex(ValueError, reason):
                        _go(kind, _engine_doc(kind, **params))

    def test_top_level_and_totals_apply_discount_on_must_agree(self):
        for kind in _KINDS:
            with self.subTest(kind):
                data = _engine_doc(kind, **_GRAND)
                data["apply_discount_on"] = "Net Total"
                with self.assertRaisesRegex(ValueError, r"apply_discount_on differs"):
                    _go(kind, data)

    def test_a_cash_or_non_trade_discount_is_refused(self):
        # The engine takes it off the grand total only (L86-90, L913-915), never off the lines
        # or the VAT.
        for kind in _KINDS:
            with self.subTest(kind):
                data = _engine_doc(kind, **_GRAND)
                data["is_cash_or_non_trade_discount"] = 1
                with self.assertRaisesRegex(ValueError, r"is_cash_or_non_trade_discount"):
                    _go(kind, data)

    def test_totals_that_do_not_add_up_are_refused_with_or_without_a_discount(self):
        # Grand total = net total + taxes (L771-785). Tax invoices keep ERP-007's own refusal
        # (ZATCA Phase 1 or the neutral check) and its error type.
        for kind in _KINDS:
            for name, data in (
                    ("no discount", _build(kind, totals={
                        "total_taxable_amount": "200.00", "total_vat_amount": "30.00",
                        "grand_total": "231.00"})),
                    ("grand total discount", _engine_doc(kind, **{
                        **_GRAND, "percentage": None,
                        "totals": ("180.00", "27.00", "208.00")}))):
                with self.subTest(kind=kind, case=name):
                    error = ZatcaValidationError if kind == "tax" else ValueError
                    with self.assertRaises(error) as caught:
                        _go(kind, data)
                    detail = " ".join(getattr(caught.exception, "errors", None)
                                      or [str(caught.exception)])
                    self.assertRegex(detail, r"\+ .*VAT.* != grand.total 2(31|08)\.00")


class TestInvoiceDiscountInformationRow(unittest.TestCase):
    """Item 4 (UNVERIFIED, Q-520): the allocated invoice discount is also shown on its own."""

    def _row(self, doc):
        return _printed_totals(doc).get(_INFO_ROW_EN)

    def test_tax_invoice_mode_shows_the_allocated_discount_without_subtracting_it_again(self):
        for params, label in ((_NET, "net"), (_GRAND, "grand")):
            for invoice_type in ("standard", "simplified"):
                with self.subTest(basis=label, invoice_type=invoice_type):
                    data = _engine_doc("tax", **params)
                    data["invoice_type"] = invoice_type
                    if invoice_type == "simplified":
                        data["transaction_type"] = "simplified_tax_invoice"
                    doc = _go("tax", data)
                    self.assertEqual(self._row(doc), Decimal("20.00"))
                    _assert_printed_numbers_add_up(self, doc, taxable="180.00",
                                                   discount_row=None)

    def test_the_row_is_labelled_bilingually_and_unreviewed(self):
        from change_engine.print_formats.document_labels import DOCUMENT_LABELS

        ar, en = DOCUMENT_LABELS["invoice_discount_included"]
        self.assertEqual(en, _INFO_ROW_EN)
        self.assertIn("invoice_discount_included", UNREVIEWED_ARABIC_LABELS)
        doc = _go("tax", _engine_doc("tax", **_NET))
        totals = doc.split('class="totals-table"', 1)[1]
        self.assertIn(f'<th class="tot-ar">{ar}</th>', totals)

    def test_no_row_without_an_allocation_or_outside_tax_invoice_mode(self):
        self.assertIsNone(self._row(_go("tax", _build("tax"))))
        unallocated = _engine_doc("tax", basis="Net Total", doc_discount="20.00",
                                  lines=[("2", "100.00", None, "200.00")],
                                  totals=("180.00", "27.00", "207.00"))
        self.assertIsNone(self._row(_go("tax", unallocated)))
        for kind in ("neutral", "quote", "po"):
            with self.subTest(kind):
                self.assertIsNone(self._row(_go(kind, _engine_doc(kind, **_NET))))


class TestAdapterFollowsTheEngineDiscounts(unittest.TestCase):
    """Items 2 and 3 through ``sales_invoice_to_zatca_dict`` (the golden path's real adapter)."""

    @staticmethod
    def _invoice(*, basis, discount, alloc, net_line, totals, rate="100.00", list_rate="100.00",
                 item_discount="0.00", pct="0"):
        from types import SimpleNamespace
        import datetime
        import json as _json

        net_total, tax, grand = (Decimal(v) for v in totals)
        item = SimpleNamespace(
            item_code="ITEM-001", item_name="Office Desk Chair", custom_item_name_ar="كرسي مكتب",
            qty=2, price_list_rate=Decimal(list_rate), discount_percentage=Decimal(pct),
            discount_amount=Decimal(item_discount), rate=Decimal(rate),
            amount=Decimal(rate) * 2, net_amount=Decimal(net_line),
            distributed_discount_amount=Decimal(alloc),
            item_tax_rate=_json.dumps({"VAT 15%": 15.0}))
        return SimpleNamespace(
            name="ACC-SINV-2026-0010", company="Al-Noor Trading Est",
            company_address="ADDR-COMP-1", customer="CUST-GULF",
            customer_name="Gulf Enterprises LLC", customer_address="ADDR-CUST-1",
            posting_date=datetime.date(2026, 11, 17),
            posting_time=datetime.timedelta(hours=14, minutes=30),
            currency="SAR", is_pos=0, is_return=0, is_debit_note=0,
            apply_discount_on=basis, additional_discount_percentage=Decimal("10"),
            discount_amount=Decimal(discount), net_total=net_total,
            total_taxes_and_charges=tax, grand_total=grand,
            taxes=[SimpleNamespace(rate=15.0)], items=[item])

    def _renders(self, inv):
        from change_engine.print_formats import render_tax_invoice_html, sales_invoice_to_zatca_dict

        env = TestAdapterEmitsDiscountFields()._env()
        payload, mode = sales_invoice_to_zatca_dict(inv, frappe_module=env)
        self.assertEqual(mode, "zatca_sa")
        return payload, {
            "erp-007 zatca": render_tax_invoice_html(payload, mode="zatca_sa"),
            "erp-007 neutral": render_tax_invoice_html(payload, mode="neutral"),
            "branded zatca": render_branded_tax_invoice_html(payload, mode="zatca_sa"),
            "branded neutral": render_branded_tax_invoice_html(payload, mode="neutral"),
        }

    def _assert_same_totals_and_branded_add_up(self, renders, taxable, vat, grand):
        seen = set()
        for name, doc in renders.items():
            totals = _printed_totals(doc)
            seen.add((totals["Total Taxable Amount"], totals["Total VAT"], totals["Grand Total"]))
            if name.startswith("branded"):
                with self.subTest(document=name):
                    _assert_printed_numbers_add_up(self, doc, taxable=taxable, discount_row=None)
        self.assertEqual(seen, {(Decimal(taxable), Decimal(vat), Decimal(grand))})

    def test_a_ten_percent_grand_total_discount_renders_the_same_in_erp_007_and_branded(self):
        payload, renders = self._renders(self._invoice(
            basis="Grand Total", discount="23.00", alloc="20.00", net_line="180.00",
            totals=("180.00", "27.00", "207.00")))
        self.assertEqual((payload["totals"]["apply_discount_on"],
                          payload["totals"]["discount_amount"]), ("Grand Total", "23.00"))
        self._assert_same_totals_and_branded_add_up(renders, "180.00", "27.00", "207.00")
        self.assertEqual(_printed_totals(renders["branded zatca"])[_INFO_ROW_EN],
                         Decimal("20.00"))

    def test_the_net_total_variant(self):
        payload, renders = self._renders(self._invoice(
            basis="Net Total", discount="20.00", alloc="20.00", net_line="180.00",
            totals=("180.00", "27.00", "207.00")))
        self.assertEqual(payload["totals"]["apply_discount_on"], "Net Total")
        self._assert_same_totals_and_branded_add_up(renders, "180.00", "27.00", "207.00")

    def test_a_per_unit_item_discount_is_not_subtracted_twice(self):
        # qty 2, list 100.00, 10% item discount: rate 90.00, discount_amount 10.00 per unit,
        # amount 180.00; a 10% Net Total discount spreads 18.00: net 162.00, VAT 24.30.
        for basis, discount in (("Net Total", "18.00"), ("Grand Total", "20.70")):
            with self.subTest(basis):
                payload, renders = self._renders(self._invoice(
                    basis=basis, discount=discount, alloc="18.00", net_line="162.00",
                    totals=("162.00", "24.30", "186.30"), rate="90.00", item_discount="10.00",
                    pct="10"))
                line = payload["lines"][0]
                # The posted rate is the ZATCA item net price (BT-146); the item discount is
                # already in it, so the line carries no further discount of its own.
                self.assertEqual((line["quantity"], line["unit_price"], line["discount"],
                                  line["distributed_discount_amount"], line["line_net_amount"]),
                                 ("2", "90.00", "0.00", "18.00", "162.00"))
                self._assert_same_totals_and_branded_add_up(renders, "162.00", "24.30", "186.30")
                for name in ("branded zatca", "branded neutral"):
                    printed = _printed_lines(renders[name])[0]
                    self.assertEqual(
                        (printed["qty"], printed["price"], printed["discount"], printed["amount"]),
                        (Decimal("2"), Decimal("90.00"), Decimal("18.00"), Decimal("162.00")))

    def test_a_cash_or_non_trade_discount_reaches_the_check_and_is_refused(self):
        inv = self._invoice(basis="Grand Total", discount="23.00", alloc="0", net_line="200.00",
                            totals=("200.00", "30.00", "207.00"))
        inv.is_cash_or_non_trade_discount = 1
        from change_engine.print_formats import sales_invoice_to_zatca_dict

        env = TestAdapterEmitsDiscountFields()._env()
        payload, _ = sales_invoice_to_zatca_dict(inv, frappe_module=env)
        with self.assertRaisesRegex(ValueError, r"is_cash_or_non_trade_discount"):
            render_branded_tax_invoice_html(payload, mode="zatca_sa")


if __name__ == "__main__":
    unittest.main()
