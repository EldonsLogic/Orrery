"""CLI. From services/blueprint:  python3 -m factory check DIR [--run-tests --trusted-source] [--out REPORT.json]

Exit 0 ok, 1 findings with errors. Default is manifest and static checks only.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import check, write_report
from .errors import FacError


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="factory", description="Check a candidate component in a logical sandbox.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check")
    p.add_argument("dir")
    p.add_argument("--run-tests", action="store_true", help="run the declared tests through the allow-list")
    p.add_argument("--trusted-source", action="store_true", help="required for --run-tests; the source is trusted")
    p.add_argument("--timeout", type=float, default=120.0, help="wall-clock seconds for all tests")
    p.add_argument("--out", help="write the JSON report here (outside the component)")
    a = ap.parse_args(argv)
    rep = check(a.dir, run_tests=a.run_tests, trusted_source=a.trusted_source, timeout=a.timeout)
    if a.out:
        try:
            write_report(rep, a.out, a.dir)
        except FacError as exc:
            print(f"ERROR {exc}", file=sys.stderr)
            return 1
    print(json.dumps(rep.as_dict(), indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
