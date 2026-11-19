#!/usr/bin/env python3
"""QA-007: property-style contrast tests for tenant themes (light and dark). pytest or plain python, stdlib only, deterministic.
Run: python3 -m pytest docs/brand/tools/test_tenant_contrast.py -q   (or python3 test_tenant_contrast.py from this folder)

Reference: WCAG 2.2 SC 1.4.3 Contrast (Minimum) 4.5:1 text, 3:1 large text; SC 1.4.11 Non-text Contrast 3:1 (UI components, graphics);
SC 1.4.11 also covers the focus indicator colour; relative luminance and contrast ratio definitions in the same spec.
  https://www.w3.org/TR/WCAG22/#contrast-minimum  https://www.w3.org/TR/WCAG22/#non-text-contrast
  https://www.w3.org/TR/WCAG22/#dfn-contrast-ratio  (accessed 2026-11-19)
Published reference values used below (the well known WebAIM/W3C examples): black on white 21:1; #767676 on white 4.54:1 (the lightest
grey that passes 4.5:1); #777777 on white 4.48:1 (just fails); #808080 on white 3.95:1; white on white 1:1. Relative luminance of #808080 is 0.2159."""
import json, pathlib, re
import themelib as T
import derive_tenant_theme as D

TOKENS = pathlib.Path(__file__).resolve().parent.parent / "tokens"
AA_TEXT, AA_UI = 4.5, 3.0
RAISED_MIN = {"text": 4.5, "ui": 3.0}

# ---- independent reference implementation straight from the WCAG definition (does not import themelib) ----
def ref_ratio(a, b):
    def lin(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4   # WCAG 2.x text; equals the 0.04045 form for 8-bit input
    def lum(h):
        r, g, b = (lin(int(h.lstrip("#")[i:i + 2], 16)) for i in (0, 2, 4))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)

# ---- brand colour grid (hex, note). Includes edge cases and Arabic-market typical palettes ----
GRID = [
    # edge cases
    ("#FFFFFF", "white"), ("#FEFEFE", "near-white"), ("#FAFAFF", "near-white tinted"), ("#000000", "black"), ("#010101", "near-black"),
    ("#0A0A14", "near-black tinted"), ("#808080", "mid grey"), ("#6B7280", "cool grey"), ("#BFBFBF", "light grey"), ("#404040", "dark grey"),
    ("#FF0000", "pure red"), ("#00FF00", "pure green"), ("#0000FF", "pure blue"), ("#FFFF00", "pure yellow"), ("#00FFFF", "cyan"), ("#FF00FF", "magenta"),
    ("#FFD400", "yellow"), ("#F59E0B", "amber"), ("#7DB6FF", "sky"), ("#14B8A6", "teal-500"), ("#1A1040", "very dark violet"),
    ("#767676", "AA boundary grey"), ("#E8E8FF", "very low contrast lavender"), ("#FFF5F5", "very low contrast blush"),
    ("#2443D0", "Orrery Cobalt"), ("#C21F3A", "Orrery Crimson"), ("#E0552C", "Orrery Coral"), ("#13795B", "Orrery Jade"), ("#9E5600", "Orrery Ochre"),
    # hue extremes at medium lightness (every 30 degrees)
    *[(T.oklch_to_hex(0.55, 0.15, h), f"hue {h}") for h in range(0, 360, 30)],
    *[(T.oklch_to_hex(0.80, 0.12, h), f"light hue {h}") for h in range(0, 360, 60)],
    *[(T.oklch_to_hex(0.30, 0.10, h), f"dark hue {h}") for h in range(0, 360, 60)],
    # Arabic-brand typical palettes (Gulf and Egypt retail, finance, logistics; invented, not real brands)
    ("#006C35", "Saudi flag green"), ("#0F766E", "teal"), ("#1F3A8A", "navy"), ("#C8A24A", "gold"), ("#8A6D1D", "dark gold"),
    ("#7A1F3D", "maroon"), ("#9A3412", "burnt orange"), ("#5B2C83", "royal purple"), ("#9333EA", "purple"), ("#0E7490", "petrol"),
    ("#1E40AF", "royal blue"), ("#B45309", "copper"), ("#4D7C0F", "olive"), ("#00A651", "emerald"), ("#D4AF37", "metallic gold"),
    ("#0B3D2E", "very dark green"), ("#E4572E", "vermilion"), ("#2D6A4F", "forest"), ("#264653", "slate teal"), ("#7C3AED", "violet"),
]
# deterministic pseudo-random fill (LCG, fixed seed, same generator as test_derive_tenant_theme.py)
_x = 987654
for _i in range(150):
    _c = []
    for _k in range(3):
        _x = (1103515245 * _x + 12345) & 0x7FFFFFFF
        _c.append(_x >> 8 & 255)
    GRID.append((T.rgb2h(_c), f"lcg {_i}"))

