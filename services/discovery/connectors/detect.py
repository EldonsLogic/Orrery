"""Instruction-like pattern list, English and Arabic. A metric only: it never changes an outcome."""
from __future__ import annotations

import re

# Run on the comparison copy (casefolded, digits ASCII, diacritics and tatweel removed, alef unified).
# `_` is treated as a separator so column names like ignore_all_rules match.
PATTERNS = (
    ("en.ignore_rules", "en", r"\b(ignore|disregard|forget)\s+(all\s+|any\s+|the\s+)?(previous\s+|prior\s+|above\s+)?(rules|instructions)"),
    ("en.role_prefix", "en", r"(^|\n|\s)(system|assistant|developer)\s*:"),
    ("en.you_are_now", "en", r"\byou\s+are\s+now\b"),
    ("en.mark_paid", "en", r"\bmark\s+(this\s+)?invoice\s+(as\s+)?paid\b"),
    ("en.change_bank", "en", r"\b(update|change|replace)\s+(our|the|their|my)?\s*(iban|bank\s+details|account\s+number)\b"),
    ("en.export_data", "en", r"\bexport\s+(all\s+)?(the\s+)?(customers?|data|records)\b"),
    ("en.grant_role", "en", r"\bgrant\s+.{0,40}\b(role|admin|owner|access)\b"),
    ("en.send_to", "en", r"\b(email|send|forward)\s+.{0,40}\bto\s+\S+@\S+"),
    ("en.disable_logging", "en", r"\bdisable\s+(logging|audit)\b"),
    ("ar.ignore_rules", "ar", r"تجاهل\s+(كل\s+)?(التعليمات|القواعد|الاوامر)(\s+السابقه|\s+السابقة)?"),
    ("ar.change_iban", "ar", r"(حدث|غير|استبدل)\s+(رقم\s+)?(الايبان|الحساب)"),
    ("ar.transfer", "ar", r"(حول|ادفع)\s+\d+"),
    ("ar.you_are_now", "ar", r"انت\s+الان"),
    ("ar.system_notice", "ar", r"(تعليمات|اشعار)\s+النظام"),
)
_COMPILED = tuple((i, lang, re.compile(p)) for i, lang, p in PATTERNS)


def instruction_hits(comparison: str) -> list:
    """Return sorted [(pattern_id, lang)] matching the comparison copy."""
    text = comparison.replace("_", " ")
    return sorted({(i, lang) for i, lang, rx in _COMPILED if rx.search(text)})
