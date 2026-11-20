"""Text hygiene and scope scans. All text from a Blueprint or a model is untrusted data."""
from __future__ import annotations

import re
import unicodedata

from exceptions.errors import ExceptionsError  # noqa: E402  (services/blueprint is on the path)
from exceptions.sanitize import clean, scan  # noqa: E402

__all__ = ["clean", "slug", "injection", "scope_hits", "per_client", "personal_data", "fold", "tokens", "foreign_letters"]

_INJECTION = re.compile(
    r"(?i)(ignore (all |any |the )?(previous|prior|above)|disregard|system prompt|you are (now )?an? |new instructions?|"
    r"override|jailbreak|<\|?\s*(system|im_start|assistant)|\[/?inst\]|```|assistant\s*:|system\s*:|developer\s*:|"
    r"approve (this|it)|auto[- ]?approve|mark (it )?(as )?approved|call (the )?tool|execute|eval\(|rm -rf|curl |http://|https://)"
    r"|تجاهل|تعليمات (جديدة|النظام)|وافق على")
_CLIENT_EN = re.compile(r"\b(only for|just for|exclusively|tailored to|specific to|custom for|bespoke|client specific|customer specific|"
                        r"tenant specific|one off|per client|per tenant|for one client|for our client|"
                        r"for (this|that|the) (client|customer|company|tenant|branch))\b")
_CLIENT_AR = ("خاص بالعميل", "لعميل واحد", "مخصص لعميل", "خاص بالشركة", "لشركتنا", "لهذا العميل", "لهذه الشركة")
_URL = re.compile(r"(?i)(https?://|www\.)\S+")


def injection(text: str) -> bool:
    return bool(_INJECTION.search(unicodedata.normalize("NFKC", text)))


def per_client(text: str) -> bool:
    t = unicodedata.normalize("NFKC", text)
    return bool(_CLIENT_EN.search(_split_words(t))) or any(a in t for a in _CLIENT_AR)


def personal_data(text: str) -> bool:
    """True when text looks like personal data, a secret or a URL (a spec must be tenant neutral)."""
    t = clean(text)
    if _URL.search(t):
        return True
    try:
        scan(t, "text")
    except ExceptionsError:
        return True
    return False


def slug(text: str, limit: int = 60) -> str:
    """Id-safe form of an untrusted reference: ASCII a-z0-9_ only, starts with a letter, may be empty."""
    t = unicodedata.normalize("NFKD", text)
    t = re.sub(r"[^a-z0-9]+", "_", t.lower()).strip("_")[:limit].strip("_")
    return t if t and t[0].isalpha() else ""


# ---- scope detection (backstop only: the structural control is policy.py, which derives the risk class) -------------------
_AR_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي", "ی": "ي", "ئ": "ي", "ؤ": "و", "ک": "ك", "ۀ": "ه"})
_CONFUSABLE = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "к": "k", "і": "i", "ј": "j", "ѕ": "s", "һ": "h",
    "т": "t", "м": "m", "н": "h", "в": "b", "ԁ": "d", "ɡ": "g", "ɑ": "a", "ο": "o", "α": "a", "ν": "v", "τ": "t", "ρ": "p",
    "ι": "i", "κ": "k", "χ": "x", "υ": "u", "ε": "e", "ʏ": "y", "ꜱ": "s", "ı": "i"})
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})
_CAMEL = re.compile(r"([a-z0-9])([A-Z])")
_CAMEL2 = re.compile(r"([A-Z]+)([A-Z][a-z])")
_SPLIT = re.compile(r"[^a-z0-9ء-ي]+")
_EN_TOKEN = re.compile(
    r"^(ledgers?|gl|journals?|tax(es|able|ation|ed|code|codes|rate|rates|id|ids)?|vat|zakat|zatca|fatoora|einvoic\w*|payrolls?|"
    r"payslips?|wages?|remunerations?|salary|salaries|gratuity|eosb|wps|gosi|audit\w*|bookkeep\w*|withholding|excise|accounting|"
    r"accountants?|accruals?|reconcil\w*)$")
_EN_CONCAT = ("payroll", "payslip", "ledger", "zatca", "fatoora", "einvoic", "electronicinvoic", "bookkeep", "remuneration", "gratuity",
              "endofservice", "chartofaccounts", "trialbalance", "grosspay", "netpay", "salestax", "taxcode", "taxrate", "taxid",
              "auditlog", "audittrail", "withholdingtax", "wagesheet")
_AR_STEMS = ("ضريب", "زكا", "دفتر", "قيد", "قيود", "رواتب", "راتب", "مسير", "تدقيق", "محاسب", "فوتر", "فاتور", "اجور", "تاميني")
_AR_CONCAT = ("دفترالاستاذ", "نهايهالخدمه", "فاتورهالكترونيه", "قيديوميه", "مراجعهحسابات")


def fold(text: str) -> str:
    """Normal form for matching: NFKC, tatweel, harakat and format characters removed, Arabic variants and common
    Latin look-alikes (Cyrillic, Greek) folded, lower case. Used for detection only, never stored."""
    t = _CAMEL2.sub(r"\1 \2", _CAMEL.sub(r"\1 \2", unicodedata.normalize("NFKC", text)))
    t = "".join(c for c in t if unicodedata.category(c) not in ("Cf", "Cc", "Co", "Cn")
                and not (0x64B <= ord(c) <= 0x65F or ord(c) in (0x640, 0x670)))
    return t.translate(_AR_FOLD).lower().translate(_CONFUSABLE)


def _split_words(text: str) -> str:
    return " ".join(w for w in _SPLIT.split(fold(text)) if w)


def tokens(text: str) -> list[str]:
    return [w for w in _split_words(text).split(" ") if w]


def foreign_letters(text: str) -> bool:
    """True when text has letters that are neither ASCII nor Arabic (Cyrillic, Greek and other look-alike scripts)."""
    for c in unicodedata.normalize("NFKC", text):
        o = ord(c)
        if c.isalpha() and not (c.isascii() or 0x600 <= o <= 0x6FF or 0x750 <= o <= 0x77F or 0xFB50 <= o <= 0xFDFF or 0xFE70 <= o <= 0xFEFF):
            return True
    return False


def scope_hits(*texts: str) -> list[str]:
    """Words for ledger, tax, e-invoicing, payroll maths or audit, after normalising. A backstop: a miss proves nothing."""
    found: set[str] = set()
    for t in texts:
        for variant in (t, t.translate(_LEET)):
            toks = tokens(variant)
            toks_ar = [w[2:] if w.startswith("ال") and len(w) > 4 else (w[1:] if w.startswith("لل") else w) for w in toks]
            concat = "".join(toks)
            found.update(w for w in toks if _EN_TOKEN.match(w))
            found.update(c for c in _EN_CONCAT if c in concat)
            for w in toks_ar:
                found.update(a for a in _AR_STEMS if w.startswith(a))
            found.update(a for a in _AR_CONCAT if a in "".join(toks_ar))
    return sorted(found)
