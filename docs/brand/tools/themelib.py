"""Shared colour maths and the v1.1 PROPOSED state/derived-token formulas. Python 3.9+, stdlib only.
Used by build_proposed_tokens.py, check_proposed.py, derive_tenant_theme.py. No file is written here."""
import json, math, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
WHITE, CARBON_DEEP, CARBON_INK = "#FFFFFF", "#0E1117", "#12151B"

# ---------- sRGB / contrast (WCAG 2.x) ----------
def h2rgb(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]

def rgb2h(c):
    return "#" + "".join(f"{max(0, min(255, int(round(v)))):02X}" for v in c)

def _lin(v):
    v /= 255.0
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

def _delin(v):
    v = max(0.0, min(1.0, v))
    return 255.0 * (12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055)

def lum(h):
    r, g, b = [_lin(v) for v in h2rgb(h)]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b

def ratio(a, b):
    hi, lo = sorted([lum(a), lum(b)], reverse=True)
    return (hi + 0.05) / (lo + 0.05)

def mix(a, b, t):
    """sRGB-space mix: fraction t of b."""
    ca, cb = h2rgb(a), h2rgb(b)
    return rgb2h([x + (y - x) * t for x, y in zip(ca, cb)])

def over(fg, alpha, bg):
    return mix(bg, fg, alpha)

# ---------- OKLab / OKLCH (Ottosson) ----------
def to_oklab(h):
    r, g, b = [_lin(v) for v in h2rgb(h)]
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l, m, s = l ** (1 / 3), m ** (1 / 3), s ** (1 / 3)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)

def _from_oklab_lin(L, a, b):
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
            -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)

def to_oklch(h):
    L, a, b = to_oklab(h)
    return L, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360

def _in_gamut(rgb, eps=1e-4):
    return all(-eps <= v <= 1 + eps for v in rgb)

def oklch_to_hex(L, C, H):
    """Gamut-map by reducing chroma (hue and lightness kept)."""
    hr = math.radians(H)
    lo, hi = 0.0, C
    if not _in_gamut(_from_oklab_lin(L, C * math.cos(hr), C * math.sin(hr))):
        for _ in range(40):
            mid = (lo + hi) / 2
            if _in_gamut(_from_oklab_lin(L, mid * math.cos(hr), mid * math.sin(hr))):
                lo = mid
            else:
                hi = mid
        C = lo
    rgb = _from_oklab_lin(L, C * math.cos(hr), C * math.sin(hr))
    return rgb2h([_delin(v) for v in rgb])

def dE(a, b):
    la, lb = to_oklab(a), to_oklab(b)
    return math.dist(la, lb)

_CVD = {
    "protan": [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
    "deutan": [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]],
    "tritan": [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.303900]],
}

def cvd(h, kind):
    """Machado et al. 2009 matrices, severity 1.0, applied in linear RGB (matrices typed from memory: UNVERIFIED)."""
    if kind == "normal":
        return h
    lin = [_lin(v) for v in h2rgb(h)]
    m = _CVD[kind]
    out = [sum(m[i][j] * lin[j] for j in range(3)) for i in range(3)]
    return rgb2h([_delin(v) for v in out])

# ---------- tokens ----------
def load_v1():
    return json.loads((ROOT / "tokens" / "tokens.json").read_text(encoding="utf-8"))

def v1_base(mode):
    c = load_v1()["color"][mode]
    return {k: c[k]["hex"] for k in ("background", "surface", "text", "primary", "accent", "success", "warning", "danger")}

# Fixed formula parameters (PROPOSED; tuned so that every pair in contrast_pairs() passes)
P = {
    "light": dict(raised_mix=0.0, muted=0.28, border=0.12, border_control=0.58, hover=0.06, pressed=0.12, selected=0.12,
                  p_hover=("#12151B", 0.12), p_pressed=("#12151B", 0.24), d_hover=("#12151B", 0.12), d_pressed=("#12151B", 0.24),
                  visited=0.45, disabled_fill=0.08, disabled_label=0.52, scrim=("#0E1117", 0.48)),
    "dark": dict(raised_mix=0.05, muted=0.28, border=0.14, border_control=0.50, hover=0.06, pressed=0.12, selected=0.16,
                 p_hover=("#FFFFFF", 0.12), p_pressed=("#0E1117", 0.12), d_hover=("#FFFFFF", 0.12), d_pressed=("#0E1117", 0.12),
                 visited=0.45, disabled_fill=0.10, disabled_label=0.52, scrim=("#0E1117", 0.64)),
}
TINT, SECONDARY_HOVER, SECONDARY_PRESSED = 0.14, 0.08, 0.14
DEVICE_OPACITY, DEVICE_OPACITY_MAX = 0.10, 0.16

