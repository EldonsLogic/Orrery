#!/usr/bin/env python3
"""Build the Seshna logo set (Nuqta S mark, Cairo Bold wordmark) into ../logo/. ADR-0066, BRD-014.
Adapted from the Seshna logo kit's build_kit.py (draft v3); see PROVENANCE.md in this folder.

  python3 tools/build_logo.py                                   marks and app icons only (stdlib)
  SESHNA_FONT_CAIRO=/path/to/Cairo-VF.ttf \\
    uv run --no-project --with fonttools --with uharfbuzz python3 tools/build_logo.py   also wordmark and lockups

Without SESHNA_FONT_CAIRO the wordmark and lockup files are left untouched (never replaced by live text).
The name comes from ../brand.json and is written in Latin letters only. Output: flat paths, no live text,
transforms, clip paths or external references (SEC-018 section 6)."""
import json, math, os, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "logo"; OUT.mkdir(exist_ok=True)
NAME = json.loads((ROOT / "brand.json").read_text(encoding="utf-8"))["name"]
WGHT, TRACKING, FAMILY = 700.0, -0.005, "Cairo"

# Seshna palette (tokens.json, v1). Coral is never used in the logo.
COBALT, COBALT_D = "#2443D0", "#86A0FF"
CARBON, CHALK_TXT = "#12151B", "#E8EAEF"
BG_D, WHITE, BLACK = "#0E1117", "#FFFFFF", "#000000"
fmt = lambda v: f"{v:.2f}".rstrip("0").rstrip(".") or "0"

# ---------- mark: Nuqta S ----------
# Local frame: a square of half side s (the Nuqta diamond before turning), cut horizontally by a gap g.
# Each half is a bar; the top bar's left end and the bottom bar's right end are half circles (radius = half the bar height).
# The frame is turned -45 deg so the cut runs at the pen angle, lower left to upper right.
C45 = math.sqrt(0.5)
def turn(x, y):
    return (C45 * (x + y), C45 * (y - x))

def mark_geometry(gap, half_diag=112.0):
    s = half_diag * C45
    h = s - gap / 2; r = h / 2
    top = [("M", (-s + r, -s)), ("L", (s, -s)), ("L", (s, -gap / 2)), ("L", (-s + r, -gap / 2)), ("A", (-s + r, -s))]
    bot = [("M", (s - r, s)), ("L", (-s, s)), ("L", (-s, gap / 2)), ("L", (s - r, gap / 2)), ("A", (s - r, s))]
    pts = []  # bounds (turned): sample the outline including the arcs
    for cx, cy, sign in [(-s + r, -s + r, -1), (s - r, s - r, 1)]:
        for i in range(181):
            t = math.radians(90 + 180 * i / 180) if sign < 0 else math.radians(-90 + 180 * i / 180)
            pts.append(turn(cx + r * math.cos(t), cy + r * math.sin(t)))
    for shape in (top, bot):
        pts += [turn(*p) for _, p in shape]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return dict(top=top, bot=bot, r=r, bounds=(min(xs), min(ys), max(xs), max(ys)))

def mark_path(gap, box_h, ox, oy, half_diag=112.0):
    """Path for the mark scaled so its height is box_h, with its bounding box's top-left at (ox, oy)."""
    G = mark_geometry(gap, half_diag)
    x0, y0, x1, y1 = G["bounds"]
    k = box_h / (y1 - y0)
    def P(p):
        x, y = turn(*p)
        return f"{fmt(ox + (x - x0) * k)} {fmt(oy + (y - y0) * k)}"
    out = []
    for shape in (G["top"], G["bot"]):
        d = ""
        for cmd, p in shape:
            d += (f"A{fmt(G['r'] * k)} {fmt(G['r'] * k)} 0 0 1 {P(p)} Z " if cmd == "A" else f"{cmd}{P(p)} ")
        out.append(d.strip())
    return " ".join(out), (x1 - x0) * k

def centred(gap, box, hgt):
    _, w = mark_path(gap, hgt, 0, 0)
    return mark_path(gap, hgt, (box - w) / 2, (box - hgt) / 2)[0]

