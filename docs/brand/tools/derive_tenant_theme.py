#!/usr/bin/env python3
"""Derive a tenant theme (light and dark) from ONE primary colour and an optional accent. PROPOSED, v1.1.
Usage: derive_tenant_theme.py PRIMARY [ACCENT] [--json] [--css SLUG] [--brief] [--preview OUT.html]
Exit 0 accepted, 1 rejected, 2 bad usage. Python 3.9+, stdlib only. Work is done in OKLCH (Ottosson), contrast is WCAG 2.x on the final hex."""
import json, re, sys
import themelib as T

# ---- policy constants (PROPOSED; calibrated in docs/brand/12-tenant-theming.md) ----
LIGHT_MAX_SHIFT = 0.20     # max OKLab lightness change allowed when darkening a primary to reach AA in the light theme
ACCENT_MAX_SHIFT = 0.25    # accent is graphics only (3:1), so a larger shift is tolerated
MIN_CHROMA = 0.04          # below this the colour reads as grey
MIN_TEXT_CONTRAST = 1.5    # primary must differ from body text colour by at least this ratio
DANGER_DE = 0.10           # OKLab distance to Crimson below which a colour reads as an error colour
ACCENT_MIN_DE = 0.12       # accent must be this far from the primary (OKLab)
STATUS_WARN_DE = 0.10      # closeness to Jade/Ochre is a warning only (pills always carry icon and label)
DARK_L0, DARK_CHROMA = 0.72, 0.65   # start point for the dark primary: v1 Cobalt maps #2443D0 (L .46, C .22) to #86A0FF (L .73, C .14)
DARK_ACCENT_CHROMA = 0.90
STEP = 0.005

def norm_hex(s):
    s = str(s).strip().lstrip("#")
    if re.fullmatch(r"[0-9a-fA-F]{3}", s):
        s = "".join(c * 2 for c in s)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", s):
        raise ValueError(f"not a hex colour: {s!r}")
    return "#" + s.upper()

def _frange(a, b, step):
    n = int(round(abs(b - a) / step))
    sign = 1 if b >= a else -1
    return [a + sign * step * i for i in range(n + 1)]

def _fails(mode, tags, **kw):
    t = T.build_theme(mode, **kw)
    bad = [(p, T.ratio(p["fg"], p["bg"])) for p in T.contrast_pairs(t, mode) if (p["tags"] & tags) and T.ratio(p["fg"], p["bg"]) + 1e-9 < p["min"]]
    return t, bad

def _lch(h):
    L, C, H = T.to_oklch(h)
    return round(L, 3), round(C, 3), round(H, 1)

