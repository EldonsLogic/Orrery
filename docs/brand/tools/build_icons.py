#!/usr/bin/env python3
"""Render PNGs, favicon.ico, apple-touch-icon and the maskable PWA icon from the SVGs in ../logo/ into ../logo/png/.
Stdlib only, deterministic: a small exact-coverage rasteriser for the flat shapes build_logo.py writes (rect with
optional rx; path with M, L, A, Z), 4 sub-rows per pixel with exact horizontal coverage, and its own fixed-Huffman deflate.

  uv run --no-project --python 3.12 python3 tools/build_icons.py           write
  uv run --no-project --python 3.12 python3 tools/build_icons.py --check   exit 1 if a committed file differs

Pinned toolchain: CPython 3.12 (uv-managed); no PyMuPDF, MuPDF, Pillow or zlib compression, so the bytes depend only on
IEEE double arithmetic and the platform libm (math.cos, math.sin, math.atan2) for the arc points.
Run build_logo.py first. Marks below 24 px and the favicon use the small-size cut (logo/mark-small*.svg), per 02-logo.md."""
import math, pathlib, re, struct, sys, zlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOGO, OUT = ROOT / "logo", ROOT / "logo" / "png"
SIZES = [16, 32, 48, 64, 128, 180, 192, 256, 512, 1024]
SUB = 4                      # sub-rows per pixel
NUM = r"-?\d+(?:\.\d+)?"

# ---------- SVG subset ----------
def parse(svg):
    vb = [float(v) for v in re.search(r'viewBox="([^"]+)"', svg).group(1).split()]
    layers = []
    for m in re.finditer(r"<(rect|path)\b([^>]*)/>", svg):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(2)))
        if m.group(1) == "rect":
            polys = [rounded_rect(float(a.get("x", 0)), float(a.get("y", 0)), float(a["width"]), float(a["height"]), float(a.get("rx", 0)))]
        else:
            polys = path_polys(a["d"])
        layers.append((a["fill"], polys))
    return vb, layers

def arc_points(cx, cy, r, a0, a1):
    n = max(8, math.ceil(abs(a1 - a0) * r / 0.25))   # chord step at most about 0.25 user units
    return [(cx + r * math.cos(a0 + (a1 - a0) * i / n), cy + r * math.sin(a0 + (a1 - a0) * i / n)) for i in range(1, n + 1)]

def rounded_rect(x, y, w, h, r):
    if r <= 0:
        return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    p = []
    for cx, cy, a0 in [(x + w - r, y + r, -math.pi / 2), (x + w - r, y + h - r, 0), (x + r, y + h - r, math.pi / 2), (x + r, y + r, math.pi)]:
        p += [(cx + r * math.cos(a0), cy + r * math.sin(a0))] + arc_points(cx, cy, r, a0, a0 + math.pi / 2)
    return p

def path_polys(d):
    toks = re.findall(r"[MLAZ]|" + NUM, d)
    polys, cur, i = [], [], 0
    while i < len(toks):
        c = toks[i]; i += 1
        if c in "ML":
            pt = (float(toks[i]), float(toks[i + 1])); i += 2
            if c == "M" and cur:
                polys.append(cur)
            cur = [pt] if c == "M" else cur + [pt]
        elif c == "A":   # circular arc only (rx = ry, no rotation): the shapes build_logo.py writes
            r, _, _, large, sweep, x2, y2 = [float(t) for t in toks[i:i + 7]]; i += 7
            (x1, y1) = cur[-1]
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            dx, dy = (x2 - x1) / 2, (y2 - y1) / 2
            dd = math.hypot(dx, dy); r = max(r, dd)
            k = math.sqrt(max(0.0, r * r - dd * dd)) / dd
            sgn = -1 if large == sweep else 1
            cx, cy = mx + sgn * k * -dy, my + sgn * k * dx
            a0, a1 = math.atan2(y1 - cy, x1 - cx), math.atan2(y2 - cy, x2 - cx)
            if sweep and a1 <= a0: a1 += 2 * math.pi
            if not sweep and a1 >= a0: a1 -= 2 * math.pi
            cur += arc_points(cx, cy, r, a0, a1)
        elif c == "Z":
            if cur: polys.append(cur)
            cur = []
    if cur: polys.append(cur)
    return polys

# ---------- rasteriser ----------
def coverage(polys, s, w, h):
    """Alpha bytes (w*h) for the polygons scaled by s, nonzero winding, exact horizontal coverage, SUB sub-rows."""
    edges = []
    for p in polys:
        for (x0, y0), (x1, y1) in zip(p, p[1:] + p[:1]):
            if y0 != y1:
                edges.append((x0 * s, y0 * s, x1 * s, y1 * s))
    out = bytearray(w * h)
    for py in range(h):
        diff = [0.0] * (w + 2)
        for j in range(SUB):
            sy = py + (j + 0.5) / SUB
            xs = []
            for x0, y0, x1, y1 in edges:
                if (y0 <= sy < y1) or (y1 <= sy < y0):
                    xs.append((x0 + (sy - y0) * (x1 - x0) / (y1 - y0), 1 if y1 > y0 else -1))
            xs.sort()
            wind = 0
            for k, (x, dirn) in enumerate(xs):
                prev, wind = wind, wind + dirn
                if prev == 0 and wind != 0:
                    a = x
                elif prev != 0 and wind == 0:
                    b = x
                    a2, b2 = min(max(a, 0.0), w), min(max(b, 0.0), w)
                    if b2 <= a2: continue
                    ia, ib = int(a2), int(b2)
                    if ia == ib:
                        diff[ia] += b2 - a2; diff[ia + 1] -= b2 - a2
                    else:
                        diff[ia] += ia + 1 - a2; diff[ia + 1] -= ia + 1 - a2
                        diff[ia + 1] += 1; diff[ib] -= 1
                        if ib < w: diff[ib] += b2 - ib; diff[ib + 1] -= b2 - ib
        acc, base = 0.0, py * w
        for x in range(w):
            acc += diff[x]
            out[base + x] = min(255, max(0, round(acc / SUB * 255)))
    return out

def hexrgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))

def render(name, px):
    (vx, vy, vw, vh), layers = parse((LOGO / name).read_text(encoding="utf-8"))
    s, w, h = px / vw, px, round(vh * px / vw)
    rgba = bytearray(w * h * 4)   # straight alpha, composited "over" in layer order
    for fill, polys in layers:
        r, g, b = hexrgb(fill)
        al = coverage([[(x - vx, y - vy) for x, y in p] for p in polys], s, w, h)
        for i, a in enumerate(al):
            if not a: continue
            o = i * 4; da = rgba[o + 3]
            if a == 255 or not da:
                rgba[o:o + 4] = bytes((r, g, b, a)); continue
            oa = a + da * (255 - a) / 255
            for c, sc in enumerate((r, g, b)):
                rgba[o + c] = round((sc * a + rgba[o + c] * da * (255 - a) / 255) / oa)
            rgba[o + 3] = round(oa)
    return png(w, h, rgba)

# ---------- deterministic deflate (fixed Huffman, matches at distance 4 only) ----------
# Written here so PNG bytes do not depend on the zlib build (zlib is used only for crc32 and adler32).
LEN_BASE = [3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35, 43, 51, 59, 67, 83, 99, 115, 131, 163, 195, 227, 258]
LEN_EXTRA = [0] * 8 + [1] * 4 + [2] * 4 + [3] * 4 + [4] * 4 + [5] * 4 + [0]

def rev(code, n):
    return int(format(code, f"0{n}b")[::-1], 2)

def lit_code(v):
    if v < 144: return rev(0x30 + v, 8), 8
    if v < 256: return rev(0x190 + v - 144, 9), 9
    if v < 280: return rev(v - 256, 7), 7
    return rev(0xC0 + v - 280, 8), 8

LIT = [lit_code(v) for v in range(288)]
LEN = {}
for L in range(3, 259):
    i = 28 if L == 258 else max(k for k in range(28) if LEN_BASE[k] <= L)
    c, n = LIT[257 + i]
    LEN[L] = (c | ((L - LEN_BASE[i]) << n), n + LEN_EXTRA[i])
DIST4 = (rev(3, 5), 5)   # distance 4: code 3, no extra bits

def deflate(data):
    acc, nb, out = 0, 0, bytearray()
    def put(code, n):
        nonlocal acc, nb
        acc |= code << nb; nb += n
        while nb >= 8:
            out.append(acc & 255); acc >>= 8; nb -= 8
    put(1, 1); put(1, 2)              # final block, fixed Huffman
    i, n = 0, len(data)
    while i < n:
        if i >= 4:
            if i + 258 <= n and data[i:i + 258] == data[i - 4:i + 254]:
                put(*LEN[258]); put(*DIST4); i += 258; continue
            L = 0
            while L < 258 and i + L < n and data[i + L] == data[i + L - 4]:
                L += 1
            if L >= 3:
                put(*LEN[L]); put(*DIST4); i += L; continue
        put(*LIT[data[i]]); i += 1
    put(*LIT[256])
    if nb: out.append(acc & 255)
    return bytes(out)

def png(w, h, rgba):
    raw = b"".join(b"\x00" + bytes(rgba[y * w * 4:(y + 1) * w * 4]) for y in range(h))
    z = b"\x78\x01" + deflate(raw) + struct.pack(">I", zlib.adler32(raw) & 0xFFFFFFFF)
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + chunk(b"IDAT", z) + chunk(b"IEND", b"")

def mark_svg(size, dark):
    base = "mark-small" if size < 24 else ("mark" if dark else "mark-primary")
    return f"{base}{'-dark' if dark else ''}.svg"

def build():
    files = {}
    for size in SIZES:
        for dark in (False, True):
            sfx = "-dark" if dark else ""
            files[f"mark{sfx}-{size}.png"] = render(mark_svg(size, dark), size)
            files[f"app-icon{sfx}-{size}.png"] = render(f"app-icon{sfx}.svg", size)
    # favicon.ico: 16, 32 and 48 px, small-size cut, Cobalt on transparent. PNG-compressed entries.
    entries = [(px, render("mark-small.svg", px)) for px in (16, 32, 48)]
    head = struct.pack("<HHH", 0, 1, len(entries)); offset = 6 + 16 * len(entries); body = b""; table = b""
    for px, data in entries:
        table += struct.pack("<BBBBHHII", px, px, 0, 0, 1, 32, len(data), offset + len(body)); body += data
    files["favicon.ico"] = head + table + body
    # apple-touch-icon: full-bleed square (iOS applies its own mask). Maskable: full bleed, mark inside the safe circle.
    files["apple-touch-icon.png"] = render("app-icon-square.svg", 180)
    files["maskable-512.png"] = render("app-icon-maskable.svg", 512)
    return files

def main(argv):
    files = build()
    if "--check" in argv:
        bad = [n for n, data in files.items() if not (OUT / n).is_file() or (OUT / n).read_bytes() != data]
        if bad:
            print(f"differs: {', '.join(bad)}"); return 1
        print(f"icons up to date ({len(files)} files)"); return 0
    OUT.mkdir(parents=True, exist_ok=True)
    for n, data in files.items():
        (OUT / n).write_bytes(data)
    print(f"wrote {len(files)} files to logo/png"); return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
