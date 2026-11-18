"""Append-only, in-memory audit of every identity decision. No secrets, tokens
or contact addresses are recorded; only ids, decision and reason code."""

from dataclasses import dataclass
from typing import Optional

MAX_DETAIL = 200
ALLOW = "allow"
DENY = "deny"


@dataclass(frozen=True)
class AuditEvent:
    seq: int
    at: int
    action: str
    decision: str  # allow | deny
    code: str  # "OK" or an IDN-xxx code
    realm: str
    subject: Optional[str]
    tenant: Optional[str]
    detail: str = ""


class AuditLog:
    """Only `record` adds; nothing edits or removes. `events` returns a copy."""

    def __init__(self):
        self._events: list = []

    def record(self, *, at: int, action: str, decision: str, code: str, realm: str,
               subject: Optional[str], tenant: Optional[str], detail: str = "") -> AuditEvent:
        if decision not in (ALLOW, DENY):
            raise ValueError("decision must be allow or deny")
        event = AuditEvent(len(self._events) + 1, at, action, decision, code, realm,
                           subject, tenant, str(detail)[:MAX_DETAIL])
        self._events.append(event)
        return event

    def events(self) -> tuple:
        return tuple(self._events)

    def for_tenant(self, tenant_id: str) -> tuple:
        """Tenant-visible slice (support grants and access must be visible to the tenant)."""
        return tuple(e for e in self._events if e.tenant == tenant_id)
