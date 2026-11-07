"""Result types and the validation context for the Blueprint validator."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def ptr(*parts: Any) -> str:
    """Build an RFC 6901 JSON pointer from path parts."""
    out = ""
    for p in parts:
        out += "/" + str(p).replace("~", "~0").replace("/", "~1")
    return out


@dataclass(frozen=True)
class Issue:
    """One finding: stable rule code, JSON pointer into the Blueprint, short factual message."""

    code: str
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.code} {self.path or '/'}: {self.message}"


@dataclass
class Report:
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    # Colour auto-adjust proposals: dicts with path, theme, original, proposed, ratios.
    adjustments: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, code: str, path: str, message: str) -> None:
        self.errors.append(Issue(code, path, message))

    def warn(self, code: str, path: str, message: str) -> None:
        self.warnings.append(Issue(code, path, message))

    def codes(self) -> set[str]:
        return {i.code for i in self.errors} | {i.code for i in self.warnings}


@dataclass
class ValidationContext:
    """Everything the validator may not learn from the Blueprint itself. All fields optional.

    registry:      component id -> list of manifests (component.manifest.schema.json shape)
    metrics:       known semantic-layer metric ids
    connectors:    known connector ids
    assets:        assetId -> record (mediaType, bytes, sha256, sanitised, optional widthPx/heightPx)
    entitlements:  plan entitlements of the tenant, for example {"white_label"}
    pack_locales:  overrides DEFAULT_PACK_LOCALES (pack id -> locale defaults)
    schema_path:   overrides the location of contracts/blueprint.schema.json
    """

    registry: dict[str, list[dict]] | None = None
    metrics: set[str] | None = None
    connectors: set[str] | None = None
    assets: dict[str, dict] | None = None
    entitlements: set[str] | None = None
    pack_locales: dict[str, dict] | None = None
    schema_path: Path | None = None


def as_list(x: Any) -> list:
    return x if isinstance(x, list) else []


def as_dict(x: Any) -> dict:
    return x if isinstance(x, dict) else {}


def items(x: Any):
    """Yield (index, dict) for the dict members of a list; tolerant of bad shapes."""
    for i, v in enumerate(as_list(x)):
        if isinstance(v, dict):
            yield i, v


def sid(x: Any) -> str | None:
    """The value if it is a string, else None (used for ids that may be malformed)."""
    return x if isinstance(x, str) else None
