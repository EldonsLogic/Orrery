"""Typed errors and findings for the component factory sandbox. Codes are stable: never renumber, add at the end."""
from __future__ import annotations

from dataclasses import dataclass

CANDIDATE = "FAC-001"      # candidate folder missing, not a folder, a symlink or unreadable
MANIFEST = "FAC-002"       # manifest.json missing, unreadable, too large, not JSON or not an object
SPECIAL_FILE = "FAC-003"   # symlink or non-regular file inside the component
TRAVERSAL = "FAC-004"      # path leaves the component folder (absolute, '..', backslash, NUL)
TOO_MANY = "FAC-005"       # file count over the limit
TOO_BIG = "FAC-006"        # total size (or one file) over the limit
TEST_MISSING = "FAC-007"   # a declared test path does not exist in the component
TIMEOUT = "FAC-008"        # wall-clock limit hit; process group killed
BLOCKING_FAIL = "FAC-009"  # a blocking test failed
TEST_FAIL = "FAC-010"      # a non-blocking test failed (warning)
LEVEL_CAPPED = "FAC-011"   # declared level above 'tested'; the sandbox never grants it (warning)
UNTRUSTED = "FAC-012"      # tests not run: --trusted-source not given
REPORT_PATH = "FAC-013"    # report path inside the component or unwritable
COMMAND = "FAC-014"        # command not in the allow-list, or could not start

ERROR, WARNING = "error", "warning"


class FacError(Exception):
    """A precondition failure. Carries a stable code; the runner turns it into a finding."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code, self.message = code, message


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    message: str

    def as_dict(self) -> dict:
        return {"code": self.code, "severity": self.severity, "message": self.message}

    @property
    def is_error(self) -> bool:
        return self.severity == ERROR
