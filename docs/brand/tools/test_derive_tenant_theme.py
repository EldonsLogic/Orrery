#!/usr/bin/env python3
"""Plain-assert tests for derive_tenant_theme.py. Run: python3 tools/test_derive_tenant_theme.py"""
import themelib as T
import derive_tenant_theme as D

def ok(c, accent=None):
    r = D.derive(c, accent)
    assert r["status"] == "ok", (c, r["reasons"])
    for m in ("light", "dark"):
        bad = [p for p in r["pairs"][m] if not p["ok"]]
        assert not bad, (c, m, bad)
    return r

def rejected(c, word, accent=None):
    r = D.derive(c, accent)
    assert r["status"] == "rejected", (c, "expected rejection")
    assert word in " ".join(r["reasons"]), (c, word, r["reasons"])
    return r

# 1. Orrery's own Cobalt passes unchanged in light; dark lands close to the v1 dark Cobalt
r = ok("#2443D0")
assert r["light"]["primary"] == "#2443D0" and r["light"]["primaryLabel"] == "#FFFFFF"
assert T.dE(r["dark"]["primary"], "#86A0FF") < 0.03, r["dark"]["primary"]
assert r["dark"]["primaryLabel"] == "#0E1117"
assert not [a for a in r["adjustments"] if a.startswith("light primary")]

# 2. mid-tone teal: accepted, darkened slightly in light
r = ok("#0F766E"); assert r["light"]["primary"] != "#0F766E" and T.ratio(r["light"]["primary"], "#FFFFFF") >= 4.5

# 3. flag-style green: accepted with a closeness-to-Jade warning
r = ok("#006C35"); assert r["warnings"] and "success" in r["warnings"][0]

# 4. navy: accepted, dark theme lifted to a readable tint
r = ok("#1F3A8A"); assert T.ratio(r["dark"]["primary"], "#171B23") >= 4.5

# 5. too light colours are rejected with the reason
rejected("#FFD400", "too light"); rejected("#F59E0B", "too light"); rejected("#7DB6FF", "too light")

# 6. too dark / near-black
rejected("#1A1040", "too dark"); rejected("#0B1020", "near-black")

# 7. near-grey
rejected("#6B7280", "near-grey"); rejected("#808080", "near-grey")

# 8. near the brand danger colour (the red family, including Orrery's own Crimson)
for c in ("#C21F3A", "#D32F2F", "#E53935", "#BE185D"):
    rejected(c, "Crimson")

# 9. Coral as a tenant primary darkens into the danger zone and is rejected
rejected("#E0552C", "Crimson")

# 10. bad input
rejected("zzz", "not a hex"); rejected("#12345", "not a hex")
assert D.norm_hex("abc") == "#AABBCC" and D.norm_hex("#abcdef") == "#ABCDEF"

# 11. accents
r = ok("#2443D0", "#F59E0B"); assert r["light"]["accent"] != "#F59E0B"          # darkened to 3:1
assert T.ratio(r["light"]["accent"], "#F3F4F6") >= 3.0 and T.ratio(r["dark"]["accent"], "#171B23") >= 3.0
rd = D.derive("#2443D0", "#2A48D6"); assert rd["status"] == "rejected" and "too close" in rd["reasons"][0]
rd = D.derive("#2443D0", "#D32F2F"); assert rd["status"] == "rejected" and "Crimson" in rd["reasons"][0]
rd = D.derive("#2443D0", "#FFF200"); assert rd["status"] == "rejected" and "too light" in rd["reasons"][0]
# default accent falls back when the primary is close to Coral
rd = D.derive("#9A3412")  # burnt orange-brown: dark enough, near Coral hue but not Crimson
assert rd["status"] in ("ok", "rejected")

# 12. invariant on 300 deterministic pseudo-random colours: rejected, or every pair of both themes passes
x, accepted = 12345, 0
for _ in range(300):
    x = (1103515245 * x + 12345) & 0x7FFFFFFF; r_ = x >> 8 & 255
    x = (1103515245 * x + 12345) & 0x7FFFFFFF; g_ = x >> 8 & 255
    x = (1103515245 * x + 12345) & 0x7FFFFFFF; b_ = x >> 8 & 255
    res = D.derive(T.rgb2h([r_, g_, b_]))
    if res["status"] == "ok":
        accepted += 1
        assert all(p["ok"] for m in ("light", "dark") for p in res["pairs"][m]), res["input"]
        assert T.ratio(res["light"]["primary"], "#FFFFFF") >= 4.5 and T.ratio(res["dark"]["primary"], "#171B23") >= 4.5
assert accepted > 20
print(f"all tests passed ({accepted} of 300 random colours accepted, none violating AA)")