def pick_label(fill, light_first=True):
    """Label colour with the higher contrast among white and Carbon deep (white preferred when it passes 4.5)."""
    if light_first and ratio(WHITE, fill) >= 4.5:
        return WHITE
    return WHITE if ratio(WHITE, fill) >= ratio(CARBON_DEEP, fill) else CARBON_DEEP

CHART = {
    # Found by script search: pool filtered to >=3.1:1 on background, surface, raised; status hues (crimson, jade, ochre) excluded;
    # slots 1-3 are brand colours (Cobalt, Coral, text); slots 4-6 maximise the minimum pairwise OKLab distance under normal vision,
    # protanopia, deuteranopia and tritanopia simulation.
    "light": ["#2443D0", "#E0552C", "#12151B", "#0095A1", "#5C4300", "#97386B"],
    "dark":  ["#86A0FF", "#FF8A63", "#E8EAEF", "#2B8F9A", "#A1790C", "#F3A6CA"],
}

def build_theme(mode, base=None, primary=None, accent=None, chart=None):
    """Return {key: hex | (hex, alpha)} of the PROPOSED derived tokens for one mode, from the 8 base colours."""
    b = dict(base or v1_base(mode))
    if primary:
        b["primary"] = primary
    if accent:
        b["accent"] = accent
    p = P[mode]
    bg, sf, tx, pr, dg = b["background"], b["surface"], b["text"], b["primary"], b["danger"]
    t = {}
    t["surface-raised"] = mix(sf, tx, p["raised_mix"]) if p["raised_mix"] else sf
    rs = t["surface-raised"]
    t["text-muted"] = mix(tx, sf, p["muted"])
    t["border"] = mix(sf, tx, p["border"])
    t["border-control"] = mix(sf, tx, p["border_control"])
    t["hover"] = (tx, p["hover"]); t["pressed"] = (tx, p["pressed"]); t["selected"] = (pr, p["selected"])
    t["primary-hover"] = mix(pr, *p["p_hover"]); t["primary-pressed"] = mix(pr, *p["p_pressed"])
    t["primary-label"] = pick_label(pr) if mode == "light" else (CARBON_DEEP if ratio(CARBON_DEEP, pr) >= 4.5 else WHITE)
    t["secondary-hover"] = (pr, SECONDARY_HOVER); t["secondary-pressed"] = (pr, SECONDARY_PRESSED)
    t["danger-hover"] = mix(dg, *p["d_hover"]); t["danger-pressed"] = mix(dg, *p["d_pressed"])
    t["danger-label"] = WHITE if mode == "light" else CARBON_DEEP
    t["link-visited"] = mix(pr, tx, p["visited"])
    t["disabled-fill"] = over(tx, p["disabled_fill"], sf)
    t["disabled-label"] = mix(tx, t["disabled-fill"], 1 - p["disabled_label"])
    for s in ("success", "warning", "danger"):
        t[s + "-tint"] = (b[s], TINT)
    sfs = surfaces(dict(t, _base=b))
    for st in ("success", "warning", "danger"):
        # v1 gap: status colour on its own 14% tint can miss 4.5:1. Pill label = status colour mixed toward text, smallest step that passes everywhere.
        for step in range(0, 21):
            c = mix(b[st], tx, step * 0.05)
            if all(ratio(c, over(*t[st + "-tint"], v)) >= 4.5 for v in sfs.values()):
                break
        t[st + "-pill"] = c
    t["scrim"] = p["scrim"]
    t["device-primary"] = (pr, DEVICE_OPACITY)
    t["device-neutral"] = (tx, DEVICE_OPACITY * (0.6 if mode == "light" else 1.0))
    for i, c in enumerate(chart or CHART[mode], 1):
        t[f"chart-{i}"] = c
    for a in range(40, 101):
        c = over(tx, a / 100, sf)
        if ratio(c, sf) >= 3.0 and ratio(c, bg) >= 3.0 and ratio(c, rs) >= 3.0:
            t["chart-comparison"] = c; t["_comparison_alpha"] = a / 100
            break
    t["_base"] = b
    return t

