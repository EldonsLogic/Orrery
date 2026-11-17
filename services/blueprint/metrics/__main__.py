"""CLI: python3 -m metrics autonomy DRAFT.json APPLIED.json [--tenant T] [--revision N]

From services/blueprint, or from the repo root with PYTHONPATH=services/blueprint. Prints the result as JSON.
Exit 0 on success, 1 on a refusal or unreadable input (`ERROR <code> <message>` on stderr).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # run as a script
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "metrics"

from .autonomy import autonomy_rate  # noqa: E402
from .errors import MetricsError  # noqa: E402

MAX_BYTES = 8 * 1024 * 1024


def _read(path: str):
    p = Path(path)
    if p.stat().st_size > MAX_BYTES:
        raise MetricsError("MET-INPUT-004", f"{path}: file over {MAX_BYTES} bytes")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, RecursionError):
        raise MetricsError("MET-INPUT-004", f"{path}: not valid JSON") from None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="metrics")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("autonomy", help="Platform Autonomy Rate of an applied revision against its library draft")
    p.add_argument("draft")
    p.add_argument("applied")
    p.add_argument("--tenant")
    p.add_argument("--revision")
    args = ap.parse_args(argv)
    try:
        rev = args.revision
        if rev is not None and rev.isdigit():
            rev = int(rev)
        res = autonomy_rate(_read(args.draft), _read(args.applied), tenant=args.tenant, revision=rev)
    except MetricsError as e:
        print(f"ERROR {e.code} {e.message}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"ERROR MET-INPUT-004 cannot read input ({type(e).__name__})", file=sys.stderr)
        return 1
    print(json.dumps(res.to_dict(), indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
