"""Locked page shell, stylesheet and layout verifier for branded documents (ERP-016).

ADR-0014: tenant branding may colour a document, never restructure it. The guarantee is built
from three parts, none of which trusts tenant input:

1. The only tenant-controlled output is the token block ``:root{--brand-primary:#rrggbb;
   --brand-accent:#rrggbb;}`` (colours validated upstream). Everything else in the stylesheet is
   the constant ``LOCKED_DOCUMENT_CSS``, which reads colour only through ``var(--...)`` tokens,
   fixes typography and status colours, and keeps the QR clear zone and logo limits.
2. Every legally required block carries ``data-locked-region="<name>"`` in a fixed order.
3. ``verify_locked_layout`` re-parses finished HTML and reports any deviation: a changed or extra
   stylesheet, a missing, duplicated or reordered region, a changed direction or language, a
   missing mandatory Arabic label, a QR without payload or clear zone, a logo outside the header,
   scripts, inline styles, event handlers, hidden elements or remote resources. Renderers call
   ``assert_locked_layout`` on their own output (defence in depth); the function is public so a
   custom or stored template can be checked before it is ever used.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from html.parser import HTMLParser
import re

from .document_labels import ALL_LABELS
from .document_tokens import document_tokens

# Every colour and the font come from the token source (``document_tokens``); print-only neutrals
# that are not brand tokens use the closest existing light token (ADR-0014, no new tokens here).
# The constants below are resolved on first use so importing this module never needs the file.


def print_surfaces() -> tuple[str, ...]:
    """Surfaces the primary and accent are contrast-checked against: surface, panel, subtle panel."""
    t = document_tokens()
    return (t.surface, t.background, t.surface)


def status_tokens() -> dict[str, str]:
    """Status colours are fixed (ADR-0014); always shown with an icon and a label."""
    t = document_tokens()
    return {"success": t.success, "warning": t.warning, "danger": t.danger}


def default_primary() -> str:
    return document_tokens().primary


_TOKEN_BLOCK_RE = re.compile(
    r":root\{--brand-primary:#[0-9a-f]{6};--brand-accent:#[0-9a-f]{6};\}"
)
_LOGO_SRC_RE = re.compile(r"^data:image/(png|jpeg|svg\+xml);base64,[A-Za-z0-9+/=]+$")
_SVG_NS = "http://www.w3.org/2000/svg"


def render_token_block(primary_hex: str, accent_hex: str) -> str:
    """The single tenant-controlled stylesheet fragment; inputs must already be validated hex."""
    block = f":root{{--brand-primary:{primary_hex.lower()};--brand-accent:{accent_hex.lower()};}}"
    if not _TOKEN_BLOCK_RE.fullmatch(block):
        raise ValueError("Brand token block is malformed")
    return block


def _fixed_root() -> str:
    t = document_tokens()
    return f"""\
:root {{
  --doc-surface: {t.surface};
  --doc-panel: {t.background};
  --doc-panel-subtle: {t.surface};
  --doc-text: {t.text};
  --doc-text-secondary: {t.text};
  --doc-text-muted: {t.text};
  --doc-border: {t.background};
  --doc-border-soft: {t.background};
  --status-success: {t.success};
  --status-warning: {t.warning};
  --status-danger: {t.danger};
  --font-doc: {t.font_stack};
}}
"""


_RULES = """\
@page {
  size: A4 portrait;
  margin: 14mm 14mm 16mm 14mm;
}
* { box-sizing: border-box; }
html, body {
  margin: 0;
  padding: 0;
  background: var(--doc-surface);
  color: var(--doc-text);
  font-family: var(--font-doc);
  font-size: 9.5pt;
  line-height: 1.45;
  direction: rtl;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}