def val(t, k, over_bg=None):
    v = t[k] if k in t else t["_base"][k]
    if isinstance(v, tuple):
        return over(v[0], v[1], over_bg) if over_bg else v[0]
    return v

def surfaces(t):
    """Named backdrops a component can sit on (opaque hex)."""
    b = t["_base"]; sf = b["surface"]
    return {
        "background": b["background"], "surface": sf, "raised": t["surface-raised"],
        "hover": over(*t["hover"], sf), "pressed": over(*t["pressed"], sf), "selected": over(*t["selected"], sf),
    }

def contrast_pairs(t, mode):
    """All pairs the PROPOSED tokens promise. Each: dict(id,label,fg,bg,min,tags). min 4.5 text, 3.0 non-text."""
    b = t["_base"]; S = surfaces(t); out = []
    def add(pid, label, fg, bg, mn, *tags):
        out.append(dict(id=pid, label=label, fg=fg, bg=bg, min=mn, tags=set(tags)))
    for sn, sv in S.items():
        add(f"text/{sn}", f"Text on {sn}", b["text"], sv, 4.5)
        add(f"muted/{sn}", f"Muted text and placeholder on {sn}", t["text-muted"], sv, 4.5)
    for sn in ("background", "surface", "raised", "hover", "selected"):
        add(f"link/{sn}", f"Primary text and links on {sn}", b["primary"], S[sn], 4.5, "primary")
    for sn in ("background", "surface", "raised"):
        add(f"visited/{sn}", f"Visited link on {sn}", t["link-visited"], S[sn], 4.5, "primary")
    for key, tint in (("secondary-hover", t["secondary-hover"]), ("secondary-pressed", t["secondary-pressed"])):
        for sn in ("background", "surface"):
            add(f"{key}/{sn}", f"Secondary label on {key} over {sn}", b["primary"], over(*tint, S[sn]), 4.5, "primary")
    for st in ("success", "warning", "danger"):
        for sn in ("background", "surface", "raised"):
            add(f"{st}/{sn}", f"{st.capitalize()} text on {sn}", b[st], S[sn], 4.5)
        for sn in ("background", "surface", "raised", "hover", "selected"):
            pill = over(*t[st + "-tint"], S[sn])
            add(f"pill-{st}/{sn}", f"{st.capitalize()} pill label on its tint over {sn}", t[st + "-pill"], pill, 4.5)
            add(f"pill-icon-{st}/{sn}", f"{st.capitalize()} pill icon on its tint over {sn} (non-text)", b[st], pill, 3.0)
    for nm, fill in (("", b["primary"]), ("-hover", t["primary-hover"]), ("-pressed", t["primary-pressed"])):
        add(f"btn-primary{nm}", f"Primary button label on fill{nm or ' (rest)'}", t["primary-label"], fill, 4.5, "primary")
    for nm, fill in (("", b["danger"]), ("-hover", t["danger-hover"]), ("-pressed", t["danger-pressed"])):
        add(f"btn-danger{nm}", f"Destructive button label on fill{nm or ' (rest)'}", t["danger-label"], fill, 4.5)
    add("btn-disabled", "Disabled label on disabled fill (brand target; WCAG exempt)", t["disabled-label"], t["disabled-fill"], 3.0)
    for sn in ("background", "surface", "raised"):
        add(f"ring/{sn}", f"Focus ring on {sn}", b["primary"], S[sn], 3.0, "primary")
        add(f"border-control/{sn}", f"Control border on {sn}", t["border-control"], S[sn], 3.0)
    for sn in ("background", "surface"):
        add(f"accent/{sn}", f"Accent graphic on {sn}", b["accent"], S[sn], 3.0, "accent")
    for i in range(1, 7):
        for sn in ("background", "surface"):
            add(f"chart-{i}/{sn}", f"Chart series {i} on {sn}", t[f"chart-{i}"], S[sn], 3.0)
    for sn in ("background", "surface"):
        add(f"chart-comparison/{sn}", f"Chart comparison series on {sn}", t["chart-comparison"], S[sn], 3.0)
    for a in (DEVICE_OPACITY, DEVICE_OPACITY_MAX):
        for nm, col in (("primary", b["primary"]), ("neutral", b["text"])):
            for sn in ("background", "surface"):
                add(f"device-{nm}-{int(a*100)}/{sn}", f"Text over quadrant device ({nm}, {int(a*100)}%) on {sn}", b["text"], over(col, a, S[sn]), 4.5)
    return out

