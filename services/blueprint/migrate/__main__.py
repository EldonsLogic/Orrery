"""CLI. From the repo root:

    PYTHONPATH=services/blueprint python3 -m migrate BLUEPRINT.json [--to X.Y.Z] [--allow-non-draft]

Prints JSON ({"ok", "from", "to", "steps", "blueprint"} or {"ok": false, "errors"}). Exit 0 migrated or already
current, 1 on a refusal or unreadable input. Nothing is written to disk.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "migrate"

from .core import migrate  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="migrate", description="Migrate a Blueprint to another schema version.")
    ap.add_argument("blueprint", type=Path)
    ap.add_argument("--to", dest="target", default=None, help="target schemaVersion (default: latest)")
    ap.add_argument("--allow-non-draft", action="store_true", help="also migrate a frozen (non-draft) Blueprint")
    args = ap.parse_args(argv)
    try:
        doc = json.loads(args.blueprint.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "errors": [{"code": "MIG-INPUT-002", "path": "/",
                                                      "message": f"cannot read input ({type(exc).__name__})"}]}))
        return 1
    r = migrate(doc, args.target, allow_non_draft=args.allow_non_draft)
    if not r.ok:
        print(json.dumps({"ok": False, "errors": [{"code": i.code, "path": i.path, "message": i.message} for i in r.errors]},
                         ensure_ascii=False, sort_keys=True))
        return 1
    steps = [{"from": s.from_version, "to": s.to_version, "changes": list(s.changes)} for s in r.steps]
    print(json.dumps({"ok": True, "from": r.from_version, "to": r.to_version, "steps": steps, "blueprint": r.blueprint},
                     ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