bdi { unicode-bidi: isolate; direction: ltr; }
bdi[dir="rtl"] { direction: rtl; }
[data-locked-region] {
  visibility: visible !important;
  opacity: 1 !important;
  transform: none !important;
  position: static !important;
  clip-path: none !important;
  overflow: visible !important;
  float: none !important;
}
.document-page { width: 100%; max-width: 182mm; margin: 0 auto; background: var(--doc-surface); }
.top-header {
  display: table; width: 100%;
  border-bottom: 2px solid var(--brand-primary);
  padding-bottom: 4mm; margin-bottom: 4.5mm;
}
.header-start, .header-end { display: table-cell; vertical-align: middle; }
.header-start { width: 55%; text-align: right; padding-left: 5mm; }
.header-end { width: 45%; text-align: left; direction: ltr; }
.brand-logo-wrap { margin-bottom: 2mm; }
.brand-logo {
  min-height: 8mm; max-height: 16mm; max-width: 60mm;
  width: auto; height: auto; display: inline-block;
}
.brand-logo.logo-mono { filter: grayscale(100%) contrast(120%); }
.brand-name { font-size: 11pt; font-weight: 700; color: var(--brand-primary); margin-bottom: 1.5mm; }
.doc-title-row {
  display: table; width: 100%; margin-bottom: 1mm;
  border-bottom: 0.8mm solid var(--brand-accent);
}
.doc-title-ar, .doc-title-en {
  display: table-cell; width: 50%; font-size: 14pt; font-weight: 700; color: var(--brand-primary);
}
.doc-title-ar { text-align: right; }
.doc-title-en { text-align: left; direction: ltr; }
.doc-badge-row { display: table; width: 100%; font-size: 9pt; font-weight: 600; color: var(--doc-text-secondary); }
.doc-badge-row .bi-ar { display: table-cell; text-align: right; }
.doc-badge-row .bi-en { display: table-cell; text-align: left; direction: ltr; }
.bi-row { display: table; width: 100%; }
.bi-ar, .bi-en { display: table-cell; width: 50%; font-size: 9.5pt; font-weight: 600; vertical-align: top; }
.bi-ar { text-align: right; padding-left: 2mm; }
.bi-en { text-align: left; direction: ltr; padding-right: 2mm; }
.party-name .bi-ar, .party-name .bi-en {
  font-size: 10pt; font-weight: 700; color: var(--doc-text); margin-bottom: 1.5mm;
}
.detail-row {
  display: table; width: 100%; margin-top: 1mm;
  font-size: 9pt; font-weight: 400; color: var(--doc-text-secondary);
}
.detail-row .bi-ar, .detail-row .bi-en { font-size: 9pt; font-weight: 400; }
.meta-table { width: 100%; border-collapse: collapse; margin-bottom: 4.5mm; border: 1px solid var(--doc-border); }
.meta-table th, .meta-table td { padding: 1.8mm 2.5mm; border-bottom: 1px solid var(--doc-border-soft); font-size: 9.2pt; }
.meta-label-ar { width: 30%; text-align: right; font-weight: 600; background: var(--doc-panel-subtle); color: var(--brand-primary); }
.meta-value { width: 40%; text-align: center; font-weight: 600; color: var(--doc-text); }
.meta-label-en { width: 30%; text-align: left; direction: ltr; font-weight: 600; background: var(--doc-panel-subtle); color: var(--brand-primary); }
.parties-grid { display: table; width: 100%; table-layout: fixed; border-spacing: 3mm 0; margin: 0 -3mm 4.5mm -3mm; }
.party-col { display: table-cell; width: 50%; vertical-align: top; }
.party-card { border: 1px solid var(--doc-border); border-radius: 1.5mm; background: var(--doc-surface); break-inside: avoid; }
.card-header {
  display: table; width: 100%; background: var(--doc-panel);
  border-bottom: 1.5px solid var(--brand-primary); padding: 2mm 2.5mm; color: var(--brand-primary);
}
.card-body { padding: 2.5mm; }
.muted { color: var(--doc-text-muted); }
.adjustment-box {
  border: 1px solid var(--brand-primary); background: var(--doc-panel-subtle);
  padding: 2.5mm 3mm; margin-bottom: 4.5mm; break-inside: avoid;
}
.delivery-box { border: 1px solid var(--doc-border); background: var(--doc-surface); margin-bottom: 4.5mm; break-inside: avoid; }
.lines-table { width: 100%; border-collapse: collapse; margin-bottom: 5mm; }
.lines-table th {
  background: var(--doc-panel); color: var(--brand-primary);
  border-top: 1.5px solid var(--brand-primary); border-bottom: 1.5px solid var(--brand-primary);
  border-left: 1px solid var(--doc-border-soft); border-right: 1px solid var(--doc-border-soft);
  padding: 2mm 1.5mm; text-align: center; font-size: 8.8pt; font-weight: 700;
}
.th-ar, .th-en { font-size: 8.8pt; font-weight: 700; }
.th-en { direction: ltr; }
.lines-table td { border: 1px solid var(--doc-border-soft); padding: 2mm 1.5mm; vertical-align: top; font-size: 9pt; }
.num-col { text-align: center; white-space: nowrap; }
.code-col { text-align: center; white-space: nowrap; font-weight: 600; }
.desc-col { text-align: right; }
.item-desc-ar { font-weight: 600; color: var(--doc-text); }
.item-desc-en { direction: ltr; text-align: left; font-weight: 500; color: var(--doc-text-secondary); }
.item-exemption { font-size: 8.2pt; color: var(--doc-text-muted); margin-top: 0.8mm; }
.cat-col { text-align: center; font-size: 8.5pt; }
.cat-ar, .cat-en { display: block; }
.cat-en { direction: ltr; }
.summary-section { display: table; width: 100%; margin-top: 3mm; break-inside: avoid; }
.summary-totals-cell { display: table-cell; width: 58%; vertical-align: top; padding-left: 4mm; }
.summary-totals-cell.summary-wide { width: 100%; padding-left: 0; }
.summary-qr-cell { display: table-cell; width: 42%; vertical-align: top; text-align: center; }
.totals-table { width: 100%; border-collapse: collapse; border: 1px solid var(--doc-border); }
.totals-table th, .totals-table td { padding: 2.2mm 2.5mm; border-bottom: 1px solid var(--doc-border-soft); font-size: 9.5pt; }
.tot-ar { text-align: right; font-weight: 600; width: 34%; }
.tot-val { text-align: center; font-weight: 700; width: 32%; white-space: nowrap; }
.tot-en { text-align: left; direction: ltr; font-weight: 600; width: 34%; }
.grand-row th, .grand-row td {
  background: var(--doc-panel); border-top: 1.5px solid var(--brand-primary);
  border-bottom: 1.5px solid var(--brand-primary); color: var(--brand-primary);
  font-size: 10.5pt; font-weight: 700;
}
.qr-panel { display: block; width: 100%; text-align: center; break-inside: avoid; }
.qr-clear-zone { display: inline-block; background: var(--doc-surface); padding: 4.5mm; border: 1px solid var(--doc-border); margin: 0; }
.qr-clear-zone svg { display: block; }
.qr-caption { max-width: 72mm; margin: 1.5mm auto 0 auto; font-size: 8.5pt; color: var(--doc-text-secondary); }
.notes-box, .terms-box { margin-top: 4mm; padding: 2.5mm 3mm; border: 1px solid var(--doc-border-soft); background: var(--doc-surface); }
.notes-body, .terms-body { margin-top: 1mm; font-size: 9pt; color: var(--doc-text-secondary); }
.terms-body div { margin-top: 0.8mm; }
.terms-body div, .notes-body { unicode-bidi: plaintext; }
.status-pill {
  display: inline-block; margin-top: 1.5mm; padding: 0.6mm 2.2mm; font-size: 9pt; font-weight: 700;
  border: 1px solid currentColor; border-radius: 1mm; background: var(--doc-surface);
}
.status-icon { display: inline-block; margin-left: 1.2mm; font-weight: 700; }
.status-warning { color: var(--status-warning); }
.status-success { color: var(--status-success); }
.status-danger { color: var(--status-danger); }
.doc-footer {
  margin-top: 6mm; padding-top: 2.5mm; border-top: 1px solid var(--doc-border);
  display: table; width: 100%; font-size: 8.5pt; color: var(--doc-text-muted);
}
.footer-ref { display: table-cell; text-align: right; }
.footer-brand { display: table-cell; text-align: left; direction: ltr; }
"""


@lru_cache(maxsize=1)
def locked_document_css() -> str:
    return _fixed_root() + _RULES


_LAZY = {
    "LOCKED_DOCUMENT_CSS": locked_document_css,
    "PRINT_SURFACES": print_surfaces,
    "STATUS_TOKENS": status_tokens,
    "DEFAULT_PRIMARY": default_primary,
}


def __getattr__(name: str):  # PEP 562: the constants load the token file on first access
    if name in _LAZY:
        return _LAZY[name]()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def render_document_shell(*, kind: str, title_html: str, token_block: str, body_html: str) -> str:
    """Wrap region markup in the locked page shell. ``title_html`` must already be escaped."""
    return (
        "<!DOCTYPE html>\n"
        '<html lang="ar" dir="rtl">\n'
        "<head>\n"
        '<meta charset="utf-8"/>\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1"/>\n'
        f"<title>{title_html}</title>\n"
        f"<style>{token_block}\n{locked_document_css()}</style>\n"
        "</head>\n"
        '<body dir="rtl">\n'
        f'<div class="document-page" data-document-kind="{kind}">\n'
        f"{body_html}\n"
        "</div>\n"
        "</body>\n"
        "</html>"
    )


# ----------------------------------------------------------------------------- verification
class LockedLayoutViolation(ValueError):
    """The finished document deviates from the locked compliance layout."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def _ar(*keys: str) -> tuple[str, ...]:
    return tuple(ALL_LABELS[k][0] for k in keys)


