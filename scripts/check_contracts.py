#!/usr/bin/env python3
"""Contracts check: every schema under contracts/ is a valid JSON Schema (draft 2020-12), every example
validates against its schema, and cross-file $refs resolve. Needs `jsonschema` (see services/blueprint/requirements.txt).
"""
import json
import sys
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012
except ImportError:
    print("jsonschema with referencing is required: pip install -r services/blueprint/requirements.txt")
    sys.exit(2)

ROOT = Path(__file__).resolve().parent.parent
C = ROOT / "contracts"
# example glob -> schema file
PAIRS = [("examples/blueprint-*.json", "blueprint.schema.json"),
         ("examples/compiled-artifact-*.json", "compiled-artifact.schema.json")]


def main():
    errors = []
    schemas = sorted(C.rglob("*.schema.json"))
    registry = Registry()
    for f in schemas:
        data = json.loads(f.read_text(encoding="utf-8"))
        try:
            Draft202012Validator.check_schema(data)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{f.relative_to(ROOT)}: invalid schema: {exc}")
            continue
        res = Resource.from_contents(data, default_specification=DRAFT202012)
        registry = registry.with_resource(f.resolve().as_uri(), res)
        if "$id" in data:
            registry = registry.with_resource(data["$id"], res)
    for pattern, schema_name in PAIRS:
        sf = C / schema_name
        if not sf.exists():
            errors.append(f"missing schema {schema_name}")
            continue
        validator = Draft202012Validator(json.loads(sf.read_text(encoding="utf-8")), registry=registry)
        for ex in sorted(C.glob(pattern)):
            for e in validator.iter_errors(json.loads(ex.read_text(encoding="utf-8"))):
                errors.append(f"{ex.relative_to(ROOT)}: {'/'.join(map(str, e.absolute_path))}: {e.message[:160]}")
    for e in errors:
        print(e)
    print(f"Contracts OK ({len(schemas)} schemas)" if not errors else f"Contracts FAILED ({len(errors)})")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
