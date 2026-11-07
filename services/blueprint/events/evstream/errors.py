"""Error codes, the Issue record and the EventError exception."""
from __future__ import annotations

from dataclasses import dataclass

CODES = {
    "EVS-ENV-001": "envelope violates envelope.schema.json",
    "EVS-ENV-002": "input is not an event object (or an internal failure while checking it)",
    "EVS-TYPE-001": "unknown event type (a warning when consuming; an error when producing)",
    "EVS-TYPE-002": "schema_version differs from the registry (data not checked; warning)",
    "EVS-DATA-001": "data violates the type's data schema",
    "EVS-DATA-002": "data too large (bytes or node count)",
    "EVS-DATA-003": "data nested too deep",
    "EVS-DATA-004": "data looks like a whole record (too many keys, or a whole-record key or marker)",
    "EVS-DATA-005": "data holds a value that is not plain JSON",
    "EVS-DATA-006": "personal or financial data breaks the minimisation rule",
    "EVS-SUBJ-001": "record event without subject",
    "EVS-TRACE-001": "an AI model took part but trace is missing",
    "EVS-TENANT-001": "tenant id supplied by the producer, or another tenant's id inside data",
    "EVS-TENANT-002": "tenant scope mismatch (platform type vs tenant id)",
    "EVS-TENANT-003": "events of more than one tenant in one stream",
    "EVS-SEQ-001": "producer supplied a sequence (the store assigns it)",
    "EVS-SEQ-002": "sequence gap",
    "EVS-SEQ-003": "sequence repeated or out of order",
    "EVS-DUP-001": "event_id already used by another tenant",
    "EVS-DUP-002": "event_id reused with different content",
    "EVS-CAUSE-001": "causation_id does not reference an existing event of the same tenant",
    "EVS-CAUSE-002": "event causes itself",
    "EVS-FIELD-001": "field not allowed in build_event (platform-stamped or unknown)",
    "EVS-CLASS-001": "data_class lower than the type's default (warning)",
    "EVS-READ-001": "bad read arguments",
}


@dataclass(frozen=True)
class Issue:
    code: str
    path: str
    message: str
    severity: str = "error"

    def as_dict(self) -> dict:
        return {"code": self.code, "path": self.path, "message": self.message, "severity": self.severity}


class EventError(Exception):
    """Raised by producers and stores (never by validate_event)."""

    def __init__(self, code: str, message: str = ""):
        self.code = code
        self.message = message or CODES.get(code, "")
        super().__init__(f"{code}: {self.message}")


def clip(text: object, n: int = 200) -> str:
    s = str(text)
    return s if len(s) <= n else s[: n - 3] + "..."
