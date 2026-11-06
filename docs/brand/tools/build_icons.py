#!/usr/bin/env python3
"""Render PNGs, favicon.ico and apple-touch-icon from the SVGs into ../logo/png/. Needs PyMuPDF ('fitz') for rendering; the ICO container is
written here (PNG-compressed entries, stdlib only). Python 3.9+. Run build_logo.py and build_logo_proposed.py first.
Small marks: 16 px uses logo/proposed/mark-16.svg and 32 px uses mark-32.svg (DRAFT, PROPOSED); other sizes use the v1 mark SVGs."""
import pathlib, struct, sys
root = pathlib.Path(__file__).resolve().parent.parent
logo, prop, out = root / "logo", root / "logo" / "proposed", root / "logo" / "png"
SIZES = [16, 32, 48, 64, 128, 180, 192, 256, 512, 1024]
COBALT, COBALT_DARK = "#2443D0", "#86A0FF"
try:
    import fitz
except ImportError:
    print("PyMuPDF (fitz) is not importable: PNG/ICO NOT generated. Install it (pip install pymupdf) and rerun."); sys.exit(2)

def render(svg_text, px):
    page = fitz.open(stream=svg_text.encode("utf-8"), filetype="svg")[0]
    z = px / page.rect.width
    return page.get_pixmap(matrix=fitz.Matrix(z, z), alpha=True).tobytes("png")

def mark_svg(size, dark):
    if size == 16:
        s = (prop / "mark-16.svg").read_text(encoding="utf-8")
    elif size == 32:
        s = (prop / "mark-32.svg").read_text(encoding="utf-8")
    else:
        return (logo / ("mark-dark.svg" if dark else "mark-primary.svg")).read_text(encoding="utf-8")
    return s.replace(COBALT, COBALT_DARK) if dark else s

out.mkdir(parents=True, exist_ok=True)
n = 0
for size in SIZES:
    for dark in (False, True):
        sfx = "-dark" if dark else ""
        (out / f"mark{sfx}-{size}.png").write_bytes(render(mark_svg(size, dark), size))
        (out / f"app-icon{sfx}-{size}.png").write_bytes(render((logo / f"app-icon{sfx}.svg").read_text(encoding="utf-8"), size)); n += 2

# favicon.ico: 16, 32 (hand-tuned DRAFT marks) and 48 (v1 mark), light mark on transparent. PNG-compressed entries.
entries = [(16, render(mark_svg(16, False), 16)), (32, render(mark_svg(32, False), 32)), (48, render(mark_svg(48, False), 48))]
head = struct.pack("<HHH", 0, 1, len(entries)); offset = 6 + 16 * len(entries); body = b""; table = b""
for px, data in entries:
    table += struct.pack("<BBBBHHII", px, px, 0, 0, 1, 32, len(data), offset + len(body)); body += data
(out / "favicon.ico").write_bytes(head + table + body)
# apple-touch-icon: full-bleed square (iOS applies its own mask), so the tile corner radius is removed
sq = (logo / "app-icon.svg").read_text(encoding="utf-8").replace('rx="14"', 'rx="0"')
(out / "apple-touch-icon.png").write_bytes(render(sq, 180))
print(f"wrote {n} PNGs, favicon.ico ({len(head + table + body)} bytes, sizes 16/32/48) and apple-touch-icon.png (180) to {out}")