def worst(pairs):
    return [(p, ratio(p["fg"], p["bg"])) for p in pairs if ratio(p["fg"], p["bg"]) + 1e-9 < p["min"]]


# ---------- CSS variable map ----------
# key -> (display name, role, css variable)
COLOR_KEYS = [
    ("surface-raised", "Panel raised", "Surface of menus, popovers, modals, drawers, toasts", "--color-surface-raised"),
    ("text-muted", "Carbon muted", "Secondary text, helper text, placeholder (AA on every surface)", "--color-text-muted"),
    ("border", "Hairline", "Dividers, card and table borders (decorative, no contrast requirement)", "--color-border"),
    ("border-control", "Control edge", "Input, checkbox, radio, switch boundary (3:1 non-text)", "--color-border-control"),
    ("hover", "Hover", "Overlay on rows, menu items, ghost controls", "--state-hover"),
    ("pressed", "Pressed", "Overlay while pressed", "--state-pressed"),
    ("selected", "Selected", "Overlay on selected rows, nav item, tab", "--state-selected"),
    ("primary-hover", "Cobalt hover", "Primary button fill on hover", "--color-primary-hover"),
    ("primary-pressed", "Cobalt pressed", "Primary button fill pressed", "--color-primary-pressed"),
    ("primary-label", "Primary label", "Label on primary fill (white light, Carbon deep dark; same as v1)", "--color-primary-label"),
    ("secondary-hover", "Secondary hover", "Secondary button background on hover", "--state-secondary-hover"),
    ("secondary-pressed", "Secondary pressed", "Secondary button background pressed", "--state-secondary-pressed"),
    ("danger-hover", "Crimson hover", "Destructive button fill on hover", "--color-danger-hover"),
    ("danger-pressed", "Crimson pressed", "Destructive button fill pressed", "--color-danger-pressed"),
    ("danger-label", "Destructive label", "Label on destructive fill (white light, Carbon deep dark: fixes the v1 dark gap)", "--color-danger-label"),
    ("link-visited", "Visited link", "Visited link colour (underline always on)", "--color-link-visited"),
    ("disabled-fill", "Disabled fill", "Disabled control background", "--color-disabled-fill"),
    ("disabled-label", "Disabled label", "Disabled control label (3:1 brand target; WCAG exempts disabled)", "--color-disabled-label"),
    ("success-tint", "Jade tint", "Pill background (v1 14%)", "--color-success-tint"),
    ("warning-tint", "Ochre tint", "Pill background (v1 14%)", "--color-warning-tint"),
    ("danger-tint", "Crimson tint", "Pill background (v1 14%)", "--color-danger-tint"),
    ("success-pill", "Jade pill label", "Pill label on its tint (v1 gap fix; icon keeps full Jade)", "--color-success-pill"),
    ("warning-pill", "Ochre pill label", "Pill label on its tint (v1 gap fix)", "--color-warning-pill"),
    ("danger-pill", "Crimson pill label", "Pill label on its tint (v1 gap fix)", "--color-danger-pill"),
    ("scrim", "Scrim", "Behind modals and drawers", "--color-scrim"),
    ("device-primary", "Device Cobalt", "Quadrant device, primary version", "--color-device-primary"),
    ("device-neutral", "Device neutral", "Quadrant device, Carbon (light) or Chalk (dark) version", "--color-device-neutral"),
] + [(f"chart-{i}", f"Chart {i}", f"Categorical series {i}", f"--chart-{i}") for i in range(1, 7)] + [
    ("chart-comparison", "Chart comparison", "De-emphasised comparison series (text colour at the lowest alpha that gives 3:1)", "--chart-comparison")]


def rgba(h, a):
    r, g, b = h2rgb(h)
    return f"rgba({r},{g},{b},{a:g})"

BASE_VARS = {"background": "--color-background", "surface": "--color-surface", "text": "--color-text", "primary": "--color-primary",
             "accent": "--color-accent", "success": "--color-success", "warning": "--color-warning", "danger": "--color-danger"}

def css_vars(t):
    """{cssVar: value} for the 8 base colours plus every PROPOSED derived colour of a built theme."""
    out = {BASE_VARS[k]: t["_base"][k] for k in BASE_VARS}
    for key, _n, _r, var in COLOR_KEYS:
        v = t[key]
        out[var] = rgba(*v) if isinstance(v, tuple) else v
    return out
