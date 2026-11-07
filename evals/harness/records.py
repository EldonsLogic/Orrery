"""Record schema validation and set loading."""
import json
import os
from collections import Counter

from jsonschema import Draft202012Validator

HERE = os.path.dirname(os.path.abspath(__file__))
EVALS_DIR = os.path.dirname(HERE)
SCHEMA_PATH = os.path.join(EVALS_DIR, "schema", "eval-record.schema.json")
SETS_DIR = os.path.join(EVALS_DIR, "sets")


def _validator() -> Draft202012Validator:
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_record(record) -> list:
    """Return a list of human-readable schema errors (empty when valid)."""
    v = _validator()
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
            for e in sorted(v.iter_errors(record), key=lambda e: list(map(str, e.absolute_path)))]


def list_sets(sets_dir: str = SETS_DIR) -> list:
    if not os.path.isdir(sets_dir):
        return []
    return sorted(d for d in os.listdir(sets_dir) if os.path.isdir(os.path.join(sets_dir, d)))


def load_set(name: str, sets_dir: str = SETS_DIR):
    """Return (records, errors) for every *.jsonl file in sets_dir/name. Never raises on bad data."""
    folder = os.path.join(sets_dir, name)
    records, errors, seen = [], [], {}
    files = sorted(f for f in os.listdir(folder) if f.endswith(".jsonl")) if os.path.isdir(folder) else []
    v = _validator()
    for fn in files:
        path = os.path.join(folder, fn)
        with open(path, encoding="utf-8") as f:
            for n, line in enumerate(f, 1):
                if not line.strip():
                    continue
                where = f"{name}/{fn}:{n}"
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError as e:
                    errors.append(f"{where}: invalid JSON: {e}")
                    continue
                errs = [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in v.iter_errors(rec)]
                if errs:
                    errors.extend(f"{where}: {m}" for m in errs)
                    continue
                if rec["set"] != name:
                    errors.append(f"{where}: set '{rec['set']}' does not match folder '{name}'")
                if rec["id"] in seen:
                    errors.append(f"{where}: duplicate id '{rec['id']}' (first at {seen[rec['id']]})")
                    continue
                seen[rec["id"]] = where
                records.append(rec)
    return records, errors


def counts(records) -> dict:
    return {
        "total": len(records),
        "by_category": dict(sorted(Counter(r["category"] for r in records).items())),
        "by_dialect": dict(sorted(Counter(r["dialect"] for r in records).items())),
    }