MASTER_GAP, SMALL_GAP = 18, 30   # small-size cut below 24 px

def svg(w, h, body, title, comment=""):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {fmt(w)} {fmt(h)}" width="{fmt(w)}" height="{fmt(h)}">\n'
            f'  <title>{title}</title>\n{comment}{body}\n</svg>\n')

def write(name, text):
    (OUT / name).write_text(text, encoding="utf-8"); print("wrote", name)

# symbol on a 256 square, centred, height 224 (master) or 240 (small cut)
for fn, col, gap, hgt, label in [
    ("mark-primary.svg", COBALT, MASTER_GAP, 224, "-"), ("mark-dark.svg", COBALT_D, MASTER_GAP, 224, "-dark"),
    ("mark-small.svg", COBALT, SMALL_GAP, 240, "-"), ("mark-small-dark.svg", COBALT_D, SMALL_GAP, 240, "-dark"),
    ("mark-mono.svg", BLACK, MASTER_GAP, 224, " one colour black"), ("mark-reversed.svg", WHITE, MASTER_GAP, 224, " one colour white"),
]:
    tag = "" if label == "-" else label
    kind = "small-size cut" if gap == SMALL_GAP else "master"
    write(fn, svg(256, 256, f'  <path fill="{col}" d="{centred(gap, 256, hgt)}"/>', f"{NAME} mark{tag} ({kind})"))

# App icons on a 64-unit tile, small-size cut (they render small), mark height 62% of the tile, centred.
# app-icon: rounded tile (rx 14, about 22%); square: full bleed for apple-touch-icon (iOS masks it);
# maskable: full bleed, mark height 50% so it stays inside the 80% safe circle.
T = 64
for fn, tile, glyph, rx, share in [
    ("app-icon.svg", COBALT, WHITE, 14, 0.62), ("app-icon-dark.svg", BG_D, COBALT_D, 14, 0.62),
    ("app-icon-square.svg", COBALT, WHITE, 0, 0.62), ("app-icon-maskable.svg", COBALT, WHITE, 0, 0.5),
]:
    rect = f'  <rect width="{T}" height="{T}" rx="{rx}" fill="{tile}"/>\n' if rx else f'  <rect width="{T}" height="{T}" fill="{tile}"/>\n'
    write(fn, svg(T, T, rect + f'  <path fill="{glyph}" d="{centred(SMALL_GAP, T, share * T)}"/>', f"{NAME} app icon"))

# ---------- wordmark and lockups (need the Cairo variable font) ----------
FONT = os.environ.get("SESHNA_FONT_CAIRO")
if not FONT:
    print("SESHNA_FONT_CAIRO not set: wordmark and lockups NOT rebuilt (existing files kept).")
    raise SystemExit(0)

import uharfbuzz as hb
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.boundsPen import BoundsPen

src = TTFont(FONT)
axes = {ax.axisTag: ax.defaultValue for ax in src["fvar"].axes} if "fvar" in src else {}
axes["wght"] = WGHT
if "slnt" in axes: axes["slnt"] = 0
inst = instancer.instantiateVariableFont(src, axes)
upm, cap = inst["head"].unitsPerEm, inst["OS/2"].sCapHeight
hfont = hb.Font(hb.Face(hb.Blob.from_file_path(FONT))); hfont.set_variations(axes)
buf = hb.Buffer(); buf.add_str(NAME); buf.guess_segment_properties()
hb.shape(hfont, buf, {"kern": True})
gs, order = inst.getGlyphSet(), inst.getGlyphOrder()
x, placed, n = 0.0, [], len(buf.glyph_infos)
for i, (info, pos) in enumerate(zip(buf.glyph_infos, buf.glyph_positions)):
    placed.append((order[info.codepoint], x + pos.x_offset, pos.y_offset))
    x += pos.x_advance + (TRACKING * upm if i < n - 1 else 0)
bp = BoundsPen(gs)
for g, gx, gy in placed:
    gs[g].draw(TransformPen(bp, (1, 0, 0, 1, gx, gy)))
