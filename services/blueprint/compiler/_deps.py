"""Imports of the sibling packages the compiler reuses (validator, registry, bpdiff), with the same path fallback as
bpdiff/validated.py: when `services/blueprint` (or `services/blueprint/diff`) is not on the import path, add it."""
from __future__ import annotations

import sys
from pathlib import Path

BLUEPRINT_DIR = Path(__file__).resolve().parents[1]
REPO = BLUEPRINT_DIR.parents[1]
CONTRACTS = REPO / "contracts"


def _ensure(path: Path) -> None:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


try:
    import validator  # type: ignore  # noqa: F401
except ImportError:
    _ensure(BLUEPRINT_DIR)
try:
    import bpdiff  # type: ignore  # noqa: F401
except ImportError:
    _ensure(BLUEPRINT_DIR / "diff")

import bpdiff  # type: ignore  # noqa: E402
from bpdiff.model import blueprint_hash, canonical  # type: ignore  # noqa: E402
from registry import Registry  # type: ignore  # noqa: E402
from validator import ValidationContext, validate  # type: ignore  # noqa: E402
from validator import semver  # type: ignore  # noqa: E402

__all__ = ["bpdiff", "blueprint_hash", "canonical", "Registry", "ValidationContext", "validate", "semver",
           "CONTRACTS", "REPO", "BLUEPRINT_DIR"]
