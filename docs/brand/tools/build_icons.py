#!/usr/bin/env python3
"""Render PNGs, favicon.ico, apple-touch-icon and the maskable PWA icon from the SVGs in ../logo/ into ../logo/png/.
Needs PyMuPDF ('fitz') for rendering; the ICO container is written here (PNG-compressed entries, stdlib only). Python 3.9+.
Run build_logo.py first:  uv run --no-project --with pymupdf python3 tools/build_icons.py
Marks below 24 px and the favicon use the small-size cut (logo/mark-small*.svg), per 02-logo.md."""
import pathlib, struct, sys
root = pathlib.Path(__file__).resolve().parent.parent
logo, out = root / "logo", root / "logo" / "png"
SIZES = [16, 32, 48, 64, 128, 180, 192, 256, 512, 1024]
try:
    import fitz
except ImportError:
    print("PyMuPDF (fitz) is not importable: PNG/ICO NOT generated. Run with: uv run --no-project --with pymupdf python3 tools/build_icons.py"); sys.exit(2)

def render(svg_name, px):
    page = fitz.open(stream=(logo / svg_name).read_bytes(), filetype="svg")[0]
    z = px / page.rect.width
    return page.get_pixmap(matrix=fitz.Matrix(z, z), alpha=True).tobytes("png")

def mark_svg(size, dark):
    base = "mark-small" if size < 24 else ("mark" if dark else "mark-primary")
    return f"{base}{'-dark' if dark else ''}.svg"

out.mkdir(parents=True, exist_ok=True)
n = 0
for size in SIZES:
    for dark in (False, True):
        sfx = "-dark" if dark else ""
        (out / f"mark{sfx}-{size}.png").write_bytes(render(mark_svg(size, dark), size))
        (out / f"app-icon{sfx}-{size}.png").write_bytes(render(f"app-icon{sfx}.svg", size)); n += 2

# favicon.ico: 16, 32 and 48 px, small-size cut, Cobalt on transparent. PNG-compressed entries.
entries = [(px, render("mark-small.svg", px)) for px in (16, 32, 48)]
head = struct.pack("<HHH", 0, 1, len(entries)); offset = 6 + 16 * len(entries); body = b""; table = b""
for px, data in entries:
    table += struct.pack("<BBBBHHII", px, px, 0, 0, 1, 32, len(data), offset + len(body)); body += data
(out / "favicon.ico").write_bytes(head + table + body)
# apple-touch-icon: full-bleed square (iOS applies its own mask). Maskable: full bleed, mark inside the safe circle.
(out / "apple-touch-icon.png").write_bytes(render("app-icon-square.svg", 180))
(out / "maskable-512.png").write_bytes(render("app-icon-maskable.svg", 512))
print(f"wrote {n} PNGs, favicon.ico ({len(head + table + body)} bytes, 16/32/48), apple-touch-icon.png (180) and maskable-512.png to {out}")
