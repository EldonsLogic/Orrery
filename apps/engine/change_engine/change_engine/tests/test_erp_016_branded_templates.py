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
                lambda d: d.pop("typography"),
            ):
                broken = json.loads(json.dumps(good))
                mutate(broken)
                with self.subTest(mutate=mutate), self.assertRaises(DocumentTokenError):
                    load_document_tokens(written(tmp, broken))

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

    def test_computed_amount_rounds_half_even_to_two_places_like_the_totals_check(self):
        # 3 x 33.335 = 100.005 -> 100.00 (half-even, the quantize used for printed amounts)
        data = self._quote(quantity="3", unit_price="33.335", line_total="100.00")
        data["totals"] = {"total_taxable_amount": "100.00", "total_vat_amount": "15.00",
                          "grand_total": "115.00"}
        self.assertIn("100.00", render_branded_quote_html(data))
        data["lines"][0]["line_total"] = "100.01"
        with self.assertRaisesRegex(ValueError, r"Line 1.*line_total"):
            render_branded_quote_html(data)

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


if __name__ == "__main__":
    unittest.main()