xmin, ymin, xmax, ymax = bp.bounds

CAP_PX = 100.0
s = CAP_PX / cap
wm_w, asc_px, desc_px = (xmax - xmin) * s, ymax * s, max(0.0, -ymin * s)
NOTE = (f"  <!-- Wordmark outlined from {FAMILY} (wght {int(WGHT)}), SIL OFL 1.1; tracking {TRACKING * 100:g}% em, "
        f"kerning via HarfBuzz. Latin only: the name is never written in Arabic script. -->\n")

def wordmark(ox, base_y, fill):
    sp = SVGPathPen(gs, ntos=lambda v: f"{v:.2f}".rstrip("0").rstrip(".") or "0")
    for g, gx, gy in placed:
        gs[g].draw(TransformPen(sp, (s, 0, 0, -s, ox + (gx - xmin) * s, base_y - gy * s)))
    return f'  <path fill="{fill}" d="{sp.getCommands()}"/>'

for fn, tag, col in [("wordmark.svg", "", CARBON), ("wordmark-dark.svg", "-dark", CHALK_TXT)]:
    write(fn, svg(wm_w, asc_px + desc_px, wordmark(0, asc_px, col), f"{NAME} wordmark{tag}", NOTE))

PAD = CAP_PX  # clear space on panel versions: one cap height on every side
def panel(W, H, body, bg):
    return f'  <rect width="{fmt(W + 2 * PAD)}" height="{fmt(H + 2 * PAD)}" fill="{bg}"/>\n' + body

# Horizontal: mark height 1.6 x cap height, centred on the middle of the cap height; gap 0.6 x cap height.
MARK_H, GAP = 1.6 * CAP_PX, 0.6 * CAP_PX
for fn, variant, mf, wf, bg in [("lockup-primary.svg", "primary", COBALT, CARBON, None), ("lockup-dark.svg", "dark", COBALT_D, CHALK_TXT, BG_D),
                                ("lockup-on-cobalt.svg", "on-cobalt", WHITE, WHITE, COBALT)]:
    off = PAD if bg else 0.0
    top = max(0.0, asc_px - (MARK_H / 2 + CAP_PX / 2))
    base = top + MARK_H / 2 + CAP_PX / 2
    md, mw = mark_path(MASTER_GAP, MARK_H, off, off + top)
    W, H = mw + GAP + wm_w, max(top + MARK_H, base + desc_px)
    body = f'  <path fill="{mf}" d="{md}"/>\n' + wordmark(off + mw + GAP, off + base, wf)
    title = f"{NAME} lockup, horizontal, {variant}"
    write(fn, svg(W + 2 * PAD, H + 2 * PAD, panel(W, H, body, bg), title, NOTE) if bg else svg(W, H, body, title, NOTE))

# Stacked: mark height 2.2 x cap height, gap 0.6 x cap height.
SMH, SGAP = 2.2 * CAP_PX, 0.6 * CAP_PX
for fn, variant, mf, wf, bg in [("lockup-stacked-primary.svg", "primary", COBALT, CARBON, None), ("lockup-stacked-dark.svg", "dark", COBALT_D, CHALK_TXT, BG_D)]:
    off = PAD if bg else 0.0
    _, mw = mark_path(MASTER_GAP, SMH, 0, 0)
    SW = max(mw, wm_w)
    md, _ = mark_path(MASTER_GAP, SMH, off + (SW - mw) / 2, off)
    sbase = SMH + SGAP + asc_px; SH = sbase + desc_px
    body = f'  <path fill="{mf}" d="{md}"/>\n' + wordmark(off + (SW - wm_w) / 2, off + sbase, wf)
    title = f"{NAME} lockup, stacked, {variant}"
    write(fn, svg(SW + 2 * PAD, SH + 2 * PAD, panel(SW, SH, body, bg), title, NOTE) if bg else svg(SW, SH, body, title, NOTE))
print(f"{FAMILY} {int(WGHT)}: cap={cap} wordmark_w={wm_w:.1f}")
