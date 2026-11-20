"""Closed set of refusal codes. No free text: a refusal never echoes the content it refused."""
from __future__ import annotations

CODES = frozenset({"invalid_scope", "invalid_input", "kind_not_allowed", "too_large", "empty_after_redaction",
                   "quota_exceeded", "clock_invalid", "not_found", "audit_failed", "store_failed",
                   "not_unverified"})


class MemoryRefused(Exception):
    def __init__(self, code: str):
        assert code in CODES
        super().__init__(code)
        self.code = code
