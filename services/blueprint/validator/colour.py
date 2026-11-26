"""WCAG 2.x contrast maths (rule 10). Colour derivation lives in the token resolver (tokens.brand_tools)."""
from __future__ import annotations

import re

# Always use HEX_RE.fullmatch (like the token resolver): "$" would let a trailing newline through.
HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}")


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
