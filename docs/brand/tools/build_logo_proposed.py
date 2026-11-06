#!/usr/bin/env python3
"""DRAFT small-size marks (16 and 32 px) and stacked lockup into ../logo/proposed/. PROPOSED, needs a designer's eye.
Usage: build_logo_proposed.py [--verify]   (--verify renders with PyMuPDF 'fitz' and measures the sighting slot)
Python 3.9+. Geometry from docs/brand/02-logo.md: lower sector 0-40 deg, slot 40-52 (axis 46), upper sector 52-90."""
import json, math, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wordmark_outline
root = pathlib.Path(__file__).resolve().parent.parent
out = root / "logo" / "proposed"; out.mkdir(parents=True, exist_ok=True)
name = json.loads((root / "brand.json").read_text(encoding="utf-8"))["name"]
COBALT, CARBON = "#2443D0", "#12151B"
AXIS, HALF = 46.0, 6.0

def f(v):
    return f"{v:.3f}".rstrip("0").rstrip(".")

def small_mark_paths(cx, cy, R, w):
    """Quarter disc with corner (cx,cy) on the pixel grid, integer radius R. The v1 12-degree wedge slot is kept, but near the corner it is
    replaced by a parallel-sided channel of constant width w (px) so the slot never narrows below w."""
    th = math.radians(AXIS)
    q = w / (2 * math.sin(math.radians(HALF)))            # distance along the slot edge rays where the wedge is w wide
    def ray(a, d):
        a = math.radians(a); return cx + d * math.cos(a), cy - d * math.sin(a)
    lx, ly = cx + (w / 2) / math.sin(th), cy               # lower sector apex, on the baseline
    ux, uy = cx, cy - (w / 2) / math.cos(th)               # upper sector apex, on the left edge
    q40, q52 = ray(40, q), ray(52, q)
    e40, e52 = ray(40, R), ray(52, R)
    lower = f"M{f(lx)} {f(ly)}L{f(q40[0])} {f(q40[1])}L{f(e40[0])} {f(e40[1])}A{R} {R} 0 0 1 {f(cx + R)} {f(cy)}Z"
    upper = f"M{f(ux)} {f(uy)}L{f(q52[0])} {f(q52[1])}L{f(e52[0])} {f(e52[1])}A{R} {R} 0 0 0 {f(cx)} {f(cy - R)}Z"
    return lower, upper

SPEC = {16: dict(cx=0, cy=16, R=16, w=1.5), 32: dict(cx=1, cy=31, R=30, w=2.0)}

def small_mark(px):
    s = SPEC[px]; lo, up = small_mark_paths(s["cx"], s["cy"], s["R"], s["w"])
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{px}" height="{px}" viewBox="0 0 {px} {px}" role="img">\n<title>{name} mark {px}</title>\n'
            f'<!-- DRAFT, PROPOSED. Pixel-snapped: corner ({s["cx"]},{s["cy"]}) and radius {s["R"]} are integers. Slot: v1 12 degree wedge outside, '
            f'parallel channel {s["w"]} px wide near the corner. Needs a designer\'s review. -->\n'
            f'<path d="{lo}" fill="{COBALT}"/><path d="{up}" fill="{COBALT}"/>\n</svg>\n')

for px in SPEC:
    (out / f"mark-{px}.svg").write_text(small_mark(px), encoding="utf-8")

# ---- stacked lockup (DRAFT). Mark in v1 mark units (corner 5,27 r 22.5). X = wordmark cap height. ----
LOWER = "M5 27L27.5 27A22.5 22.5 0 0 0 22.236 12.537Z"; UPPER = "M5 27L18.852 9.27A22.5 22.5 0 0 0 5 4.5Z"
MARK_H = 22.5; X = MARK_H / 2.8                  # mark visible height 2.8 X (twice the horizontal lockup's 1.4 X)
GAP = 0.6 * X                                    # v1 gap value reused: flat edge to wordmark cap top
CAP = 0.70                                       # placeholder-mode cap-height ratio (matches the measured OS/2 sCapHeight 700/1000)
base = 27 + GAP + X                              # wordmark baseline
fs = X / CAP; adv = 4.5 * X * len(name) / 6      # INFERRED width 4.5 X
left, right, top, bottom = 5 - X, 5 + adv + X, 4.5 - X, base + X
W, H = right - left, bottom - top
WM = wordmark_outline.build(name)      # None unless ORRERY_FONT_ALEXANDRIA points at Alexandria-VF.ttf
RULE = (f'Rule: quadrant flat edge sits {f(GAP)} units (0.6 X, the v1 gap) above the wordmark cap top; wordmark start-aligned with the quadrant\'s left edge; '
        f'mark height 2.8 X; clear space 1 X. Never mirrored in RTL.')