_LINE_LABELS = ("item_code", "description", "quantity", "unit_price", "discount", "vat_rate",
                "line_amount")
_TOTAL_LABELS = ("total_taxable_amount", "total_vat_amount", "grand_total")


@dataclass(frozen=True)
class _Spec:
    regions: tuple[str, ...]
    labels: dict[str, tuple[str, ...]]


def _tax_spec(zatca: bool, qr: bool, standard: bool = False) -> _Spec:
    """ZATCA mode also needs the issue time; a standard (B2B) invoice the buyer's VAT number and
    address (round 6, UNVERIFIED against the ZATCA rules)."""
    regions = ("header", "seller", "buyer", "lines", "totals") + (("qr",) if qr else ()) + (
        "footer",)
    labels = {
        "header": _ar("invoice_number", "issue_date", "currency")
        + (_ar("issue_time") if zatca else ()),
        "seller": _ar("seller") + (_ar("vat_number") if zatca else ()),
        "buyer": _ar("customer") + (_ar("vat_number", "address") if standard else ()),
        "lines": _ar(*_LINE_LABELS, "vat_category"),
        "totals": _ar(*_TOTAL_LABELS),
    }
    if qr:
        labels["qr"] = _ar("qr_caption")
    return _Spec(regions, labels)


DOCUMENT_KINDS: dict[str, _Spec] = {
    "tax_invoice_zatca_sa_standard": _tax_spec(True, True, standard=True),
    "tax_invoice_zatca_sa_simplified": _tax_spec(True, True),
    "tax_invoice_neutral": _tax_spec(False, False),
    "tax_invoice_neutral_qr": _tax_spec(False, True),
    "quote": _Spec(
        ("header", "seller", "buyer", "lines", "totals", "terms", "footer"),
        {
            "header": _ar("quote_number", "issue_date", "valid_until", "currency"),
            "seller": _ar("seller"),
            "buyer": _ar("customer"),
            "lines": _ar(*_LINE_LABELS),
            "totals": _ar(*_TOTAL_LABELS),
            "terms": _ar("terms"),
        },
    ),
    "purchase_order": _Spec(
        ("header", "buyer", "supplier", "delivery", "lines", "totals", "terms", "footer"),
        {
            "header": _ar("po_number", "issue_date", "required_by", "currency"),
            "buyer": _ar("buyer"),
            "supplier": _ar("supplier"),
            "delivery": _ar("delivery_address"),
            "lines": _ar(*_LINE_LABELS),
            "totals": _ar(*_TOTAL_LABELS),
            "terms": _ar("terms"),
        },
    ),
}

