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
import json
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
ALLOWED = {"svg", "g", "defs", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "title", "desc"}
ALLOWED_ATTR = {"xmlns", "width", "height", "viewBox", "role", "d", "fill", "transform", "rx", "x", "y", "cx", "cy", "r"}
HEX = re.compile(r"fill=\"(#[0-9A-Fa-f]{6})\"")


def roles(tokens):
    """hex (upper) -> role for the light palette, and role -> hex per mode."""
    col = tokens["color"]
    by_mode = {m: {r: v["hex"].upper() for r, v in col[m].items()} for m in ("light", "dark")}
    return {h: r for r, h in by_mode["light"].items()}, by_mode


def derive(svg, mode, remap, hex_role, by_mode):
    def sub(m):
        h = m.group(1).upper()
        if h not in hex_role:
            raise SystemExit(f"fill {h} is not a light token colour; extend tokens, not this script")
        role = remap.get(hex_role[h], hex_role[h])
        return f'fill="{by_mode[mode][role]}"'
    return HEX.sub(sub, svg)


def resize(svg, w, h):
    head, rest = svg.split(">", 1)
    head = re.sub(r'width="[^"]*"', f'width="{w}"', head, 1)
    head = re.sub(r'height="[^"]*"', f'height="{h}"', head, 1)
    return head + ">" + rest


def validate(name, svg):
    """SEC-018 section 6: static, no active content, no external references."""
    if re.search(r"<!(DOCTYPE|ENTITY)|<\?(?!xml )|javascript:|https?://(?!www\.w3\.org/2000/svg)|url\(|href", svg, re.I):
        raise SystemExit(f"{name}: forbidden content")
    root = ET.fromstring(svg)
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag not in ALLOWED:
            raise SystemExit(f"{name}: element <{tag}> not allowed")
        for a in el.attrib:
            if a not in ALLOWED_ATTR:
                raise SystemExit(f"{name}: attribute {a} not allowed")


def build():
    tokens = json.loads(TOKENS.read_text(encoding="utf-8"))
    hex_role, by_mode = roles(tokens)
    files = {}
    for src, (stem, remaps) in FAMILIES.items():
        text = (SRC / src).read_text(encoding="utf-8")
        for mode in ("light", "dark"):
            variant = derive(text, mode, remaps[mode], hex_role, by_mode)
            suffix = "" if mode == "light" else "-dark"
            sizes = [(f"-w{w}", w, None) for w in LOCKUP_WIDTHS] if stem == "lockup" else [(f"-{s}", s, s) for s in MARK_SIZES]
            files[f"{stem}{suffix}.svg"] = variant
            vb = [float(x) for x in re.search(r'viewBox="([^"]+)"', variant).group(1).split()]
            for tag, w, h in sizes:
                height = h if h else round(w * vb[3] / vb[2], 3)
                files[f"{stem}{suffix}{tag}.svg"] = resize(variant, w, f"{height:g}")
    for n, s in files.items():
        validate(n, s)
    return files


def main(argv):
    files = build()
    if "--check" in argv:
        bad = [n for n, s in files.items() if not (OUT / n).exists() or (OUT / n).read_text(encoding="utf-8") != s]
        bad += [p.name for p in OUT.glob("*.svg") if p.name not in files] if OUT.exists() else []
        if bad:
            print("brand assets out of date, run scripts/build_brand_assets.py:", ", ".join(sorted(bad)))
            return 1
        print(f"brand assets up to date ({len(files)} files)")
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    for n, s in files.items():
        (OUT / n).write_text(s, encoding="utf-8")
    print(f"wrote {len(files)} files to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
