#!/usr/bin/env python3
"""Build Quadrant mark, app icons and lockups into ../logo/. Python 3; stdlib only, plus fontTools when ORRERY_FONT_ALEXANDRIA (path to Alexandria-VF.ttf) is set, which outlines the wordmark. Name comes from ../brand.json.
Geometry: PDF p.4, 32-unit grid. Corner (5,27), r=22.5, lower sector 0-40 deg, slot 40-52, upper 52-90.
Angles are measured up from the horizontal baseline; SVG y points down so y = 27 - r*sin(a)."""
import json, math, os, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wordmark_outline
root = pathlib.Path(__file__).resolve().parent.parent
out = root / "logo"; out.mkdir(exist_ok=True)
name = json.loads((root / "brand.json").read_text(encoding="utf-8"))["name"]

CX, CY, R = 5.0, 27.0, 22.5
COBALT, COBALT_DARK, CARBON, CORAL, WHITE, CARBON_BG = "#2443D0", "#86A0FF", "#12151B", "#E0552C", "#FFFFFF", "#0E1117"
CHALK = "#E8EAEF"
BBOX = (5.0, 4.5, 27.5, 27.0)

def pt(a):
    r = math.radians(a)
    return CX + R * math.cos(r), CY - R * math.sin(r)

def f(v):
    return f"{v:.3f}".rstrip("0").rstrip(".")

def sector(a0, a1):
    x0, y0 = pt(a0); x1, y1 = pt(a1)
    # sweep-flag 0 = counter-clockwise on screen, i.e. angle increasing upward
    return f"M{f(CX)} {f(CY)}L{f(x0)} {f(y0)}A{f(R)} {f(R)} 0 0 0 {f(x1)} {f(y1)}Z"

LOWER, UPPER = sector(0, 40), sector(52, 90)

def svg(w, h, vb, body, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{f(w)}" height="{f(h)}" viewBox="{vb}" role="img">\n'
            f'<title>{title}</title>\n{body}\n</svg>\n')

def mark(fill, lower=None, upper=None, tf=""):
    g = f' transform="{tf}"' if tf else ""
    return f'<g{g}><path d="{LOWER}" fill="{lower or fill}"/><path d="{UPPER}" fill="{upper or fill}"/></g>'

def mark_file(fn, fill, **kw):
    pad = 1.0
    x, y = BBOX[0] - pad, BBOX[1] - pad
    w, h = BBOX[2] - BBOX[0] + 2 * pad, BBOX[3] - BBOX[1] + 2 * pad
    (out / fn).write_text(svg(w * 8, h * 8, f"{f(x)} {f(y)} {f(w)} {f(h)}", mark(fill, **kw), f"{name} mark"), encoding="utf-8")

mark_file("mark-primary.svg", COBALT)
mark_file("mark-dark.svg", COBALT_DARK)
mark_file("mark-mono.svg", CARBON)
mark_file("mark-reversed.svg", WHITE)
mark_file("mark-two-tone.svg", COBALT, lower=COBALT, upper=CORAL)

# App icon: 64 unit tile, mark width = 56% of tile, optically centred then nudged up and right.
T = 64.0; s = 0.56 * T / (BBOX[2] - BBOX[0])
NUDGE_X, NUDGE_Y = 1.5, -1.5   # INFERRED: PDF gives no value, only "nudged up and right"
RX = 14.0                      # INFERRED: PDF gives "rounded tile", no radius
mcx, mcy = (BBOX[0] + BBOX[2]) / 2, (BBOX[1] + BBOX[3]) / 2
tf = f"translate({f(T/2+NUDGE_X)} {f(T/2+NUDGE_Y)}) scale({f(s)}) translate({f(-mcx)} {f(-mcy)})"
for fn, tile, fill in (("app-icon.svg", COBALT, WHITE), ("app-icon-dark.svg", CARBON_BG, COBALT_DARK)):
    body = f'<rect width="{f(T)}" height="{f(T)}" rx="{f(RX)}" fill="{tile}"/>\n' + mark(fill, tf=tf)
    (out / fn).write_text(svg(512, 512, f"0 0 {f(T)} {f(T)}", body, f"{name} app icon"), encoding="utf-8")

# Lockup. X = cap height of the wordmark. Mark visible height = 1.4 X, gap = 0.6 X, clear space = 1 X.
MARK_H = BBOX[3] - BBOX[1]            # 22.5 units
X = MARK_H / 1.4
GAP = 0.6 * X
CAP_RATIO = 0.70                      # INFERRED: Alexandria cap height / em. Verify against the font file.
FONT_SIZE = X / CAP_RATIO
ADVANCE_X = 4.5 * X * len(name) / 6       # INFERRED from the PDF cover: "Orrery" is about 4.5 X wide
tx = BBOX[2] + GAP
left, right = BBOX[0] - X, tx + ADVANCE_X + X
top, bottom = BBOX[1] - X, CY + X
W, H = right - left, bottom - top
PLACEHOLDER = ("<!-- PLACEHOLDER: wordmark is live text, must be outlined from Alexandria SemiBold "
               "before any external use. Width and cap-height ratio are INFERRED. -->")
OUTLINED = "<!-- outlined from Alexandria SemiBold (SIL OFL 1.1) -->"
WM = wordmark_outline.build(name)      # None unless ORRERY_FONT_ALEXANDRIA points at the font file
if WM:
    # Measured: X = OS/2 sCapHeight (700/1000 em). Ink left edge sits GAP right of the quadrant; baseline = CY (quadrant flat edge).
    S = X / WM["cap"]
    ink_l, _, ink_r, _ = WM["bounds"]
    ox = BBOX[2] + GAP - ink_l * S
    WM_D = wordmark_outline.path_data(WM, S, ox, CY)
    right = BBOX[2] + GAP + (ink_r - ink_l) * S + X
    W = right - left

def lockup(fn, mark_fill, text_fill):
    vb = f"{f(left)} {f(top)} {f(W)} {f(H)}"
    if WM:
        body = OUTLINED + "\n" + mark(mark_fill) + "\n" + f'<path d="{WM_D}" fill="{text_fill}"/>'
        (out / fn).write_text(svg(W * 5, H * 5, vb, body, f"{name} lockup"), encoding="utf-8")
        return
    text = (f'<text x="{f(tx)}" y="{f(CY)}" font-family="Alexandria, sans-serif" font-weight="600" '
            f'font-size="{f(FONT_SIZE)}" letter-spacing="{f(FONT_SIZE*-0.005)}" fill="{text_fill}">{name}</text>')
    body = PLACEHOLDER + "\n" + mark(mark_fill) + "\n" + text
    (out / fn).write_text(svg(W * 5, H * 5, vb, body, f"{name} lockup"), encoding="utf-8")

lockup("lockup-primary.svg", COBALT, CARBON)
lockup("lockup-dark.svg", COBALT_DARK, CHALK)
print("name:", name, "| wordmark:", "outlined (cap height %s/%s em, kerning pairs %s)" % (WM["cap"], WM["upm"], WM["kern"]) if WM else "PLACEHOLDER live text (set ORRERY_FONT_ALEXANDRIA to outline)")
print("LOWER:", LOWER); print("UPPER:", UPPER)
print("files:", sorted(p.name for p in out.glob("*.svg")))
