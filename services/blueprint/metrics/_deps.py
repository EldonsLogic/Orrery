"""Import of bpdiff with the same path fallback as compiler/_deps.py."""
from __future__ import annotations

import sys
from pathlib import Path

_DIFF_DIR = Path(__file__).resolve().parents[1] / "diff"

try:
    import bpdiff  # type: ignore  # noqa: F401
except ImportError:
    sys.path.insert(0, str(_DIFF_DIR))

import bpdiff  # type: ignore  # noqa: E402
from bpdiff import BpdError  # type: ignore  # noqa: E402

__all__ = ["bpdiff", "BpdError"]
