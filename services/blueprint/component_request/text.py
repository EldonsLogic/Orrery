"""Text hygiene and scope scans. All text from a Blueprint or a model is untrusted data."""
from __future__ import annotations

import re
import unicodedata

from exceptions.errors import ExceptionsError  # noqa: E402  (services/blueprint is on the path)
from exceptions.sanitize import clean, scan  # noqa: E402

__all__ = ["clean", "slug", "injection", "scope_hits", "per_client", "personal_data"]

_INJECTION = re.compile(
    r"(?i)(ignore (all |any |the )?(previous|prior|above)|disregard|system prompt|you are (now )?an? |new instructions?|"
    r"override|jailbreak|<\|?\s*(system|im_start|assistant)|\[/?inst\]|```|assistant\s*:|system\s*:|developer\s*:|"
    r"approve (this|it)|auto[- ]?approve|mark (it )?(as )?approved|call (the )?tool|execute|eval\(|rm -rf|curl |http://|https://)"
    r"|تجاهل|تعليمات (جديدة|النظام)|وافق على")
_SCOPE_EN = re.compile(
    r"\b(ledgers?|gl|journals?|tax|taxes|taxable|taxation|vat|zakat|zatca|fatoora|einvoic\w*|e invoic\w*|"
    r"electronic invoic\w*|payroll|payslips?|wps|gosi|salary|salaries|gratuity|end of service|audit\w*)\b")
_SCOPE_AR = ("ضريب", "زكا", "دفتر الأستاذ", "دفتر الاستاذ", "قيد يومية", "قيود يومية", "رواتب", "راتب", "مسير", "تدقيق",
             "مراجعة حسابات", "فاتورة إلكترونية", "فاتورة الكترونية", "الفوترة الإلكترونية", "نهاية الخدمة", "التأمينات")
_CLIENT_EN = re.compile(r"\b(only for|specific to|custom for|bespoke|client specific|customer specific|tenant specific|"
                        r"one off|per client|per tenant|for one client|for our client)\b")
_CLIENT_AR = ("خاص بالعميل", "لعميل واحد", "مخصص لعميل", "خاص بالشركة")
_URL = re.compile(r"(?i)(https?://|www\.)\S+")


def _words(text: str) -> str:
    t = unicodedata.normalize("NFKC", text)
    t = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", t).lower()
    return re.sub(r"[^a-z0-9؀-ۿ]+", " ", t)


def injection(text: str) -> bool:
    return bool(_INJECTION.search(unicodedata.normalize("NFKC", text)))


def scope_hits(*texts: str) -> list[str]:
    """Forbidden-scope terms found (ledger, tax, e-invoicing, payroll maths, audit). Empty list means none seen."""
    found: set[str] = set()
    for t in texts:
        w = _words(t)
        found.update(m.group(0) for m in _SCOPE_EN.finditer(w))
        found.update(a for a in _SCOPE_AR if a in w or a in unicodedata.normalize("NFKC", t))
    return sorted(found)


def per_client(text: str) -> bool:
    w = _words(text)
    return bool(_CLIENT_EN.search(w)) or any(a in unicodedata.normalize("NFKC", text) for a in _CLIENT_AR)


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
