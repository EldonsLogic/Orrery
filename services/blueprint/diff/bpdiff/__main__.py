"""CLI: python3 -m bpdiff A.json B.json [--json] [--apply-check]. Exit 0 same, 1 differs, 2 error."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .applier import apply, invert
from .engine import diff
from .errors import BpdError
from .model import eq

MAX_BYTES = 8 * 1024 * 1024


def _load(path: str) -> dict:
    p = Path(path)
    if p.stat().st_size > MAX_BYTES:
        raise BpdError("BPD-INPUT-002", f"{path}: file over {MAX_BYTES} bytes")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except RecursionError:
        raise BpdError("BPD-INPUT-001", f"{path}: nesting too deep") from None
    except ValueError as e:
        raise BpdError("BPD-INPUT-002", f"{path}: not valid JSON ({e})") from None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bpdiff", description="Structural diff of two Blueprint revisions.")
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--json", action="store_true", help="print the Diff object as JSON")
    ap.add_argument("--apply-check", action="store_true",
                    help="also check apply(d, a) == b and apply(invert(d), b) == a")
    args = ap.parse_args(argv)
    try:
        a, b = _load(args.a), _load(args.b)
        d = diff(a, b)
        if args.apply_check:
            if not eq(apply(d, a), b) or not eq(apply(invert(d), b), a):
                raise BpdError("BPD-APPLY-002", "apply check failed")
    except (BpdError, OSError) as e:
        code = e.code if isinstance(e, BpdError) else "BPD-INPUT-002"
        print(f"ERROR {code} {getattr(e, 'message', e)}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(d, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        for op in d["ops"]:
            print(f"{op['op']:7} {op['impact']:11} {op['code']} {op['pointer']}")
        r = d["risk"]
        print(f"{r['total']} operations; " + ", ".join(f"{k}={v}" for k, v in r["counts"].items() if v)
              + f"; needsDdlPlanGate={str(r['needsDdlPlanGate']).lower()}"
              f" touchesCompliance={str(r['touchesCompliance']).lower()}"
              f" touchesAccess={str(r['touchesAccess']).lower()}")
        if args.apply_check:
            print("apply check: ok")
    return 1 if d["ops"] else 0


if __name__ == "__main__":
    sys.exit(main())