_CACHE = {}
def der(c, accent=None):
    k = (c, accent)
    if k not in _CACHE:
        _CACHE[k] = D.derive(c, accent)
    return _CACHE[k]

def accepted():
    return [(c, der(c)) for c, _ in GRID if der(c)["status"] == "ok"]

def rejected():
    return [(c, der(c)) for c, _ in GRID if der(c)["status"] == "rejected"]

# 1. reference values: the contrast function matches published WCAG values, and the three implementations agree
def test_contrast_matches_published_values():
    cases = [("#000000", "#FFFFFF", 21.0, 0.005), ("#FFFFFF", "#FFFFFF", 1.0, 0.0005), ("#767676", "#FFFFFF", 4.54, 0.005),
             ("#777777", "#FFFFFF", 4.48, 0.005), ("#808080", "#FFFFFF", 3.95, 0.005)]
    for a, b, want, tol in cases:
        for f in (T.ratio, ref_ratio):
            assert abs(f(a, b) - want) <= tol, (f.__name__, a, b, f(a, b), want)
            assert abs(f(b, a) - want) <= tol          # symmetric
    assert abs(T.lum("#808080") - 0.2159) < 0.0005 and T.lum("#FFFFFF") == 1 and T.lum("#000000") == 0
    assert T.ratio("#767676", "#FFFFFF") >= AA_TEXT > T.ratio("#777777", "#FFFFFF")      # the 4.5 boundary sits between these greys

def test_contrast_implementations_agree():
    import importlib.util
    spec = importlib.util.spec_from_file_location("cc_ref", TOKENS.parent / "tools" / "check_contrast.py")
    src = spec.loader.get_source("cc_ref")
    ns = {}
    exec(src.split("def hexof")[0].replace("sys.exit", "int").replace('root = pathlib.Path(__file__).resolve().parent.parent', f'root = pathlib.Path(r"{TOKENS.parent}")'), ns)
    for g in range(0, 256, 5):
        h = "#%02X%02X%02X" % (g, 255 - g, (g * 7) % 256)
        for b in ("#FFFFFF", "#12151B", "#F3F4F6"):
            assert abs(T.ratio(h, b) - ref_ratio(h, b)) < 1e-9 and abs(ns["ratio"](h, b) - ref_ratio(h, b)) < 1e-9

# 2. every accepted colour: every pair in both themes meets its AA minimum, recomputed independently; minima themselves are AA
def test_accepted_themes_meet_aa_both_themes():
    acc = accepted()
    assert len(acc) >= 40, len(acc)       # the grid must exercise real acceptances, not only rejections
    for c, r in acc:
        for m in ("light", "dark"):
            assert r["pairs"][m], (c, m)
            for p in r["pairs"][m]:
                assert p["min"] in (AA_TEXT, AA_UI), (c, m, p["id"], p["min"])      # never a laxer bar than WCAG AA
                assert ref_ratio(p["fg"], p["bg"]) + 1e-9 >= p["min"], (c, m, p["id"], p["fg"], p["bg"], ref_ratio(p["fg"], p["bg"]))

def test_text_pairs_use_4_5_and_ui_pairs_use_3():
    r = der("#2443D0")
    for m in ("light", "dark"):
        for p in r["pairs"][m]:
            pid = p["id"].split("/")[0]
            if pid in ("text", "muted", "link", "visited", "btn-primary", "btn-primary-hover", "btn-primary-pressed", "secondary-hover", "secondary-pressed"):
                assert p["min"] == AA_TEXT, p["id"]
            if pid in ("ring", "accent", "border-control") or pid.startswith("chart"):
                assert p["min"] == AA_UI, p["id"]

# 3. tenant-dependent tokens, checked directly on the rebuilt theme (not only via the report): text/link, labels, focus ring, UI parts
def _rebuilt(r, m):
    d = r[m]
    return T.build_theme(m, primary=d["primary"], accent=d["accent"])

def test_focus_ring_3_to_1_against_every_adjacent_surface():
    for c, r in accepted():
        for m in ("light", "dark"):
            t = _rebuilt(r, m)
            ring = t["_base"]["primary"]
            for name, bg in T.surfaces(t).items():       # page, card, raised, and the hover/pressed/selected states the ring can sit on
                assert ref_ratio(ring, bg) >= AA_UI, (c, m, name, ring, bg, ref_ratio(ring, bg))

