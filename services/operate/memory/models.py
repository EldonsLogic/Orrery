"""Memory entry and scope. An entry is DATA: it has no field that can carry authority, a tool name or a role."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import MemoryRefused

_ID = re.compile(r"[A-Za-z0-9_.:-]{1,64}")
# Closed kinds: short preferences, terminology and plain facts. Recipients, bank details, rates, rules, permissions
# and instructions are not kinds, so they cannot be stored (prompt-injection-defence section 6).
KINDS = frozenset({"preference", "terminology", "fact"})
AUTHORS = frozenset({"user", "assistant"})
VERIFIED, UNVERIFIED = "verified", "unverified"


def check_id(value) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise MemoryRefused("invalid_scope")
    return value


@dataclass(frozen=True)
class Scope:
    """Whose memory. Both ids are required and validated; there is no tenant-wide or wildcard scope."""
    tenant_id: str
    user_id: str

    def __post_init__(self):
        check_id(self.tenant_id)
        check_id(self.user_id)


@dataclass(frozen=True)
class MemoryEntry:
    entry_id: str
    tenant_id: str
    user_id: str
    kind: str
    text: str                  # sanitised and redacted before storing
    content_hash: str
    status: str                # verified | unverified
    flags: tuple               # sanitise and redaction flags
    author: str                # user | assistant
    source_turn: str
    source_content_ids: tuple
    created_at: float
    expires_at: float
    confirmed_by: str | None = None
    confirmed_at: float | None = None
