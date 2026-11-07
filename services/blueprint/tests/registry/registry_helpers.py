"""Shared helpers for registry tests. All data is fictional."""
import copy
import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
REGISTRY_DIR = FIXTURES / "registry"
BLUEPRINT = FIXTURES / "trading-distribution.blueprint.json"


def fixture_manifest(name="core.item"):
    return json.loads((REGISTRY_DIR / f"{name}.json").read_text(encoding="utf-8"))


def variant(name="core.item", **over):
    """A deep copy of a fixture manifest with top-level keys replaced."""
    m = copy.deepcopy(fixture_manifest(name))
    m.update(over)
    return m


def write(dirpath, filename, data):
    p = Path(dirpath) / filename
    p.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return p


def codes(issues, severity=None):
    return sorted({i.code for i in issues if severity is None or i.severity == severity})