def test_labels_and_links_text_4_5_in_both_themes():
    for c, r in accepted():
        for m in ("light", "dark"):
            t = _rebuilt(r, m); b = t["_base"]; S = T.surfaces(t)
            for fill in (b["primary"], t["primary-hover"], t["primary-pressed"]):
                assert ref_ratio(t["primary-label"], fill) >= AA_TEXT, (c, m, "label", fill)
            for sn in ("background", "surface", "raised", "hover", "selected"):
                assert ref_ratio(b["primary"], S[sn]) >= AA_TEXT, (c, m, "link", sn)
            for sn in ("background", "surface", "raised"):
                assert ref_ratio(t["link-visited"], S[sn]) >= AA_TEXT, (c, m, "visited", sn)
            assert r[m]["primaryLabel"] == t["primary-label"]

def test_large_text_threshold_is_not_relied_on():
    # Primary text and links are held to 4.5:1 (normal text), so they also pass the 3:1 large-text bar with margin.
    for c, r in accepted():
        for m in ("light", "dark"):
            for p in r["pairs"][m]:
                if p["id"].startswith(("link/", "btn-primary")):
                    assert ref_ratio(p["fg"], p["bg"]) >= AA_TEXT > AA_UI

def test_accent_is_graphics_only_and_3_to_1():
    for c in ("#2443D0", "#006C35", "#7A1F3D"):
        for a in ("#F59E0B", "#00A651", "#C8A24A", "#0E7490", None):
            r = der(c, a)
            if r["status"] != "ok":
                assert r["reasons"] and "ccent" in " ".join(r["reasons"]) or a is None or "Primary" in r["reasons"][0]
                continue
            for m in ("light", "dark"):
                acc = [p for p in r["pairs"][m] if p["id"].startswith("accent/")]
                assert acc and all(p["min"] == AA_UI and ref_ratio(p["fg"], p["bg"]) >= AA_UI for p in acc), (c, a, m)

# 4. rejection carries a clear reason; nothing is silently accepted below AA; no internal-bug rejections
def test_rejections_have_clear_reasons():
    rej = rejected()
    assert len(rej) >= 20, len(rej)
    kinds = ("not a hex", "near-grey", "near-black", "near-white", "Crimson", "too light", "too dark", "indistinguishable", "grey in the dark", "No ")
    for c, r in rej:
        why = " ".join(r["reasons"])
        assert r["reasons"] and len(why) > 40, (c, r["reasons"])
        assert any(k in why for k in kinds), (c, why)
        assert "Internal check failed" not in why, (c, why)               # that message means an algorithm bug
        assert r["light"] is None and r["dark"] is None, c               # a rejected colour yields no tokens to apply
    # AA unreachable by auto-adjust: reason states the ratio, the needed ratio and the colour it would become
    why = " ".join(der("#FFD400")["reasons"])
    assert "too light" in why and "4.5:1" in why and "limit" in why and "would become" in why
    assert "near-white" in " ".join(der("#FEFEFE")["reasons"]) or "near-grey" in " ".join(der("#FEFEFE")["reasons"])
    assert "near-black" in " ".join(der("#000000")["reasons"])

def test_rejection_when_adjusting_cannot_reach_aa_names_the_limit():
    for c in ("#FFD400", "#F59E0B", "#7DB6FF", "#14B8A6", "#00FFFF", "#FFFF00"):
        r = der(c)
        assert r["status"] == "rejected", c
        assert "too light" in r["reasons"][0] and str(D.LIGHT_MAX_SHIFT) in r["reasons"][0], (c, r["reasons"])

def test_bad_input_is_rejected_not_raised():
    for bad in ("", "zzz", "#12345", "#GGGGGG", "12345678", None and "x"):
        r = D.derive(bad if bad is not None else "x")
        assert r["status"] == "rejected" and "not a hex" in r["reasons"][0], bad

# 5. determinism and idempotence
def test_derivation_is_deterministic():
    for c, _ in GRID[:60]:
        a = json.dumps(D.derive(c), sort_keys=True)
        assert a == json.dumps(D.derive(c), sort_keys=True), c
        assert a == json.dumps(D.derive(c.lower()), sort_keys=True) or c.lower() != c       # case of input never matters (input echo is normalised)

def test_light_adjustment_is_idempotent():
    n = 0
    for c, r in accepted():
        lp = r["light"]["primary"]
        r2 = D.derive(lp)
        assert r2["status"] == "ok" and r2["light"]["primary"] == lp, (c, lp, r2["reasons"], r2["light"] and r2["light"]["primary"])
        assert not [a for a in r2["adjustments"] if a.startswith("light primary")], (c, r2["adjustments"])   # already AA: no further darkening
        n += 1
    assert n >= 40

def test_adjusted_output_is_stable_json_roundtrip():
    r = der("#0F766E")
    assert json.loads(json.dumps(r)) == r

# 6. dark derives from the same seed: hue kept, lighter than light, light stays a darkening of the input
def _hue_gap(a, b):
    d = abs(T.to_oklch(a)[2] - T.to_oklch(b)[2]) % 360
    return min(d, 360 - d)

