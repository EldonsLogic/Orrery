"""diff_validated: the diff plus a validator report for each revision."""
from __future__ import annotations

import copy
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .engine import Diff, diff


def _validator():
    try:
        import validator  # type: ignore
    except ImportError:  # run without PYTHONPATH: services/blueprint is three levels up
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        import validator  # type: ignore
    return validator


def _report_dict(r: Any) -> dict:
    return {"ok": r.ok,
            "errors": [{"code": i.code, "path": i.path, "message": i.message} for i in r.errors],
            "warnings": [{"code": i.code, "path": i.path, "message": i.message} for i in r.warnings]}


@dataclass
class ValidatedDiff:
    diff: Diff
    base_report: Any
    target_report: Any
    flags: list[dict] = field(default_factory=list)

    @property
    def invalid(self) -> bool:
        return bool(self.flags)

    def to_dict(self) -> dict:
        return {"diff": self.diff, "flags": self.flags,
                "baseReport": _report_dict(self.base_report),
                "targetReport": _report_dict(self.target_report)}


def diff_validated(a: dict, b: dict, ctx: Any = None) -> ValidatedDiff:
    """Diff two revisions and validate both. A diff against an invalid revision is allowed but flagged
    (`BPD-VALID-001` base revision invalid, `BPD-VALID-002` target revision invalid)."""
    d = diff(a, b)
    v = _validator()
    ra, rb = v.validate(copy.deepcopy(a), ctx), v.validate(copy.deepcopy(b), ctx)
    flags = []
    if not ra.ok:
        flags.append({"code": "BPD-VALID-001", "side": "base", "errors": len(ra.errors)})
    if not rb.ok:
        flags.append({"code": "BPD-VALID-002", "side": "target", "errors": len(rb.errors)})
    return ValidatedDiff(d, ra, rb, flags)
