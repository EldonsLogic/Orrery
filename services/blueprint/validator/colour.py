"""WCAG 2.x contrast maths and lightness auto-adjust (rule 10)."""
from __future__ import annotations

import colorsys
import re

HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
# Auto-adjust may move HSL lightness by at most this much; beyond it the colour is rejected.
MAX_LIGHTNESS_SHIFT = 0.30
_STEP = 0.005


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    h = hex_colour.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def luminance(hex_colour: str) -> float:
    def lin(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(c) for c in _rgb(hex_colour))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def passes_all(colour: str, backgrounds: list[str], threshold: float) -> bool:
    return all(contrast(colour, bg) >= threshold for bg in backgrounds)


def _with_lightness(hex_colour: str, lightness: float) -> str:
    r, g, b = (c / 255 for c in _rgb(hex_colour))
    h, _l, s = colorsys.rgb_to_hls(r, g, b)
    nr, ng, nb = colorsys.hls_to_rgb(h, min(1.0, max(0.0, lightness)), s)
    return "#{:02X}{:02X}{:02X}".format(round(nr * 255), round(ng * 255), round(nb * 255))


def lightness(hex_colour: str) -> float:
    r, g, b = (c / 255 for c in _rgb(hex_colour))
    return colorsys.rgb_to_hls(r, g, b)[1]


def auto_adjust(hex_colour: str, backgrounds: list[str], threshold: float) -> str | None:
    """Nearest colour with the same hue and saturation that passes against every background.

    Searches lightness in both directions in 0.5% steps up to MAX_LIGHTNESS_SHIFT and returns the
    smallest shift that passes (darker wins ties), or None when nothing passes (reject).
    """
    base = lightness(hex_colour)
    steps = int(MAX_LIGHTNESS_SHIFT / _STEP)
    for i in range(1, steps + 1):
        for sign in (-1, 1):
            cand = _with_lightness(hex_colour, base + sign * i * _STEP)
            if passes_all(cand, backgrounds, threshold):
                return cand
    return None
