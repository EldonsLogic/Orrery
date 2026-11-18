"""Append-only, in-memory audit of every identity decision. No secrets, tokens
or contact addresses are recorded; only ids, decision and reason code. By
convention `detail` carries only ids and enumerated values: the length cap limits
size, it does not redact personal data. `tenant` and `subject` may come from
caller input, so a value that is not a short string is stored as None."""

from dataclasses import dataclass
from typing import Optional

MAX_DETAIL = 200
MAX_ID = 256
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


def _bounded_id(value) -> Optional[str]:
    return value if isinstance(value, str) and 0 < len(value) <= MAX_ID else None


class AuditLog:
    """Only `record` adds; nothing edits or removes. `events` returns a copy."""

    def __init__(self):
        self._events: list = []

    def record(self, *, at: int, action: str, decision: str, code: str, realm: str,
               subject: Optional[str], tenant: Optional[str], detail: str = "") -> AuditEvent:
        if decision not in (ALLOW, DENY):
            raise ValueError("decision must be allow or deny")
        event = AuditEvent(len(self._events) + 1, at, action, decision, code, realm,
                           _bounded_id(subject), _bounded_id(tenant),
                           "" if detail is None else str(detail)[:MAX_DETAIL])
        self._events.append(event)
        return event

    def events(self) -> tuple:
        return tuple(self._events)

    def for_tenant(self, tenant_id: str) -> tuple:
        """Tenant-visible slice (support grants and access must be visible to the tenant)."""
        return tuple(e for e in self._events if e.tenant == tenant_id)