if WM:
    S = X / WM["cap"]                      # X = measured OS/2 sCapHeight
    ink_l, _, ink_r, _ = WM["bounds"]
    d = wordmark_outline.path_data(WM, S, 5 - ink_l * S, base)   # ink left edge on the quadrant's left edge
    right = 5 + (ink_r - ink_l) * S + X
    W = right - left
    word = f'<path d="{d}" fill="{CARBON}"/>'
    note = f'<!-- DRAFT, PROPOSED. {RULE} -->\n<!-- outlined from Alexandria SemiBold (SIL OFL 1.1) -->\n'
else:
    word = (f'<text x="5" y="{f(base)}" font-family="Alexandria, sans-serif" font-weight="600" font-size="{f(fs)}" letter-spacing="{f(fs * -0.005)}" fill="{CARBON}">{name}</text>')
    note = f'<!-- DRAFT, PROPOSED. {RULE} PLACEHOLDER: wordmark is live text, must be outlined from Alexandria SemiBold (set ORRERY_FONT_ALEXANDRIA to the font file and rebuild). -->\n'
stacked = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{f(W * 5)}" height="{f(H * 5)}" viewBox="{f(left)} {f(top)} {f(W)} {f(H)}" role="img">\n<title>{name} stacked lockup</title>\n'
           f'{note}<path d="{LOWER}" fill="{COBALT}"/><path d="{UPPER}" fill="{COBALT}"/>\n{word}\n</svg>\n')
(out / "lockup-stacked.svg").write_text(stacked, encoding="utf-8")
print("wrote", sorted(p.name for p in out.glob("*.svg")))

# ---- verification ----
def v1_slot_width_px(r_px):
    return 2 * r_px * math.tan(math.radians(HALF))

def verify():
    try:
        import fitz
    except ImportError:
        print("fitz not importable: verification NOT run. Manual check: open the SVGs at 16 and 32 px at 100% zoom and confirm the slot is a visible gap along its full length."); return 0
    th = math.radians(AXIS); u = (math.cos(th), -math.sin(th)); n = (math.sin(th), math.cos(th))
    bad = 0
    for px in SPEC:
        s = SPEC[px]
        pix = fitz.open(str(out / f"mark-{px}.svg"))[0].get_pixmap(matrix=fitz.Matrix(1, 1), alpha=True)
        assert pix.width == px and pix.height == px
        A = [[pix.samples[(j * px + i) * 4 + 3] / 255.0 for i in range(px)] for j in range(px)]
        def alpha(x, y):   # bilinear on pixel centres, outside = 0
            fx, fy = x - 0.5, y - 0.5; i, j = math.floor(fx), math.floor(fy); tx, ty = fx - i, fy - j
            g = lambda a, b: A[b][a] if 0 <= a < px and 0 <= b < px else 0.0
            return (g(i, j) * (1 - tx) + g(i + 1, j) * tx) * (1 - ty) + (g(i, j + 1) * (1 - tx) + g(i + 1, j + 1) * tx) * ty
        widths = []; d = 3.0
        while d <= s["R"] - 2.0:
            px0, py0 = s["cx"] + d * u[0], s["cy"] + d * u[1]; tot = 0.0; k = -6.0
            while k <= 6.0:
                tot += (1 - alpha(px0 + k * n[0], py0 + k * n[1])) * 0.05; k += 0.05
            widths.append((tot, d)); d += 0.5
        mn = min(widths)
        # independent metric: pixels (sampled at 1 px steps across the slot, alpha < 0.5) per section
        cnt = []
        for _, d in widths:
            px0, py0 = s["cx"] + d * u[0], s["cy"] + d * u[1]
            cnt.append(sum(1 for k in range(-4, 5) if alpha(px0 + k * n[0] * 0.5, py0 + k * n[1] * 0.5) < 0.5) * 0.5)
        ok = mn[0] >= 1.0
        bad += (not ok)
        print(f"{'PASS' if ok else 'FAIL'} mark-{px}: slot width (integrated uncovered coverage across the slot) min {mn[0]:.2f} px at {mn[1]:.1f} px from the corner, "
              f"over d=3..{s['R'] - 2}; half-pixel-sample count min {min(cnt):.1f} px; channel w={s['w']} px, wedge width at the arc {v1_slot_width_px(s['R']):.1f} px")
    v1 = v1_slot_width_px(16)
    print(f"reference: v1 geometry scaled to a 16 px mark has a wedge slot only {2 * 4.8 * math.tan(math.radians(HALF)):.2f} px wide at 4.8 px from the corner and {v1:.1f} px at the arc: below 1 px for the first {1 / (2 * math.tan(math.radians(HALF))):.1f} px")
    return bad

if "--verify" in sys.argv:
    sys.exit(1 if verify() else 0)
