#!/usr/bin/env python3
"""WCAG 2.x contrast check for the pairs on PDF page 8. Reads tokens/tokens.json. Exit 1 on any failure below minimum."""
import json, pathlib, sys
root = pathlib.Path(__file__).resolve().parent.parent
t = json.loads((root / "tokens" / "tokens.json").read_text(encoding="utf-8"))

def lum(h):
    h = h.lstrip("#"); c = [int(h[i:i+2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

def ratio(a, b):
    hi, lo = sorted([lum(a), lum(b)], reverse=True)
    return (hi + 0.05) / (lo + 0.05)

def hexof(mode, ref):
    return ref if ref.startswith("#") else t["color"][mode][ref]["hex"]

fails = 0; mism = 0
print(f"{'pair':52} {'mode':5} {'ratio':>6} {'claimed':>7}  result")
for p in t["claimedContrast"]["pairs"]:
    for mode in ("light", "dark"):
        r = ratio(hexof(mode, p["fg"][mode]), hexof(mode, p["bg"][mode]))
        claimed = p["claimed"][mode]
        ok = r >= p["minimum"]
        match = abs(round(r, 2) - claimed) < 0.005
        fails += not ok; mism += not match
        print(f"{p['label'][:52]:52} {mode:5} {r:6.2f} {claimed:7.2f}  {'PASS' if ok else 'FAIL'}{'' if match else '  (differs from PDF claim)'}")
print(f"\nfailures below minimum: {fails}; claim mismatches: {mism}")
sys.exit(1 if fails else 0)
