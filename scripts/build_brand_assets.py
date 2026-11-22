#!/usr/bin/env python3
"""BRD-007: brand asset pipeline (stdlib only, deterministic).

Reads the generated source logos in docs/brand/logo/ and the colour tokens, and writes
docs/brand/logo/assets/: light and auto-derived dark variants of the mark, lockup and
app icon, plus a size set (width/height only; the viewBox is kept). Colours come from
tokens.json by role, never typed here. Output obeys docs/security/brand-asset-upload-security.md
section 6 (no script, style, image, foreignObject, external reference or DOCTYPE).

  python3 scripts/build_brand_assets.py          write outputs
  python3 scripts/build_brand_assets.py --check  exit 1 if committed outputs differ (CI)
Raster export (PNG, ICO) stays in docs/brand/tools/build_icons.py (needs PyMuPDF).
"""
import copy
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "docs" / "brand"
SRC = BRAND / "logo"
OUT = SRC / "assets"
TOKENS = BRAND / "tokens" / "tokens.json"

# source file -> (output stem, per-mode role remap applied before resolving the colour)
FAMILIES = {
    "mark-primary.svg": ("mark", {"light": {}, "dark": {}}),
    "lockup-primary.svg": ("lockup", {"light": {}, "dark": {}}),
    # light tile is primary with a surface glyph; dark tile is the dark background with a primary glyph
    "app-icon.svg": ("app-icon", {"light": {}, "dark": {"primary": "background", "surface": "primary"}}),
}
MARK_SIZES = (16, 24, 32, 48, 64, 128, 180, 192, 256, 512)   # square, px
LOCKUP_WIDTHS = (80, 160, 320, 640)                          # px; 80 is the minimum lockup width
SVG_NS = "http://www.w3.org/2000/svg"
ALLOWED = {"g", "defs", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "title", "desc"}  # below the root
DRAWABLE = {"path", "rect", "circle", "ellipse", "line", "polyline", "polygon"}
TEXT_OK = {"title", "desc"}
ALLOWED_ATTR = {"width", "height", "viewBox", "role", "d", "fill", "transform", "rx", "x", "y", "cx", "cy", "r"}
# SEC-018 BAU-033: C0/C1 controls (except tab, LF, CR), null, bidi marks and controls
BAD_CHARS = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u200e\u200f\u202a-\u202e\u2066-\u2069]")
# SEC-018 BAU-036, BAU-038: checked on decoded, whitespace-stripped, case-folded values
BAD_VALUE = ("javascript:", "vbscript:", "data:", "url(", "@import", "expression(", "href", "http", "//")
HEX = re.compile(r"#[0-9A-Fa-f]{6}")


def fail(name, why):
    raise SystemExit(f"{name}: {why}")


def roles(tokens):
    """hex (upper) -> role for the light palette, and role -> hex per mode."""
    col = tokens["color"]
    by_mode = {m: {r: v["hex"].upper() for r, v in col[m].items()} for m in ("light", "dark")}
    return {h: r for r, h in by_mode["light"].items()}, by_mode


def viewbox(name, root):
    """BAU-034: four finite numbers with a positive width and height, else fail closed."""
    try:
        vb = [float(x) for x in root.get("viewBox", "").replace(",", " ").split()]
    except ValueError:
        vb = []
    if len(vb) != 4 or not all(math.isfinite(v) for v in vb) or vb[2] <= 0 or vb[3] <= 0:
        fail(name, "missing or invalid viewBox")
    return vb


def load(name, text):
    """Parse and check against SEC-018 section 6; reject (never strip) anything outside the allow-list."""
    if not isinstance(text, str) or BAD_CHARS.search(text):
        fail(name, "control or bidi character")
    decl = re.match(r"\s*<\?xml\s([^?]*)\?>", text)
    if decl and re.search(r"encoding", decl.group(1)) and not re.search(r"encoding\s*=\s*[\"']utf-8[\"']", decl.group(1), re.I):
        fail(name, "encoding must be UTF-8")
    if "<?" in text[decl.end() if decl else 0:] or re.search(r"<!(?!--)", text):
        fail(name, "processing instruction, DOCTYPE, ENTITY or CDATA not allowed")
    try:
        root = ET.fromstring(text)   # comments are dropped by the parser (BAU-031)
    except ET.ParseError as e:
        fail(name, f"not well-formed XML ({e})")
    if root.tag != f"{{{SVG_NS}}}svg":
        fail(name, "root must be <svg> in the SVG namespace")
    drawable = False
    for el in root.iter():
        ns, _, tag = el.tag.rpartition("}")
        if ns != "{" + SVG_NS or (el is not root and tag not in ALLOWED):
            fail(name, f"element <{el.tag}> not allowed")
        drawable = drawable or tag in DRAWABLE
        if (el.text or "").strip() and tag not in TEXT_OK or (el.tail or "").strip():
            fail(name, f"text not allowed in <{tag}>")
        for a, v in el.attrib.items():
            if a not in ALLOWED_ATTR:
                fail(name, f"attribute {a} not allowed")
            folded = re.sub(r"\s", "", v).casefold()
            if any(b in folded for b in BAD_VALUE):
                fail(name, f"forbidden value in {a}")
        if any(BAD_CHARS.search(v) for v in (el.text or "", *el.attrib.values())):
            fail(name, "control or bidi character")
    if not drawable:
        fail(name, "nothing drawable")
    viewbox(name, root)
    return root