def derive(primary, accent=None):
    res = {"status": "ok", "input": {"primary": primary, "accent": accent}, "reasons": [], "warnings": [], "adjustments": [], "light": None, "dark": None, "pairs": {}}
    def reject(msg):
        res["status"] = "rejected"; res["reasons"].append(msg); return res
    try:
        p_in = norm_hex(primary); a_in = norm_hex(accent) if accent else None
    except ValueError as e:
        return reject(str(e))
    res["input"] = {"primary": p_in, "accent": a_in}
    base = {m: T.v1_base(m) for m in ("light", "dark")}
    crimson = {m: base[m]["danger"] for m in base}
    L, C, H = T.to_oklch(p_in)

    # ---- input checks ----
    if C < MIN_CHROMA:
        kind = "near-black" if L < 0.35 else "near-white" if L > 0.85 else "near-grey"
        return reject(f"Primary {p_in} is {kind} (OKLCH chroma {C:.3f} < {MIN_CHROMA}). Buttons and links would not read as actionable against text and borders. Choose a colour with visible hue.")
    d = T.dE(p_in, crimson["light"])
    if d < DANGER_DE:
        return reject(f"Primary {p_in} is within {d:.3f} of Orrery Crimson {crimson['light']} (limit {DANGER_DE}). It would read as an error or a destructive action. Choose a different hue or use it as the accent only if it is clearly distinct from Crimson.")

    # ---- light primary: keep the colour if it passes, else darken (hue and chroma kept, gamut-mapped) ----
    cand = [p_in] + [T.oklch_to_hex(l, C, H) for l in _frange(L - STEP, 0.15, STEP)]
    light_p = None
    for h in cand:
        t, bad = _fails("light", {"primary"}, primary=h)
        if not bad:
            light_p = h; break
    first_bad = _fails("light", {"primary"}, primary=p_in)[1]
    if light_p is None:
        return reject(f"No darker shade of {p_in} reaches AA in the light theme.")
    shift = L - T.to_oklch(light_p)[0]
    if light_p != p_in:
        worst = next((x for x in first_bad if x[0]["id"] == "link/surface"), None) or min(first_bad, key=lambda x: x[1] / x[0]["min"])
        if shift > LIGHT_MAX_SHIFT:
            return reject(f"Primary {p_in} is too light: {worst[0]['label']} is {worst[1]:.2f}:1, needs {worst[0]['min']}:1. Reaching AA means darkening it by {shift:.2f} OKLab lightness (limit {LIGHT_MAX_SHIFT}), which would no longer look like the brand colour (would become {light_p}). Choose a darker shade.")
        res["adjustments"].append(f"light primary {p_in} -> {light_p}: darkened {shift:.3f} OKLab L (limit {LIGHT_MAX_SHIFT}); worst original pair {worst[0]['label']} {worst[1]:.2f}:1 (needs {worst[0]['min']})")
    cr = T.ratio(light_p, base["light"]["text"])
    if cr < MIN_TEXT_CONTRAST:
        return reject(f"Primary {p_in} is too dark: only {cr:.2f}:1 against body text {base['light']['text']} (minimum {MIN_TEXT_CONTRAST}:1), so links and buttons would look like text. Choose a lighter or more saturated shade.")
    if T.dE(light_p, crimson["light"]) < DANGER_DE:
        return reject(f"Primary adjusted to {light_p} falls within {DANGER_DE} of Crimson after darkening. Choose a different hue.")

    # ---- dark primary: lighten (hue kept, chroma softened like v1) until every primary pair passes ----
    c0 = C * DARK_CHROMA
    dark_p = None
    for l in _frange(max(L, DARK_L0), 0.97, STEP):
        h = T.oklch_to_hex(l, c0, H)
        if not _fails("dark", {"primary"}, primary=h)[1]:
            dark_p = h; break
    if dark_p is None:
        return reject(f"No lightness of {p_in} gives AA for links and Carbon labels in the dark theme.")
    dl, dc, dh = T.to_oklch(dark_p)
    res["adjustments"].append(f"dark primary derived {p_in} -> {dark_p}: OKLCH L {L:.3f}->{dl:.3f}, C {C:.3f}->{dc:.3f}, hue {H:.0f} kept")
    if dc < MIN_CHROMA * 0.75:
        return reject(f"Dark primary {dark_p} has chroma {dc:.3f}: it would read as grey in the dark theme.")
    if T.dE(dark_p, crimson["dark"]) < DANGER_DE:
        return reject(f"Dark primary {dark_p} falls within {DANGER_DE} of dark Crimson {crimson['dark']}.")
    if T.dE(dark_p, base["dark"]["text"]) < 0.08:
        return reject(f"Dark primary {dark_p} is indistinguishable from the dark theme text colour.")

    # ---- accent ----
    acc = {}
    if a_in:
        aL, aC, aH = T.to_oklch(a_in)
        if aC < MIN_CHROMA:
            return reject(f"Accent {a_in} is near-grey (chroma {aC:.3f}).")
        if T.dE(a_in, crimson["light"]) < DANGER_DE:
            return reject(f"Accent {a_in} is within {DANGER_DE} of Crimson: a highlight in an error colour is not allowed.")
        found = None
        for h in [a_in] + [T.oklch_to_hex(l, aC, aH) for l in _frange(aL - STEP, 0.15, STEP)]:
            if not _fails("light", {"accent"}, primary=light_p, accent=h)[1]:
                found = h; break
        if found is None or aL - T.to_oklch(found)[0] > ACCENT_MAX_SHIFT:
            return reject(f"Accent {a_in} is too light for a graphic on Chalk/Panel (3:1 needs a shift above {ACCENT_MAX_SHIFT} OKLab L). Choose a darker accent.")
        if found != a_in:
            res["adjustments"].append(f"light accent {a_in} -> {found}: darkened {aL - T.to_oklch(found)[0]:.3f} OKLab L to reach 3:1 on Chalk and Panel")
        acc["light"] = found
        found_d = None
        for l in _frange(max(aL, DARK_L0), 0.97, STEP):
            h = T.oklch_to_hex(l, aC * DARK_ACCENT_CHROMA, aH)
            if not _fails("dark", {"accent"}, primary=dark_p, accent=h)[1]:
                found_d = h; break
        if found_d is None:
            return reject(f"No dark-theme shade of accent {a_in} reaches 3:1.")
        acc["dark"] = found_d
        res["adjustments"].append(f"dark accent derived {a_in} -> {found_d}")
        for m, pv in (("light", light_p), ("dark", dark_p)):
            if T.dE(acc[m], pv) < ACCENT_MIN_DE:
                return reject(f"Accent {acc[m]} is too close to the primary {pv} in the {m} theme (distance {T.dE(acc[m], pv):.3f}, minimum {ACCENT_MIN_DE}); a highlight must stand out from the actionable colour.")
    else:
        for m, pv in (("light", light_p), ("dark", dark_p)):
            acc[m] = base[m]["accent"]
            if T.dE(acc[m], pv) < ACCENT_MIN_DE:
                acc = {mm: base[mm]["text"] for mm in base}
                res["adjustments"].append(f"accent: Orrery Coral is within {T.dE(base[m]['accent'], pv):.3f} of the tenant primary in the {m} theme; accent falls back to the text colour (one highlight in Carbon/Chalk)")
                break

    # ---- status closeness is a warning only ----
    for nm in ("success", "warning"):
        dd = T.dE(light_p, base["light"][nm])
        if dd < STATUS_WARN_DE:
            res["warnings"].append(f"Primary is within {dd:.3f} of {nm} colour {base['light'][nm]}. Allowed: status is always shown with icon and label, never colour alone.")

    # ---- final build and full verification (never trust the search) ----
    for m, pv in (("light", light_p), ("dark", dark_p)):
        t = T.build_theme(m, primary=pv, accent=acc[m])
        pairs = T.contrast_pairs(t, m)
        res["pairs"][m] = [dict(id=p["id"], label=p["label"], fg=p["fg"], bg=p["bg"], min=p["min"], ratio=round(T.ratio(p["fg"], p["bg"]), 2),
                                ok=T.ratio(p["fg"], p["bg"]) + 1e-9 >= p["min"]) for p in pairs]
        res[m] = {"primary": pv, "accent": acc[m], "primaryLabel": t["primary-label"], "vars": T.css_vars(t)}
    if any(not p["ok"] for m in res["pairs"] for p in res["pairs"][m]):
        return reject("Internal check failed: a derived pair is below its minimum (this is a bug, not a colour problem).")
    return res

