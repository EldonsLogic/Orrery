"""Finding type and stable codes for the component registry."""
from __future__ import annotations

from dataclasses import dataclass

# Stable codes. Never renumber; add new ones at the end.
SCHEMA = "REG-001"          # manifest invalid against the component manifest schema
LICENCE = "REG-002"         # licence not recorded
DUPLICATE = "REG-003"       # same (id, version) with different content
REQ_UNKNOWN = "REG-004"     # requires an unknown component or capability (warning; error in strict mode)
REQ_UNSAT = "REG-005"       # requires a known component or capability but no version satisfies the range
EVIDENCE = "REG-006"        # blocking tests not evidenced as passed
FILE = "REG-007"            # file rejected: name, type, size, symlink, unreadable, not JSON, id/name mismatch
COPYLEFT = "REG-009"        # third-party copyleft licence not reviewed, or AGPL (needs an ADR)
DRAFT = "REG-010"           # draft certification level: admitted, not usable by tenants

ERROR, WARNING = "error", "warning"


@dataclass(frozen=True)
class Issue:
    """One finding. `subject` is `<id>@<version>` when known, otherwise the file name."""

    code: str
    severity: str
    subject: str
    message: str

    def __str__(self) -> str:
        return f"{self.severity.upper()} {self.code} {self.subject}: {self.message}"

    @property
    def is_error(self) -> bool:
        return self.severity == ERROR


def sort_issues(issues) -> list[Issue]:
    return sorted(issues, key=lambda i: (i.subject, i.code, i.severity, i.message))
