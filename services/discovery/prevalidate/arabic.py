"""Comparison keys for matching names. The original display spelling is never changed.

`normalise_arabic` is for matching only. Steps: NFKC; remove bidi, zero-width and tag
controls; remove tatweel and diacritics; unify alef forms; ta marbuta to ha; alef maqsura
and Farsi yeh to ya; Farsi kaf to kaf; Arabic-Indic and Eastern digits to ASCII; lower-case
Latin; punctuation to spaces; collapse whitespace; strip leading and trailing business
words from BUSINESS_WORDS (data, below). Hamza on waw or ya is NOT unified (kept distinct).
"""
from __future__ import annotations

import re
import unicodedata

# Data list. Edit here; each entry is normalised with the same steps before use.
BUSINESS_WORDS = (
    "مؤسسة", "شركة", "مؤسسه", "شركه", "مؤسسة تجارية",
    "est", "est.", "establishment", "co", "co.", "company", "ltd", "ltd.", "limited",
    "llc", "l.l.c", "l.l.c.", "inc", "inc.", "trading",
)

_BIDI = set(range(0x202A, 0x202F)) | set(range(0x2066, 0x206A)) | {0x200E, 0x200F, 0x061C}
_ZW = {0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x180E, 0x00AD}
_DROP = _BIDI | _ZW | set(range(0xE0000, 0xE0080)) | {0x0640} | set(range(0x064B, 0x0660)) | {0x0670} | set(range(0x06D6, 0x06EE))
_MAP = {0x0622: "ا", 0x0623: "ا", 0x0625: "ا", 0x0671: "ا", 0x0629: "ه", 0x0649: "ي", 0x06CC: "ي", 0x06A9: "ك"}
_MAP.update({0x0660 + i: str(i) for i in range(10)})
_MAP.update({0x06F0 + i: str(i) for i in range(10)})
_PUNCT = re.compile(r"[^\w\s]|_", re.UNICODE)


def _base(text: str) -> str:
    t = unicodedata.normalize("NFKC", text)
    out = []
    for ch in t:
        o = ord(ch)
        if o in _DROP:
            continue
        out.append(_MAP.get(o, ch))
    t = "".join(out).lower()
    t = _PUNCT.sub(" ", t)
    return " ".join(t.split())


def _word_tuples():
    seen = []
    for w in BUSINESS_WORDS:
        tup = tuple(_base(w).split())
        if tup and tup not in seen:
            seen.append(tup)
    return sorted(seen, key=lambda t: (-len(t), t))


_WORDS = _word_tuples()


def tokens(text: str) -> tuple:
    """Comparison tokens with business words stripped at the edges (never to empty)."""
    toks = _base(text).split()
    cur = list(toks)
    changed = True
    while changed and cur:
        changed = False
        for w in _WORDS:
            n = len(w)
            if len(cur) > n and tuple(cur[:n]) == w:
                cur = cur[n:]
                changed = True
                break
            if len(cur) > n and tuple(cur[-n:]) == w:
                cur = cur[:-n]
                changed = True
                break
    return tuple(cur)


def normalise_arabic(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("text must be str")
    return " ".join(tokens(text))