def css(slug, res):
    """Scoped CSS: light, system dark, explicit dark. Selector keys match tokens.css (data-theme) and add data-tenant."""
    def block(m, ind):
        return "".join(f"{ind}{k}: {v};\n" for k, v in res[m]["vars"].items())
    s = f":root[data-tenant=\"{slug}\"] {{\n{block('light', '  ')}}}\n\n"
    s += f"@media (prefers-color-scheme: dark) {{\n  :root[data-tenant=\"{slug}\"]:not([data-theme=\"light\"]) {{\n{block('dark', '    ')}  }}\n}}\n\n"
    s += f":root[data-tenant=\"{slug}\"][data-theme=\"dark\"] {{\n{block('dark', '  ')}}}\n"
    return s

def print_report(res, brief=False):
    print(f"input: primary {res['input']['primary']}  accent {res['input']['accent']}")
    print("STATUS:", res["status"].upper())
    for r in res["reasons"]:
        print("  REJECTED:", r)
    for a in res["adjustments"]:
        print("  adjustment:", a)
    for w in res["warnings"]:
        print("  warning:", w)
    if res["status"] != "ok":
        return
    for m in ("light", "dark"):
        r = res[m]
        print(f"\n[{m}] primary {r['primary']}  label {r['primaryLabel']}  accent {r['accent']}")
        for p in res["pairs"][m]:
            if brief and p["ok"] and p["id"].split("/")[0] not in ("link", "btn-primary", "ring", "accent"):
                continue
            print(f"  {'PASS' if p['ok'] else 'FAIL'} {p['ratio']:6.2f} (min {p['min']}) {p['label']}  {p['fg']} on {p['bg']}")
        print(f"  {sum(p['ok'] for p in res['pairs'][m])}/{len(res['pairs'][m])} pairs pass")

def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    flags = [a for a in argv[1:] if a.startswith("--")]
    slug = preview = None
    if "--css" in argv:
        i = argv.index("--css"); slug = argv[i + 1]; args = [a for a in args if a != slug]
    if "--preview" in argv:
        i = argv.index("--preview"); preview = argv[i + 1]; args = [a for a in args if a != preview]
    if preview:
        import build_tenant_preview
        build_tenant_preview.build(preview); print("wrote", preview); return 0
    if not 1 <= len(args) <= 2:
        print(__doc__); return 2
    res = derive(args[0], args[1] if len(args) > 1 else None)
    if "--json" in flags:
        print(json.dumps(res, indent=2))
    elif slug:
        if res["status"] != "ok":
            print_report(res); return 1
        print(css(slug, res))
    else:
        print_report(res, "--brief" in flags)
    return 0 if res["status"] == "ok" else 1

if __name__ == "__main__":
    sys.exit(main(sys.argv))
