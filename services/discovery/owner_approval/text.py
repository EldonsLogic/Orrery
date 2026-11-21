"""Untrusted text: owner notes and Blueprint or quote labels are data, never sentences. NFC, no control, bidi,
zero-width or other format characters, trimmed and length-capped, so a note cannot reorder or hide what a screen shows."""
from __future__ import annotations

import unicodedata

NOTE_LIMIT = 1000
_DROP = ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp")


def clean(value, cap: int = 120) -> str:
    if type(value) is not str:
        return ""
    t = unicodedata.normalize("NFC", value[:cap * 4])
    t = "".join(" " if c in "\n\t" else c for c in t if c in "\n\t" or unicodedata.category(c) not in _DROP)
    return " ".join(t.split())[:cap]


def note(value) -> str:
    """A note is optional text. One character over the limit survives so the caller can refuse it (never silently cut)."""
    return clean(value, NOTE_LIMIT + 1) if type(value) is str else ""