def serialise(root):
    """BAU-032: write the checked tree with a fixed namespace and layout; input text is never copied."""
    def esc(v):
        for a, b in (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"), ('"', "&quot;"),
                     ("\t", "&#9;"), ("\n", "&#10;"), ("\r", "&#13;")):
            v = v.replace(a, b)
        return v

    def node(el, top):
        tag = el.tag.rpartition("}")[2]
        attrs = (f' xmlns="{SVG_NS}"' if top else "") + "".join(f' {k}="{esc(v)}"' for k, v in el.attrib.items())
        sep = "\n" if top else ""
        inner = esc(el.text or "") if tag in TEXT_OK else "".join(sep + node(c, False) for c in el)
        return f"<{tag}{attrs}>{inner}{sep}</{tag}>" if inner else f"<{tag}{attrs}/>"
    return node(root, True) + "\n"


def derive(root, mode, remap, hex_role, by_mode):
    """Copy of the tree with every fill mapped to the mode's token; any other colour aborts."""
    root = copy.deepcopy(root)

    def walk(el, inherited):
        tag = el.tag.rpartition("}")[2]
        if "fill" in el.attrib:
            h = el.get("fill").strip()
            if not HEX.fullmatch(h) or h.upper() not in hex_role:
                fail(tag, f"fill {h!r} is not a light token colour; extend tokens, not this script")
            el.set("fill", by_mode[mode][remap.get(hex_role[h.upper()], hex_role[h.upper()])])
            inherited = True
        if tag in DRAWABLE and not inherited:
            fail(tag, "drawable without a token fill (the default would be black)")
        for c in el:
            walk(c, inherited)
    walk(root, False)
    return root


def resize(root, w, h):
    root = copy.deepcopy(root)
    root.set("width", str(w))
    root.set("height", str(h))
    return root


def validate(name, svg, palette=None):
    """SEC-018 section 6 on an output: allow-list, token fills only, canonical re-serialisation."""
    root = load(name, svg)
    palette = palette if palette is not None else token_hexes()
    for el in root.iter():
        if "fill" in el.attrib and el.get("fill") not in palette:
            fail(name, f"fill {el.get('fill')} is not a token colour")
    if serialise(root) != svg:
        fail(name, "not the canonical serialisation of its own tree")


def token_hexes():
    _, by_mode = roles(json.loads(TOKENS.read_text(encoding="utf-8")))
    return {h for m in by_mode.values() for h in m.values()}


def build():
    tokens = json.loads(TOKENS.read_text(encoding="utf-8"))
    hex_role, by_mode = roles(tokens)
    files = {}
    for src, (stem, remaps) in FAMILIES.items():
        source = load(src, (SRC / src).read_bytes().decode("utf-8"))   # strict UTF-8 (BAU-033)
        for mode in ("light", "dark"):
            variant = derive(source, mode, remaps[mode], hex_role, by_mode)
            suffix = "" if mode == "light" else "-dark"
            sizes = [(f"-w{w}", w, None) for w in LOCKUP_WIDTHS] if stem == "lockup" else [(f"-{s}", s, s) for s in MARK_SIZES]
            files[f"{stem}{suffix}.svg"] = serialise(variant)
            vb = viewbox(src, variant)
            for tag, w, h in sizes:
                height = h if h else round(w * vb[3] / vb[2], 3)
                files[f"{stem}{suffix}{tag}.svg"] = serialise(resize(variant, w, f"{height:g}"))
    palette = {h for m in by_mode.values() for h in m.values()}
    for n, s in files.items():
        validate(n, s, palette)
    return files


def main(argv):
    files = build()
    shown = OUT.relative_to(ROOT) if str(OUT).startswith(str(ROOT)) else OUT
    extra = sorted(p.name for p in OUT.iterdir() if p.name not in files) if OUT.exists() else []
    if "--check" in argv:
        bad = [n for n, s in files.items() if not (OUT / n).is_file() or (OUT / n).read_text(encoding="utf-8") != s]
        if bad or extra:
            print("brand assets out of date, run scripts/build_brand_assets.py:", ", ".join(sorted(bad + extra)))
            return 1
        print(f"brand assets up to date ({len(files)} files)")
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    for n in extra:   # the folder is generated: anything not built here is stale
        if not (OUT / n).is_file():
            fail(str(shown), f"unexpected entry {n}; remove it by hand")
        (OUT / n).unlink()
        print(f"removed stale {n}")
    for n, s in files.items():
        (OUT / n).write_text(s, encoding="utf-8")
    print(f"wrote {len(files)} files to {shown}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
