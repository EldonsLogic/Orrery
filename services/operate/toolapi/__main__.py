"""CLI. From the repo root:

    PYTHONPATH=services/operate python3 -m toolapi BLUEPRINT.json [--registry REGISTRY.json]

`python3 services/operate/toolapi/__main__.py BLUEPRINT.json` works too. Prints the definition set as JSON on stdout.
Exit 0 on success; 1 on a refusal or unreadable input (each reason on stderr as `ERROR <code> <pointer>: <fact>`,
nothing on stdout). The generated set is re-checked with check_tool_api before it is printed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # run as a script: make the package importable
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "toolapi"

from .check import check_tool_api  # noqa: E402
from .generate import generate_tool_api  # noqa: E402
from .result import to_bytes  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="toolapi", description="Generate the typed tool definitions for a Blueprint.")
    ap.add_argument("blueprint", type=Path)
    ap.add_argument("--registry", type=Path, help="optional JSON: entity_classes and entity_effects overrides")
    args = ap.parse_args(argv)
    try:
        blueprint = json.loads(args.blueprint.read_text(encoding="utf-8"))
        registry = json.loads(args.registry.read_text(encoding="utf-8")) if args.registry else None
    except (OSError, ValueError, RecursionError) as exc:
        print(f"ERROR TAPI-INPUT-002 /: cannot read input ({type(exc).__name__})", file=sys.stderr)
        return 1
    result = generate_tool_api(blueprint, registry)
    issues = list(result.errors) or check_tool_api(result.definition_set())
    if issues:
        for i in issues:
            print(f"ERROR {i}", file=sys.stderr)
        print(f"refused: {len(issues)} error(s)", file=sys.stderr)
        return 1
    sys.stdout.buffer.write(to_bytes(result.definition_set()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
