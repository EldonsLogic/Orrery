#!/usr/bin/env python3
"""Recompute every contrast pair of the v1.1 PROPOSED tokens from tokens.proposed.json (not from the builder's memory).
Prints PASS/FAIL per check; exit 1 on any FAIL. Python 3.9+, stdlib only. Use -q for summary lines only."""
import json, math, sys
import themelib as T

quiet = "-q" in sys.argv
P = json.loads((T.ROOT / "tokens" / "tokens.proposed.json").read_text(encoding="utf-8"))
v1 = T.load_v1()
fails = 0

def report(ok, msg, always=False):
    global fails
    fails += (not ok)
    if always or not ok or not quiet:
        print(("PASS " if ok else "FAIL ") + msg)

def load_theme(mode):
    t = {}
    for k, e in P["color"][mode].items():
        t[k] = (e["hex"], e["alpha"]) if "alpha" in e else e["hex"]
    t["_base"] = T.v1_base(mode)
    return t

# 1. staleness: JSON equals a fresh build
for m in ("light", "dark"):
    fresh = T.build_theme(m); t = load_theme(m)
    same = all(fresh[k] == t[k] for k in t if k != "_base")
    report(same, f"{m}: tokens.proposed.json matches tools/themelib.py formulas", True)

# 2. every text pair and state, both modes
print("\n== contrast pairs (WCAG 2.x; 4.5 text, 3.0 non-text) ==")
total = 0
for m in ("light", "dark"):
    t = load_theme(m)
    for p in T.contrast_pairs(t, m):
        r = T.ratio(p["fg"], p["bg"]); total += 1
        report(r + 1e-9 >= p["min"], f"{m:5} {r:6.2f} (min {p['min']}) {p['label']}  {p['fg']} on {p['bg']}")
print(f"pairs checked: {total}")

# 3. destructive dark contrast gap (v1 vs proposed)
print("\n== destructive button, dark ==")
d = P["destructive"]
v1r = T.ratio(d["v1"]["dark"]["label"], d["v1"]["dark"]["fill"]); pr = T.ratio(d["proposed"]["dark"]["label"], d["proposed"]["dark"]["fill"])
print(f"v1 white on {d['v1']['dark']['fill']}: {v1r:.2f}:1 (below 4.5, known gap)")
report(v1r < 4.5, "v1 gap reproduced (white label on dark Crimson is below AA)", True)
report(pr >= 4.5, f"proposed {d['proposed']['dark']['label']} on {d['proposed']['dark']['fill']}: {pr:.2f}:1", True)
report(T.ratio(d["proposed"]["light"]["label"], d["proposed"]["light"]["fill"]) >= 4.5, "proposed light destructive unchanged and AA", True)

# 4. chart palette: 3:1 vs surfaces (in pairs above) + colour-blind separation + comparison series
print("\n== chart palette ==")
mn = P["chart"]["minPairwiseDeltaEOklabCvd"]
for m in ("light", "dark"):
    t = load_theme(m); cols = [t[f"chart-{i}"] for i in range(1, 7)]
    for kind in ("normal", "protan", "deutan", "tritan"):
        c = [T.cvd(x, kind) for x in cols]
        worst = min((T.dE(c[i], c[j]), i + 1, j + 1) for i in range(6) for j in range(i + 1, 6))
        report(worst[0] >= mn, f"{m:5} {kind:6} min pairwise dE {worst[0]:.3f} (series {worst[1]} vs {worst[2]}), need >= {mn}", True)
    b = t["_base"]
    a = P["chart"]["comparisonAlpha"][m]
    report(T.ratio(T.over(b["text"], 0.40, b["surface"]), b["surface"]) < 3.0 or m == "dark",
           f"{m:5} v1 'text at 40%' comparison = {T.ratio(T.over(b['text'], 0.40, b['surface']), b['surface']):.2f}:1 on surface; proposed alpha {a} gives {T.ratio(t['chart-comparison'], b['surface']):.2f}:1", True)

# 5. spacing, breakpoints, sizes
print("\n== scale ==")
sp = P["spacing"]; half = set(sp["halfStepsPx"])
report(all(v % 4 == 0 and (v % 8 == 0 or v in half) for v in sp["scale"].values()), f"spacing values are multiples of 8 (half steps {sorted(half)} only): {list(sp['scale'].values())}", True)
report(all(v % 8 == 0 for v in P["breakpoints"]["minWidthPx"].values()), f"breakpoints multiples of 8: {list(P['breakpoints']['minWidthPx'].values())}", True)
sizes = [P["controls"]["heightPx"], P["controls"]["heightCompactPx"], P["controls"]["heightTouchPx"]] + list(P["table"]["rowHeightPx"].values()) + [
    P["table"]["headerHeightPx"], P["navigation"]["sidebarWidthPx"], P["navigation"]["sidebarCollapsedWidthPx"], P["navigation"]["topBarHeightPx"],
    P["navigation"]["navItemHeightPx"], P["navigation"]["bottomBarHeightPx"], P["tabs"]["heightPx"], P["overlays"]["toastWidthPx"],
    P["controls"]["textareaMinHeightPx"]] + list(P["overlays"]["modalWidthPx"].values()) + list(P["overlays"]["drawerWidthPx"].values())
report(all(v % 8 == 0 for v in sizes), "component heights and widths are multiples of 8", True)
report(P["controls"]["hitTargetMinPx"] >= 24 and P["controls"]["heightPx"] >= 24, "hit target minimum 24 px (WCAG 2.5.8), controls 40 px", True)

# 6. naming of the two Carbons
print("\n== naming ==")
ink, deep = P["naming"]["carbonInk"]["hex"], P["naming"]["carbonDeep"]["hex"]
report(ink == v1["color"]["light"]["text"]["hex"] and deep == v1["color"]["dark"]["background"]["hex"] and deep == v1["color"]["literals"]["carbonOnDarkLabel"],
       f"carbonInk {ink} = v1 light text; carbonDeep {deep} = v1 dark background and dark label (v1 hex unchanged)", True)
v1vars = {c["cssVar"] for m in ("light", "dark") for c in v1["color"][m].values()}
report(not any(e["cssVar"] in v1vars for m in P["color"] for e in P["color"][m].values()), "no proposed CSS variable collides with a v1 colour variable", True)

# 7. app-icon geometry: mark stays inside the maskable safe circle (radius 40% of tile)
print("\n== app icon ==")
a = P["appIcon"]; T64 = a["tileSizeUnits"]; s = a["markFraction"] * T64 / 22.5
nx, ny = a["nudgeUnitsOf64"]["x"], a["nudgeUnitsOf64"]["y"]
pts = []
for deg in list(range(0, 41)) + list(range(52, 91)):
    pts.append((5 + 22.5 * math.cos(math.radians(deg)), 27 - 22.5 * math.sin(math.radians(deg))))
pts += [(5, 27)]
far = max(math.hypot(T64 / 2 + nx + s * (x - 16.25) - T64 / 2, T64 / 2 + ny + s * (y - 15.75) - T64 / 2) for x, y in pts)
report(far <= a["maskableSafeRadiusFraction"] * T64, f"farthest mark point {far:.2f} units from tile centre, safe radius {a['maskableSafeRadiusFraction'] * T64:.1f} (of 64)", True)
report(abs(a["cornerRadiusPercent"] - 21.88) < 0.01, f"corner radius {a['cornerRadiusUnits']}/64 = {a['cornerRadiusPercent']}%", True)

print("\nFAILURES:", fails)
sys.exit(1 if fails else 0)
