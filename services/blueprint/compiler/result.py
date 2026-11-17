"""Result types: a compiled artifact or a structured refusal. Messages are developer-facing (stable code + pointer +
short English fact, as in the validator); customer-facing text is built from the codes by our services, never here."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Issue:
    """One reason for a refusal: stable code, JSON pointer (into the Blueprint, the mapping or the artifact), fact."""

    code: str
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.code} {self.path or '/'}: {self.message}"

    def as_dict(self) -> dict:
        return {"code": self.code, "path": self.path, "message": self.message}


@dataclass
class CompileResult:
    """`ok` with an `artifact`, or not `ok` with `errors` (sorted, never empty). Never both."""

    artifact: dict | None = None
    errors: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.artifact is not None and not self.errors

    def as_dict(self) -> dict:
        if self.ok:
            return {"ok": True, "artifact": self.artifact}
        return {"ok": False, "errors": [i.as_dict() for i in self.errors]}


class Refused(Exception):
    """Internal: raised to stop compiling; turned into a CompileResult by compile_blueprint."""

    def __init__(self, issues: list[Issue]):
        super().__init__(f"{len(issues)} issue(s)")
        self.issues = issues


def sort_issues(issues: list[Issue]) -> list[Issue]:
    """Deterministic order with duplicates removed."""
    return sorted(set(issues), key=lambda i: (i.code, i.path, i.message))


def ptr(*parts: Any) -> str:
    out = ""
    for p in parts:
        out += "/" + str(p).replace("~", "~0").replace("/", "~1")
    return out
