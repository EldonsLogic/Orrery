"""Section 3.3 sanitisation: deterministic, pure functions."""
from __future__ import annotations

import re
import unicodedata

BIDI = set(range(0x202A, 0x202F)) | set(range(0x2066, 0x206A)) | {0x200E, 0x200F, 0x061C}
ZERO_WIDTH = {0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x180E, 0x00AD}
TAGS = range(0xE0000, 0xE0080)
# Other default-ignorable / invisible format characters (F3): variation selectors, fillers, invisible
# operators, combining grapheme joiner, Khmer inherent vowels, Mongolian selectors, musical formatting.
# ZWJ/ZWNJ stay in ZERO_WIDTH (stripped and flagged; the Arabic/Persian joiner question is open).
INVISIBLE = ({0x034F, 0x115F, 0x1160, 0x17B4, 0x17B5, 0x3164, 0xFFA0, 0x180B, 0x180C, 0x180D, 0x180F}
             | set(range(0x2061, 0x2065)) | set(range(0xFE00, 0xFE10)) | set(range(0xE0100, 0xE01F0))
             | set(range(0xFFF0, 0xFFF9)) | set(range(0x1D173, 0x1D17B)))
_KEEP_CC = {0x09, 0x0A, 0x0D}
_DIGITS = {**{0x0660 + i: ord("0") + i for i in range(10)}, **{0x06F0 + i: ord("0") + i for i in range(10)}}
_ARABIC_NORM = {0x0623: 0x0627, 0x0625: 0x0627, 0x0622: 0x0627, 0x0649: 0x064A, 0x0640: None}
# Small confusable table (Cyrillic and Greek look-alikes to Latin). A subset of UTS #39 data.
_CONF = {ord(k): v for k, v in {
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j", "ѕ": "s",
    "ԁ": "d", "һ": "h", "ո": "n", "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O",
    "Р": "P", "С": "C", "Т": "T", "Х": "X", "α": "a", "ο": "o", "ρ": "p", "ν": "v", "ι": "i", "κ": "k",
    "τ": "t", "ѡ": "w", "ԛ": "q", "ԝ": "w", "ɡ": "g", "ⅼ": "l", "І": "I", "Ј": "J", "Ѕ": "S", "ᴏ": "o", "օ": "o", "ս": "u",
    "ա": "w", "ց": "g", "ʋ": "v", "ɑ": "a", "ӏ": "l", "ǀ": "l", "Ι": "I", "Ζ": "Z", "Μ": "M", "Ν": "N", "Υ": "Y", "Κ": "K",
    "Η": "H", "Ѵ": "V", "υ": "u", "Α": "A", "Β": "B", "Ε": "E", "Ο": "O", "Ρ": "P", "Τ": "T", "Χ": "X",
}.items()}
_SCRIPTS = ("LATIN", "CYRILLIC", "GREEK", "ARABIC", "HEBREW", "ARMENIAN")
_TOKEN = re.compile(r"[^\W_]+(?:[.\-@][^\W_]+)*", re.UNICODE)


def strip_controls(text: str) -> tuple:
    """Return (clean, counts) removing bidi, zero-width, tag, other invisible and control characters.
    VS15/VS16 are kept only directly after a symbol (emoji presentation)."""
    counts = {"bidi": 0, "zero_width": 0, "unicode_tag": 0, "invisible": 0, "control": 0}
    out = []
    for ch in text:
        o = ord(ch)
        if o in (0xFE0E, 0xFE0F) and out and unicodedata.category(out[-1]) == "So":
            out.append(ch)
        elif o in INVISIBLE:
            counts["invisible"] += 1
        elif unicodedata.category(ch) == "Cc" and o not in _KEEP_CC:
            counts["control"] += 1
        elif o in BIDI:
            counts["bidi"] += 1
        elif o in ZERO_WIDTH:
            counts["zero_width"] += 1
        elif o in TAGS:
            counts["unicode_tag"] += 1
        else:
            out.append(ch)
    return "".join(out), counts


def comparison_copy(text: str) -> str:
    """Comparison copy only: digits to ASCII, diacritics and tatweel dropped, alef forms unified.
    The display copy is never changed by this. (Q-C: no NFKC, to keep presentation forms intact.)"""
    out = []
    for ch in text.translate(_DIGITS):
        o = ord(ch)
        if 0xFF01 <= o <= 0xFF5E or 0x1D400 <= o <= 0x1D7FF:  # fullwidth, math alphanumerics (F7)
            ch = unicodedata.normalize("NFKC", ch)
        o = ord(ch[0])
        if o in _ARABIC_NORM:
            if _ARABIC_NORM[o] is None:
                continue
            ch = chr(_ARABIC_NORM[o])
        elif unicodedata.category(ch[0]) == "Mn":
            continue
        out.append(ch)
    return "".join(out).casefold()


def _script(ch: str) -> str:
    if not ch.isalpha():
        return ""
    name = unicodedata.name(ch, "")
    for s in _SCRIPTS:
        if name.startswith(s):
            return s
    return "OTHER"


def skeleton(token: str) -> str:
    """Confusable skeleton: compatibility-fold (fullwidth, math alphanumerics, ligatures), then map
    the look-alike table, then casefold."""
    return unicodedata.normalize("NFKC", token).translate(_CONF).casefold()


def script_flags(text: str, protected: tuple) -> list:
    """`mixed_script` for tokens mixing scripts; `confusable` when a token's skeleton equals a
    protected name but the token itself does not."""
    flags = set()
    prot = {p.casefold() for p in protected}
    for tok in _TOKEN.findall(text):
        scripts = {_script(c) for c in tok} - {""}
        if len(scripts) > 1:
            flags.add("mixed_script")
        sk = skeleton(tok)
        if sk != tok.casefold() and sk in prot:
            flags.add("confusable")
    whole = text.strip()
    if whole and skeleton(whole) != whole.casefold() and skeleton(whole) in prot:
        flags.add("confusable")
    return sorted(flags)
