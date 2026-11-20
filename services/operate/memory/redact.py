"""Redact obvious secrets and identifiers before a memory is stored. Detection runs on a digit-normalised copy so
Arabic-Indic digits are caught too. Redaction only removes; it never adds text."""
from __future__ import annotations

import re

from runtime.untrusted import _DATE, _SENSITIVE_VALUE

MARK = "[redacted]"
_SECRET = re.compile(
    r"(?i)\b(?:password|passwd|passcode|secret|api[_ -]?key|token|pin|otp|cvv|"
    r"كلمة\s*(?:ال)?(?:سر|مرور)|رمز|الرمز)\b\s*(?:is|=|:|هي|هو)?\s*\S+"
    r"|\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"
    r"|\b(?:sk|pk|rk|ghp|gho|xox[abp])[-_][A-Za-z0-9_-]{12,}"
    r"|\bAKIA[0-9A-Z]{16}\b"
    r"|\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|\b[A-Za-z0-9+/_-]{32,}={0,2}")


def _digits(text: str) -> str:
    """Same length, Arabic-Indic and extended digits mapped to ASCII, so spans line up with the original."""
    return "".join(str(int(c)) if c.isdigit() and not c.isascii() else c for c in text)


def redact(text: str) -> tuple:
    """Return (text, flags). flags contains "secret_redacted" and/or "id_redacted"."""
    flags = set()
    norm = _digits(text)
    spans = []
    for m in _SECRET.finditer(norm):
        spans.append((m.start(), m.end(), "secret_redacted"))
    for m in _SENSITIVE_VALUE.finditer(norm):
        if not _DATE.fullmatch(m.group(0)):
            spans.append((m.start(), m.end(), "id_redacted"))
    out, pos = [], 0
    for s, e, flag in sorted(spans):
        if e <= pos:
            continue
        out.append(text[pos:s] if s >= pos else "")
        out.append(MARK)
        pos = e
        flags.add(flag)
    out.append(text[pos:])
    return "".join(out), tuple(sorted(flags))
