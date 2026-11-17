"""Import of the sibling validator, with the same path fallback as the compiler."""
from __future__ import annotations

import sys
from pathlib import Path

BLUEPRINT_DIR = Path(__file__).resolve().parents[1]
try:
    import validator  # type: ignore  # noqa: F401
except ImportError:
    sys.path.insert(0, str(BLUEPRINT_DIR))
from validator import validate  # type: ignore  # noqa: E402

__all__ = ["validate"]
