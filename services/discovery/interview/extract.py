"""Deterministic helpers: language, intake cleaning, rule-based answer parsing, grounding check."""
from __future__ import annotations

import re
from typing import Any, Optional

from connectors.detect import instruction_hits
from connectors.sanitise import comparison_copy, strip_controls

from .catalog import Question

MAX_OWNER_TEXT = 4000
MAX_DOC_TEXT = 20000
_AR = re.compile(r"[؀-ۿ]")
_LAT = re.compile(r"[A-Za-z]")
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
YES = {"yes", "y", "yeah", "yep", "sure", "correct", "true", "ok", "okay", "نعم", "ايوه", "ايوا", "اي", "ايه",
       "صح", "طبعا", "بلي", "اكيد", "تمام"}
NO = {"no", "n", "nope", "false", "لا", "كلا", "لأ", "لاء", "مو", "مش"}
UNKNOWN = ("i dont know", "i do not know", "not sure", "no idea", "dont know", "skip", "later",
           "لا اعرف", "ما اعرف", "مش عارف", "مو متاكد", "لست متاكد", "ما ادري", "لا ادري", "تخطي", "لاحقا", "مدري")
_NUM = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?(?![\w])")


def detect_language(text: str, fallback: str = "en") -> str:
    ar, lat = len(_AR.findall(text)), len(_LAT.findall(text))
    if ar == 0 and lat == 0:
        return fallback
    return "ar" if ar >= lat else "en"


def clean_untrusted(text: Any, limit: int) -> tuple:
    """(clean text, injection hits). The text is data: stripped of invisible characters and capped."""
    if not isinstance(text, str):
        return "", []
    clean, _ = strip_controls(text)
    clean = clean[:limit]
    return clean, instruction_hits(comparison_copy(clean))


def _norm(text: str) -> str:
    return " ".join(_WORD.findall(comparison_copy(text).replace("'", "").replace("\u2019", "")))


def is_unknown(text: str) -> bool:
    n = _norm(text)
    return any(p in n for p in UNKNOWN)


def numbers(text: str) -> list:
    out = []
    for m in _NUM.findall(comparison_copy(text)):
        try:
            out.append(float(m.replace(",", "")))
        except ValueError:
            pass
    return out


def parse_deterministic(q: Question, text: str) -> Optional[dict]:
    """A {key: value} dict when a simple rule decides the answer unambiguously, else None (ask the model)."""
    n = _norm(text)
    toks = n.split()
    if q.type == "boolean" and 0 < len(toks) <= 3:
        yes, no = any(t in YES for t in toks), any(t in NO for t in toks)
        if yes != no:
            return {q.keys[0]: yes}
    elif q.type == "choice":
        hits = [v for v, labels in q.options
                if any(_norm(str(x)) and _norm(str(x)) in n for x in (v, labels.get("ar", ""), labels.get("en", "")))]
        if len(hits) == 1:
            return {q.keys[0]: hits[0]}
    elif q.type in ("integer", "number"):
        nums = numbers(text)
        if len(nums) == 1 and (q.type == "number" or nums[0].is_integer()):
            return {q.keys[0]: int(nums[0]) if q.type == "integer" else nums[0]}
    return None


def grounded(q: Question, values: dict, text: str) -> bool:
    """Free-text and numeric values must appear in what the owner wrote; models may not invent them."""
    if q.type in ("text", "text_pair"):
        hay = _norm(text)
        return all(_norm(str(v)) in hay for v in values.values())
    if q.type in ("integer", "number"):
        have = numbers(text)
        return all(float(v) in have for v in values.values())
    return True
