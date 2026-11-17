"""CLI. From the repo root:

    PYTHONPATH=services/blueprint python3 -m compiler BLUEPRINT.json --mapping MAPPING.json --registry DIR \
        [--environment sandbox|production] --out ARTIFACT.json [--plan PLAN.json]

`python3 -m services.blueprint.compiler ...` from the repo root works too. Exit 0 when an artifact was written,
1 on a refusal or unreadable input (each reason printed as `ERROR <code> <pointer>: <fact>`, nothing written).
The default environment is production, so a sandbox compile has to be asked for.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # run as a script: make the package importable
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "compiler"

from ._deps import Registry  # noqa: E402
from .artifact import to_bytes  # noqa: E402
from .core import compile_blueprint  # noqa: E402
from .plan import plan_view  # noqa: E402


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="compiler", description="Compile a Blueprint into an engine-neutral artifact.")
    ap.add_argument("blueprint", type=Path)
    ap.add_argument("--mapping", type=Path, required=True, help="Blueprint-to-engine mapping JSON")
    ap.add_argument("--registry", type=Path, required=True, help="folder of component manifest JSON files")
    ap.add_argument("--environment", choices=["sandbox", "production"], default="production")
    ap.add_argument("--out", type=Path, required=True, help="where to write the artifact JSON")
    ap.add_argument("--plan", type=Path, help="optionally write the plan view JSON here")
    args = ap.parse_args(argv)
    try:
        blueprint, mapping = _read_json(args.blueprint), _read_json(args.mapping)
        registry = Registry.load(args.registry)
    except (OSError, ValueError, RecursionError) as exc:
        print(f"ERROR CMP-INPUT-002 /: cannot read input ({type(exc).__name__})")
        return 1
    result = compile_blueprint(blueprint, registry, mapping, environment=args.environment)
    if not result.ok:
        for issue in result.errors:
            print(f"ERROR {issue}")
        print(f"refused: {len(result.errors)} error(s)")
        return 1
    try:
        args.out.write_bytes(to_bytes(result.artifact))
        if args.plan:
            args.plan.write_bytes(to_bytes(plan_view(result.artifact)))
    except OSError as exc:
        print(f"ERROR CMP-OUTPUT-001 /: cannot write output ({type(exc).__name__})")
        return 1
    print(f"{result.artifact['artifactId']} {len(result.artifact['steps'])} step(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
