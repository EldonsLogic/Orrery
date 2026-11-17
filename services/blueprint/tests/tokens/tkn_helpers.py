"""Independent WCAG maths for the tests (deliberately not importing the brand tools)."""
import re

SURFACES = ("--color-background", "--color-surface", "--color-surface-raised")


def _lin(v):
    v /= 255.0
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def rgb(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def lum(h):
    r, g, b = (_lin(v) for v in rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(a, b):
    hi, lo = sorted([lum(a), lum(b)], reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def parse(value):
    """'#RRGGBB' -> (hex, 1.0); 'rgba(r,g,b,a)' -> (hex, a)."""
    m = re.fullmatch(r"rgba\((\d+),(\d+),(\d+),([0-9.]+)\)", value)
    if m:
        return "#%02X%02X%02X" % tuple(int(m.group(i)) for i in (1, 2, 3)), float(m.group(4))
    return value.upper(), 1.0


def over(value, bg):
    h, a = parse(value)
    return "#%02X%02X%02X" % tuple(round(b + (f - b) * a) for f, b in zip(rgb(h), rgb(bg)))


def aa_failures(resolved_theme):
    """List of (name, ratio, minimum) failing for one theme of ResolvedTokens.resolved."""
    t = resolved_theme
    out = []

    def chk(name, fg, bg, mn):
        r = ratio(fg, bg)
        if r + 1e-9 < mn:
            out.append((name, round(r, 3), mn))

    primary = parse(t["--color-primary"])[0]
    for s in SURFACES:
        sv = t[s]
        chk(f"link/{s}", primary, sv, 4.5)
        chk(f"visited/{s}", t["--color-link-visited"], sv, 4.5)
        chk(f"ring/{s}", primary, sv, 3.0)
    for k in ("--color-primary", "--color-primary-hover", "--color-primary-pressed"):
        chk(f"label/{k}", t["--color-primary-label"], t[k], 4.5)
    for k in ("--state-secondary-hover", "--state-secondary-pressed"):
        for s in ("--color-background", "--color-surface"):
            chk(f"{k}/{s}", primary, over(t[k], t[s]), 4.5)
    chk("selected/surface", primary, over(t["--state-selected"], t["--color-surface"]), 4.5)
    for s in ("--color-background", "--color-surface"):
        chk(f"accent/{s}", t["--color-accent"], t[s], 3.0)
    return out