_VOID_TAGS = frozenset({"meta", "link", "img", "br", "hr", "input", "base", "col", "area",
                        "source", "track", "wbr", "embed", "param"})
_FORBIDDEN_TAGS = frozenset({
    "script", "link", "iframe", "frame", "frameset", "object", "embed", "applet", "base", "form",
    "input", "button", "textarea", "select", "audio", "video", "canvas", "noscript", "template",
    "image", "use", "a", "foreignobject", "animate", "set", "animatetransform", "animatemotion",
    "handler", "listener",
})
_FORBIDDEN_ATTRS = frozenset({"style", "hidden", "srcdoc", "href", "xlink:href", "formaction",
                              "background", "poster", "ping", "contenteditable"})


# CMP-005 prints the secondary Hijri date in the header meta table as one row: Arabic label,
# value cell, English label. Only that cell, and only on tax invoices, may carry these two
# isolates (founder decision on ERP-016): the Arabic month name runs right to left, the English
# one left to right. Every other direction or language override stays refused.
_HIJRI_BDI_FORMS = (("rtl", "ar"), ("ltr", "en"))


def _hijri_cell_isolates(nodes: list["_Node"], kind: str, problems: list[str]) -> set["_Node"]:
    """The ``<bdi>`` nodes allowed to override direction or language (empty when none)."""
    ar_label, en_label = ALL_LABELS["hijri_date"]
    cells = []
    for row in nodes:
        cols = row.children
        if row.tag != "tr" or [c.tag for c in cols] != ["th", "td", "th"]:
            continue
        if cols[0].content().strip() != ar_label or cols[2].content().strip() != en_label:
            continue
        in_meta = row.inside(lambda p: p.tag == "table"
                             and "meta-table" in p.attrs.get("class", "").split())
        in_header = row.inside(lambda p: p.attrs.get("data-locked-region") == "header")
        if in_meta and in_header and cols[1].attrs.get("class") == "meta-value":
            cells.append(cols[1])
    if len(cells) > 1:
        problems.append("duplicated Hijri date row")
    if len(cells) != 1 or not kind.startswith("tax_invoice"):
        return set()
    allowed: set[_Node] = set()
    for form in _HIJRI_BDI_FORMS:
        for child in cells[0].children:
            if child.tag == "bdi" and (child.attrs.get("dir"), child.attrs.get("lang")) == form:
                allowed.add(child)  # the first of each form only; a second one is refused
                break
    return allowed


