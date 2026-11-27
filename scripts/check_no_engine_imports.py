#!/usr/bin/env python3
"""QA-022: no Python file under services/ imports frappe, erpnext or hrms (ADR-0080 point 3).

Parses with ast, so strings and comments never count. Catches import, from-import, and dynamic
importlib.import_module("frappe...") / __import__("frappe") with a literal argument.
Prints path:line: forbidden engine import <name> (ADR-0080) and exits 1 on a hit; otherwise prints OK.
Usage: check_no_engine_imports.py [--root <dir containing services/>]
"""
import argparse
import ast
import sys
from pathlib import Path

FORBIDDEN = {"frappe", "erpnext", "hrms"}


def forbidden_name(module):
    top = (module or "").split(".")[0]
    return top if top in FORBIDDEN else None


def hits_in(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if forbidden_name(alias.name):
                    yield node.lineno, forbidden_name(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and forbidden_name(node.module):
                yield node.lineno, forbidden_name(node.module)
        elif isinstance(node, ast.Call) and node.args:
            f = node.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
            arg = node.args[0]
            if name in ("import_module", "__import__") and isinstance(arg, ast.Constant) \
                    and isinstance(arg.value, str) and forbidden_name(arg.value):
                yield node.lineno, forbidden_name(arg.value)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    root = Path(ap.parse_args().root)
    problems = []
    for path in sorted((root / "services").rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError) as e:
            problems.append(f"{rel}:1: cannot parse ({e.__class__.__name__}); fail closed (ADR-0080)")
            continue
        for line, name in sorted(hits_in(tree)):
            problems.append(f"{rel}:{line}: forbidden engine import {name} (ADR-0080)")
    if problems:
        print("\n".join(problems))
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
