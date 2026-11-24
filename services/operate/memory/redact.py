"""Redact IDs and refuse secrets before a memory is stored. Detection runs on a digit-normalised copy so Arabic-Indic
digits are caught too. A secret is refused (`secret_detected`), not masked: a masked remnant can still leak. IDs
(e-mail, IBAN, phone, card and long digit runs) are masked. Any internal error is the caller's `invalid_input`."""
from __future__ import annotations

import re
import unicodedata

from .errors import MemoryRefused

MARK = "[redacted]"
_KEY = (r"p[a@4]ssw[o0]rd|pwd|passphrase|secret|api[_ -]?key|token|كلم[ةه]\s*(?:ال)?(?:سر|مرور)|الرمز\s*السري|"
        r"(?:ال)?باسورد")
_SHORT = r"\b(?:pass|passcode|pin|otp|cvv|cvc)\b\s*(?:is|=|:|-|are)|\b(?:pin|otp|cvv|cvc)\b\s*\d|\bpw\b\s*(?:is|=|:|-)?\s*\S+"
_SECRET = re.compile(
    rf"(?i)(?:{_KEY})\s*(?:is|=|:|-|هي|هو)?\s*\S+|{_SHORT}"
    r"|\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"
    r"|\b(?:sk|pk|rk|ghp|gho|xox[abp])[-_][A-Za-z0-9_-]{6,}"
    r"|\bAKIA[0-9A-Z]{16}\b"
    r"|\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|\b[A-Za-z0-9+/_-]{32,}={0,2}"
    r"|\b(?=[A-Za-z0-9+/]*\d)[A-Za-z0-9+/]{10,}(?:\s+[A-Za-z0-9+/]{10,})+")
_ID = re.compile(r"[^\s@]+\s*@\s*[^\s@]+\.[^\s@]+|\S+\s*[(\[]\s*at\s*[)\]]\s*\S+\.\w+|\S+\s*(?:\s(?:at)\s|[(\[]\s*at\s*[)\]])\s*\S+\s*(?:\s(?:dot)\s|[(\[]\s*dot\s*[)\]])\s*\w+|\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b|"
                 r"\+?\d[\d\s().\-/]{4,}\d")
_SPLIT_CARD = re.compile(r"\d{4}[^\d\n]{1,3}\d{4}[^\d\n]{1,3}\d{4}[^\d\n]{1,3}\d{1,4}")
_DATE = re.compile(r"(?:19|20)\d{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])(?:[T ][\d:.]+(?:Z|[+-]\d{2}:\d{2})?)?")


def _digits(text: str) -> str:
    """Same length; decimal digits of any script mapped to ASCII (other digit-like marks such as a superscript two
    are left alone), so spans line up with the original."""
    return "".join(str(unicodedata.decimal(c)) if c.isdecimal() and not c.isascii() else c for c in text)


def redact(text: str) -> tuple:
    """Return (text, flags). Raises MemoryRefused("secret_detected") for a secret, ("invalid_input") on any fault."""
    try:
        norm = _digits(text)
        if _SECRET.search(norm):
            raise MemoryRefused("secret_detected")
        flags, out, pos = set(), [], 0
        for m in _ID.finditer(norm):
            if _DATE.fullmatch(m.group(0).strip()) or m.start() < pos:
                continue
            out += [text[pos:m.start()], MARK]
            pos = m.end()
            flags.add("id_redacted")
        out.append(text[pos:])
        rest = _digits("".join(out))
        if _SPLIT_CARD.search(rest):
            raise MemoryRefused("secret_detected")  # digits split by letters: a card or account in disguise
        return "".join(out), tuple(sorted(flags))
    except MemoryRefused:
        raise
    except Exception:
        raise MemoryRefused("invalid_input") from None