class _Node:
    __slots__ = ("tag", "attrs", "children", "parent", "text")

    def __init__(self, tag: str, attrs: dict[str, str], parent: "_Node | None") -> None:
        self.tag = tag
        self.attrs = attrs
        self.children: list[_Node] = []
        self.parent = parent
        self.text: list[str] = []

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()

    def content(self) -> str:
        return "".join(self.text) + "".join(c.content() for c in self.children)

    def inside(self, predicate) -> bool:
        node = self.parent
        while node is not None:
            if predicate(node):
                return True
            node = node.parent
        return False


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root", {}, None)
        self.cur = self.root
        self.problems: list[str] = []

    def _make(self, tag: str, attrs: list[tuple[str, str | None]]) -> _Node:
        names = [name for name, _ in attrs]
        if len(set(names)) != len(names):
            self.problems.append(f"duplicate attribute on <{tag}>")
        node = _Node(tag, {k: (v or "") for k, v in attrs}, self.cur)
        self.cur.children.append(node)
        return node

    def handle_starttag(self, tag, attrs):
        node = self._make(tag, attrs)
        if tag not in _VOID_TAGS:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        self._make(tag, attrs)

    def handle_endtag(self, tag):
        node = self.cur
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self.cur = node.parent

    def handle_data(self, data):
        self.cur.text.append(data)


def verify_locked_layout(document_html: str, kind: str) -> list[str]:
    """Return every deviation from the locked layout for ``kind`` (empty means compliant)."""
    spec = DOCUMENT_KINDS.get(kind)
    if spec is None:
        raise ValueError(f"Unknown document kind '{kind}'; expected one of {sorted(DOCUMENT_KINDS)}")
    try:
        return _verify(document_html, kind, spec)
    except RecursionError:  # hostile nesting depth: fail closed
        return ["document is nested too deeply to verify"]


