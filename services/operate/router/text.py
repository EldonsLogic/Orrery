"""Matching-form text normalisation for the router. Pure, stdlib only. Never used to build model output."""
from __future__ import annotations

import re
import unicodedata

_DIGITS = {ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}
_DIGITS.update({ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")})
_MAP = {"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ـ": "", "؟": "?", "،": ","}
_INVISIBLE = re.compile("[​-‏‪-‮⁠-⁤⁦-⁩﻿\U000e0000-\U000e007f]")
MAX_CHARS = 2000  # the router reads at most this much of a turn (cost and ReDoS bound)


def normalise(text) -> str:
    """Lowercase matching form: NFKC, ASCII digits, no diacritics, tatweel or bidi controls, alef unified."""
    if not isinstance(text, str):
        return ""
    t = unicodedata.normalize("NFKC", text[:MAX_CHARS]).translate(_DIGITS)
    t = _INVISIBLE.sub("", t)
    t = "".join(ch for ch in unicodedata.normalize("NFD", t) if unicodedata.category(ch) != "Mn")
    t = "".join(_MAP.get(ch, ch) for ch in t).casefold()
    return re.sub(r"\s+", " ", t).strip()


def has_arabic(text: str) -> bool:
    return any("؀" <= ch <= "ۿ" for ch in text)
