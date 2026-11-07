"""CLI. From services/blueprint:  python3 -m validator blueprint.json [--registry DIR] [--entitlement NAME]

From the repo root either set PYTHONPATH=services/blueprint, or run this file directly:
  python3 services/blueprint/validator/__main__.py blueprint.json
Exit code 0 when there are no errors, 1 otherwise (unreadable input counts as an error).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # run as a script: make the package importable
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "validator"

from validator.report import ValidationContext  # noqa: E402
from validator.validate import validate  # noqa: E402


def _load_registry(directory: Path) -> dict[str, list[dict]]:
    registry: dict[str, list[dict]] = {}
    for f in sorted(directory.rglob("*.json")):
        m = json.loads(f.read_text(encoding="utf-8"))
        if isinstance(m, dict) and isinstance(m.get("id"), str):
            registry.setdefault(m["id"], []).append(m)
    return registry


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="validator", description="Validate a Blueprint JSON file.")
    ap.add_argument("blueprint", type=Path)
    ap.add_argument("--registry", type=Path, help="directory of component manifest JSON files")
    ap.add_argument("--entitlement", action="append", default=[], help="plan entitlement, repeatable")
    args = ap.parse_args(argv)
    try:
        data = json.loads(args.blueprint.read_text(encoding="utf-8"))
        ctx = ValidationContext(entitlements=set(args.entitlement))
        if args.registry:
            ctx.registry = _load_registry(args.registry)
    except (OSError, ValueError, RecursionError) as exc:
        print(f"ERROR BP-INPUT-001 /: cannot read input ({type(exc).__name__})")
        return 1
    rep = validate(data, ctx)
    for i in rep.errors:
        print(f"ERROR {i}")
    for i in rep.warnings:
        print(f"WARN {i}")
    for a in rep.adjustments:
        print(f"ADJUST {a['path']} {a['theme']}: {a['original']} -> {a['proposed']}")
    print(f"{len(rep.errors)} error(s), {len(rep.warnings)} warning(s)")
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