def test_dark_and_light_derive_from_the_same_seed():
    for c, r in accepted():
        Lc, Cc, Hc = T.to_oklch(c)
        lp, dp = r["light"]["primary"], r["dark"]["primary"]
        if Cc >= 0.08:                       # hue is only well defined with some chroma; tolerance covers gamut mapping and hex rounding
            assert _hue_gap(c, lp) <= 12 and _hue_gap(c, dp) <= 12, (c, lp, dp, _hue_gap(c, lp), _hue_gap(c, dp))
        assert T.to_oklch(lp)[0] <= Lc + 0.01, (c, lp)                 # light only ever darkens
        assert T.to_oklch(dp)[0] >= 0.70, (c, dp)                      # dark starts at L .72 and lightens
        assert T.to_oklch(dp)[0] > T.to_oklch(lp)[0], (c, lp, dp)
        assert r["light"]["accent"] and r["dark"]["accent"]

def test_dark_surfaces_are_the_locked_base_and_tenant_cannot_move_them():
    base_l, base_d = T.v1_base("light"), T.v1_base("dark")
    for c, r in accepted()[:25]:
        assert r["light"]["vars"]["--color-background"] == base_l["background"] and r["dark"]["vars"]["--color-background"] == base_d["background"]
        assert r["light"]["vars"]["--color-text"] == base_l["text"] and r["dark"]["vars"]["--color-surface"] == base_d["surface"]
        for k in ("success", "warning", "danger"):                    # status colours are locked
            assert r["light"]["vars"][f"--color-{k}"] == base_l[k] and r["dark"]["vars"][f"--color-{k}"] == base_d[k]

def test_generated_css_carries_both_themes():
    r = der("#0F766E"); s = D.css("al-nakhla", r)
    assert s.count('[data-tenant="al-nakhla"]') == 3 and "prefers-color-scheme: dark" in s and '[data-theme="dark"]' in s
    assert r["light"]["primary"] in s and r["dark"]["primary"] in s

# 7. generated token CSS (read only): default theme has no pair below AA, light and dark, and the two dark blocks agree
def _blocks(css):
    """-> {'light': {var: val}, 'dark': {var: val}, 'dark_media': {...}} from a generated tokens file."""
    out = {"light": {}, "dark": {}, "dark_media": {}}
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        sel = sel.strip()
        vs = dict(re.findall(r"(--[\w-]+):\s*([^;]+);", body))
        if sel == ":root":
            out["light"].update(vs)
        elif sel == ':root[data-theme="dark"]':
            out["dark"].update(vs)
        elif sel == ':root:not([data-theme="light"])':
            out["dark_media"].update(vs)
    return out

def _read_tokens():
    parts = [_blocks((TOKENS / f).read_text(encoding="utf-8")) for f in ("tokens.css", "tokens.proposed.css")]
    return {k: {**parts[0][k], **parts[1][k]} for k in parts[0]}

def _parse(v):
    v = v.strip()
    m = re.fullmatch(r"rgba\((\d+),(\d+),(\d+),([\d.]+)\)", v)
    return (T.rgb2h([int(m[1]), int(m[2]), int(m[3])]), float(m[4])) if m else v.upper()

def _theme_from_css(vs):
    b = {k: vs[var].upper() for k, var in T.BASE_VARS.items()}
    t = {"_base": b}
    for key, _n, _r, var in T.COLOR_KEYS:
        t[key] = _parse(vs[var])
    return t

def test_generated_tokens_dark_blocks_agree():
    tok = _read_tokens()
    assert tok["dark"] == tok["dark_media"] and tok["dark"] and tok["light"]

def test_generated_tokens_default_theme_has_no_pair_below_aa():
    tok = _read_tokens()
    for m in ("light", "dark"):
        t = _theme_from_css(tok[m])
        pairs = T.contrast_pairs(t, m)
        assert len(pairs) >= 100
        for p in pairs:
            assert p["min"] in (AA_TEXT, AA_UI)
            assert ref_ratio(p["fg"], p["bg"]) + 1e-9 >= p["min"], (m, p["id"], p["fg"], p["bg"], round(ref_ratio(p["fg"], p["bg"]), 3))

def test_generated_tokens_match_the_derivation_of_cobalt():
    # The default theme is the identity tenant: deriving Orrery Cobalt must not move any light colour the CSS ships.
    tok = _read_tokens(); r = der("#2443D0")
    assert r["light"]["vars"]["--color-primary"].upper() == tok["light"]["--color-primary"].upper()
    for k in ("--color-primary-label", "--color-surface-raised", "--color-text-muted"):
        assert r["light"]["vars"][k].upper() == tok["light"][k].upper(), k

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for f in fns:
        f()
    print(f"all {len(fns)} QA-007 tests passed ({len(accepted())} accepted, {len(rejected())} rejected of {len(GRID)} colours)")
