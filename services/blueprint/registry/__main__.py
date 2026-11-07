"""CLI. From services/blueprint:  python3 -m registry list|show|check DIR [...]

From the repo root set PYTHONPATH=services/blueprint. Exit 0 on success, 1 when the registry has errors or input is unreadable.
"""
from __future__ import annotations

import argparse
import json
import sys

from .registry import Registry


def _load(dirpath, strict: bool) -> Registry | None:
    try:
        return Registry.load(dirpath, strict=strict)
    except OSError as exc:
        print(f"ERROR REG-007 {dirpath}: cannot read folder ({type(exc).__name__})", file=sys.stderr)
        return None


def _print_issues(reg: Registry, stream) -> None:
    for i in reg.issues:
        print(i, file=stream)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="registry", description="Inspect and check a folder of component manifests.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_list = sub.add_parser("list", help="list admitted components and versions")
    p_list.add_argument("dir")
    p_list.add_argument("--strict", action="store_true", help="unknown requires are errors")
    p_show = sub.add_parser("show", help="print one manifest as JSON (highest version unless --version or --range)")
    p_show.add_argument("dir")
    p_show.add_argument("component")
    g = p_show.add_mutually_exclusive_group()
    g.add_argument("--version")
    g.add_argument("--range", dest="range_")
    p_show.add_argument("--strict", action="store_true")
    p_check = sub.add_parser("check", help="run admission rules and print findings")
    p_check.add_argument("dir")
    p_check.add_argument("--strict", action="store_true", help="unknown requires are errors")
    args = ap.parse_args(argv)

    reg = _load(args.dir, args.strict)
    if reg is None:
        return 1
    if args.cmd == "check":
        _print_issues(reg, sys.stdout)
        print(f"{len(reg.list_components())} component(s) admitted, {len(reg.errors)} error(s), {len(reg.warnings)} warning(s)")
        return 0 if reg.ok else 1
    _print_issues(reg, sys.stderr)  # keep stdout clean for the data
    if args.cmd == "list":
        for cid in reg.list_components():
            print(f"{cid}  {', '.join(reg.versions(cid))}")
        return 0 if reg.ok else 1
    try:
        if args.version:
            m = reg.get(args.component, args.version)
        else:
            m = reg.resolve(args.component, args.range_ or "*")
    except ValueError:
        print("ERROR REG-005 invalid version range", file=sys.stderr)
        return 1
    if m is None:
        print(f"ERROR REG-004 {args.component}: not in the registry", file=sys.stderr)
        return 1
    print(json.dumps(m, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if reg.ok else 1


if __name__ == "__main__":
    sys.exit(main())
