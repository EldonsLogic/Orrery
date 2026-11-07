"""CLI: python3 -m evstream validate FILE.json|FILE.jsonl [--chain] | types. Exit 0 ok, 1 problems."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .export import verify_chain
from .registry import default_registry
from .validate import validate_event

MAX_BYTES = 16 * 1024 * 1024
MAX_EVENTS = 100_000


def _load(path: str) -> list:
    p = Path(path)
    if p.stat().st_size > MAX_BYTES:
        raise ValueError(f"{path}: over {MAX_BYTES} bytes")
    text = p.read_text(encoding="utf-8")
    if p.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()][:MAX_EVENTS]
    doc = json.loads(text)
    return doc[:MAX_EVENTS] if isinstance(doc, list) else [doc]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="evstream", description="Event stream reference tools.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate", help="validate events in a .json (object or array) or .jsonl file")
    v.add_argument("file")
    v.add_argument("--chain", action="store_true", help="also verify per-tenant sequence continuity")
    sub.add_parser("types", help="list the registry")
    args = ap.parse_args(argv)
    reg = default_registry()
    if args.cmd == "types":
        for t in reg.entries():
            print(f"{t.type}\tv{t.schema_version}\t{t.kind}\t{t.data_class}\t{t.scope}")
        return 0
    try:
        events = _load(args.file)
    except (OSError, ValueError, RecursionError) as e:
        print(f"error: {str(e)[:200]}", file=sys.stderr)
        return 1
    bad = 0
    for i, ev in enumerate(events):
        r = validate_event(ev, reg)
        for issue in r.errors + r.warnings:
            print(f"[{i}] {issue.severity} {issue.code} {issue.path}: {issue.message}")
        bad += 0 if r.ok else 1
    if args.chain:
        by_tenant: dict = {}
        for ev in events:
            if isinstance(ev, dict):
                by_tenant.setdefault(ev.get("tenant_id"), []).append(ev)
        for tid, evs in by_tenant.items():
            for issue in verify_chain(evs):
                print(f"tenant {str(tid)[:40]} {issue.code} {issue.path}: {issue.message}")
                bad += 1
    print(f"{len(events)} event(s), {bad} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