def _verify(document_html: str, kind: str, spec: _Spec) -> list[str]:
    problems: list[str] = []
    if not isinstance(document_html, str) or not document_html.startswith("<!DOCTYPE html>"):
        problems.append("document must start with the HTML5 doctype")
        if not isinstance(document_html, str):
            return problems
    builder = _TreeBuilder()
    try:
        builder.feed(document_html)
        builder.close()
    except Exception as exc:  # parser errors fail closed
        return problems + [f"document could not be parsed: {exc}"]
    problems += builder.problems
    nodes = list(builder.root.walk())[1:]

    html_nodes = [n for n in nodes if n.tag == "html"]
    body_nodes = [n for n in nodes if n.tag == "body"]
    if len(html_nodes) != 1 or html_nodes[0].attrs.get("lang") != "ar" \
            or html_nodes[0].attrs.get("dir") != "rtl":
        problems.append('<html> must be exactly lang="ar" dir="rtl"')
    if len(body_nodes) != 1 or body_nodes[0].attrs.get("dir") != "rtl":
        problems.append('<body> must have dir="rtl"')

    styles = [n for n in nodes if n.tag == "style"]
    if len(styles) != 1:
        problems.append("exactly one locked <style> block is allowed")
    else:
        token, _, rest = styles[0].content().partition("\n")
        if not _TOKEN_BLOCK_RE.fullmatch(token):
            problems.append("tenant token block is not the allowed brand colour tokens")
        if rest != locked_document_css():
            problems.append("stylesheet differs from the locked document stylesheet")

    hijri_isolates = _hijri_cell_isolates(nodes, kind, problems)
    imgs: list[_Node] = []
    for node in nodes:
        if node.tag in _FORBIDDEN_TAGS:
            problems.append(f"forbidden element <{node.tag}>")
        if node.tag == "meta" and set(node.attrs) - {"charset", "name", "content"}:
            problems.append("forbidden <meta> attributes")
        if node.tag == "img":
            imgs.append(node)
        for name, value in node.attrs.items():
            lowered = value.strip().lower()
            if name.startswith("on") or name in _FORBIDDEN_ATTRS:
                problems.append(f"forbidden attribute '{name}' on <{node.tag}>")
            if name == "src" and node.tag != "img":
                problems.append(f"forbidden attribute 'src' on <{node.tag}>")
            if name == "dir" and node.tag not in ("html", "body", "bdi"):
                problems.append(f"direction override on <{node.tag}>")
            if name == "dir" and node.tag == "bdi" and value != "ltr" \
                    and node not in hijri_isolates:
                problems.append("<bdi> must stay dir=\"ltr\"")
            if name == "lang" and node.tag != "html" and node not in hijri_isolates:
                problems.append(f"language override on <{node.tag}>")
            if "javascript:" in lowered or "vbscript:" in lowered:
                problems.append(f"script URL in '{name}'")
            if "://" in lowered or lowered.startswith("//"):
                if not (node.tag == "svg" and name == "xmlns" and value == _SVG_NS):
                    problems.append(f"remote resource reference in '{name}'")

    found = [n for n in nodes if "data-locked-region" in n.attrs]
    names = [n.attrs["data-locked-region"] for n in found]
    for expected in spec.regions:
        if names.count(expected) == 0:
            problems.append(f"missing locked region '{expected}'")
        elif names.count(expected) > 1:
            problems.append(f"duplicated locked region '{expected}'")
    for name in names:
        if name not in spec.regions:
            problems.append(f"unexpected locked region '{name}'")
    if all(names.count(r) == 1 for r in spec.regions) and \
            [n for n in names if n in spec.regions] != list(spec.regions):
        problems.append("locked regions are out of order")
    by_name = {n.attrs["data-locked-region"]: n for n in found}
    for region, needed in spec.labels.items():
        node = by_name.get(region)
        if node is None:
            continue
        text = node.content()
        for label in needed:
            if label not in text:
                problems.append(f"region '{region}' lacks the mandatory Arabic label '{label}'")

    markers = [n.attrs["data-document-kind"] for n in nodes if "data-document-kind" in n.attrs]
    if markers != [kind]:
        problems.append("document kind marker does not match the expected kind")

    header = by_name.get("header")
    if len(imgs) > 1:
        problems.append("at most one logo image is allowed")
    for img in imgs:
        in_header = header is not None and img.inside(lambda p: p is header)
        if not in_header or "brand-logo" not in img.attrs.get("class", "").split():
            problems.append("logo image must be the brand logo inside the header region")
        if not _LOGO_SRC_RE.fullmatch(img.attrs.get("src", "")):
            problems.append("logo image must be an embedded PNG, JPEG or SVG data URI")

    if "qr" in spec.regions and "qr" in by_name:
        qr = by_name["qr"]
        svgs = [n for n in qr.walk() if n.tag == "svg" and n.attrs.get("data-zatca-tlv")]
        if len(svgs) != 1:
            problems.append("QR region must contain one QR code with its TLV payload")
        elif not svgs[0].inside(lambda p: "qr-clear-zone" in p.attrs.get("class", "").split()):
            problems.append("QR code must sit inside the clear zone")
        if any(n.tag == "img" for n in qr.walk()):
            problems.append("nothing may overlap the QR clear zone")
    return problems


def assert_locked_layout(document_html: str, kind: str) -> None:
    problems = verify_locked_layout(document_html, kind)
    if problems:
        raise LockedLayoutViolation(problems)
