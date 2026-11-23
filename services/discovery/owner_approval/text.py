"""Untrusted text: owner notes and Blueprint or quote labels are data, never sentences. NFC, no control, bidi,
zero-width or other format characters, at most MAX_MARKS combining marks in a row, trimmed and length-capped, so a note
cannot reorder, hide or smear what a screen shows."""
from __future__ import annotations

import unicodedata

NOTE_LIMIT = 1000
MAX_MARKS = 3
_DROP = ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp")


def clean_cut(value, cap: int = 120) -> tuple:
    """(text, cut): `cut` is True when the text was shortened to fit `cap`."""
    if type(value) is not str:
        return "", False
    t = unicodedata.normalize("NFC", value[:cap * 8])
    out, marks = [], 0
    for c in t:
        cat = unicodedata.category(c)
        if c not in "\n\t" and cat in _DROP:
            continue
        if cat in ("Mn", "Mc", "Me"):
            marks += 1
            if marks > MAX_MARKS:
                continue
        else:
            marks = 0
        out.append(" " if c in "\n\t" else c)
    text = " ".join("".join(out).split())
    return text[:cap], len(text) > cap or len(value) > cap * 8


def clean(value, cap: int = 120) -> str:
    return clean_cut(value, cap)[0]


def note(value) -> str:
    """A note is optional text. One character over the limit survives so the caller can refuse it (never silently cut)."""
    return clean(value, NOTE_LIMIT + 1) if type(value) is str else ""
