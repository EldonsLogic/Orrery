"""Text hygiene for register rows. All row text is untrusted data: it is cleaned, scanned and stored, never
interpreted, evaluated or used as a path or format string."""
from __future__ import annotations

import re
import unicodedata

from .errors import ExceptionsError

_DROP = {"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"}   # control, format (bidi, zero width), surrogate, private, unassigned


def clean(text: str) -> str:
    """NFKC, whitespace runs to one space, control and bidi/format characters removed, trimmed."""
    t = unicodedata.normalize("NFKC", text)
    t = "".join(" " if c.isspace() else c for c in t)
    t = "".join(c for c in t if unicodedata.category(c) not in _DROP)
    return re.sub(" +", " ", t).strip()


_EMAIL = re.compile(r"[^\s@]+@[^\s@]+")
_PHONE = re.compile(r"\+?\(?\d[\d\s().\-]{6,}\d")
_URL_CRED = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*://[^\s/@]*@")
_SECRET_ASSIGN = re.compile(r"(?i)\b(pass(word|wd)?|pwd|secret|token|api[_\-]?key|apikey|auth|bearer|private[_\-]?key)\b\s*[:=]")
_KEY_PREFIX = re.compile(r"(?i)(sk-|pk_|sk_|ghp_|gho_|github_pat_|xox[abpsr]-|akia|asia|eyj|-----begin)")
_TOKEN = re.compile(r"[A-Za-z0-9_\-+=]{16,}")


def _digits(text: str) -> str:
    return "".join(str(unicodedata.digit(c)) for c in text if unicodedata.category(c) == "Nd")


def scan(text: str, column: str) -> None:
    """Refuse text that looks like personal data or a secret. `text` is already cleaned."""
    if _URL_CRED.search(text):
        raise ExceptionsError("EXC-DATA-002", f"{column}: URL with credentials")
    if _EMAIL.search(text):
        raise ExceptionsError("EXC-DATA-001", f"{column}: looks like an email address")
    if _SECRET_ASSIGN.search(text):
        raise ExceptionsError("EXC-DATA-002", f"{column}: looks like a secret assignment")
    if re.search(r"\d(?:[\s.\-]?\d){7,}", text) or len(_digits(text)) >= 9 and _PHONE.search(text):
        raise ExceptionsError("EXC-DATA-001", f"{column}: looks like a phone number or long digit run")
    for tok in _TOKEN.findall(text):
        mixed = len(tok) >= 24 and all(re.search(p, tok) for p in (r"[A-Z]", r"[a-z]", r"\d"))
        if (_KEY_PREFIX.match(tok) and re.search(r"\d", tok)) or mixed:
            raise ExceptionsError("EXC-DATA-002", f"{column}: looks like a key or token")
    if _KEY_PREFIX.search(text) and re.search(r"-----BEGIN", text, re.I):
        raise ExceptionsError("EXC-DATA-002", f"{column}: looks like a private key")
