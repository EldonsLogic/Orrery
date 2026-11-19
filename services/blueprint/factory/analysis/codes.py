"""Typed findings for the static analyser (SEC-010). Codes are stable: never renumber, add at the end."""
from __future__ import annotations

from dataclasses import dataclass, field

NETWORK = "SA-001"         # network access (socket, HTTP clients, URL literals, mail and file-transfer clients)
FILESYSTEM = "SA-002"      # filesystem escape: absolute or '..' path, destructive or link calls, dynamic path
PROCESS = "SA-003"         # subprocess, shell, process replacement, threads of control outside the test run
DYNAMIC_CODE = "SA-004"    # eval, exec, compile
DYNAMIC_IMPORT = "SA-005"  # importlib, __import__, runpy, plugin loaders
SECRETS = "SA-006"         # reads environment variables, credential files, keyrings
INTERNALS = "SA-007"       # imports engine-internal or platform-internal modules
UNDECLARED = "SA-008"      # capability the manifest does not declare (model SDK, undeclared dependency)
OBFUSCATION = "SA-009"     # encoded blobs, decode-then-run, dynamic getattr, homoglyphs, huge lines
INTROSPECTION = "SA-010"   # interpreter introspection used to escape (__subclasses__, __globals__, frames)
DESERIALISE = "SA-011"     # pickle, marshal, shelve, unsafe yaml.load
UNPARSEABLE = "SA-012"     # file cannot be parsed or decoded: fail closed
UNSUPPORTED = "SA-013"     # binary, compiled or non-Python script file: cannot be analysed
CREDENTIAL = "SA-014"      # hard-coded credential or private key literal
INTERNAL_ERROR = "SA-015"  # the analyser itself failed: fail closed

HIGH, MEDIUM, LOW = "high", "medium", "low"
SEVERITIES = (HIGH, MEDIUM, LOW)


@dataclass(frozen=True, order=True)
class Issue:
    path: str
    line: int
    code: str
    severity: str = field(compare=False)
    message: str = field(compare=False)

    def as_dict(self) -> dict:
        return {"code": self.code, "severity": self.severity, "path": self.path, "line": self.line,
                "message": self.message}

    def __str__(self) -> str:
        return f"{self.path}:{self.line} {self.code} {self.severity}: {self.message}"


@dataclass
class Analysis:
    files: int = 0
    issues: list = field(default_factory=list)

    @property
    def high(self) -> list:
        return [i for i in self.issues if i.severity == HIGH]

    @property
    def blocked(self) -> bool:
        """True when a high finding exists: the component can never reach 'tested'."""
        return bool(self.high)

    def as_dict(self) -> dict:
        counts = {s: sum(1 for i in self.issues if i.severity == s) for s in SEVERITIES}
        return {"files": self.files, "blocked": self.blocked, "counts": counts,
                "issues": [i.as_dict() for i in self.issues]}
