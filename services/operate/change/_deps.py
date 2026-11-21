"""Imports of the Blueprint packages (validator, bpdiff) with the same path fallback as the compiler."""
from __future__ import annotations

import sys
from pathlib import Path

BLUEPRINT_DIR = Path(__file__).resolve().parents[2] / "blueprint"


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
from validator import validate  # type: ignore  # noqa: E402

__all__ = ["bpdiff", "blueprint_hash", "canonical", "validate"]
