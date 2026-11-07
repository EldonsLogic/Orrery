"""Fictional component manifests and context for tests. Nothing here is a real component."""
import copy
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "contracts" / "examples" / "blueprint-trading-minimal.json"
COMPONENT_SCHEMA = REPO / "contracts" / "component.manifest.schema.json"


def _manifest(cid, requires=(), functions=()):
    provides = [{"capability": cid + ".core", "artifacts": [{"type": "entity", "ref": "entity/" + cid}]}]
    if functions:
        provides.append({"capability": cid + ".functions",
                         "artifacts": [{"type": "function", "ref": f} for f in functions]})
    return {
        "id": cid, "version": "0.1.2", "kind": "configurable",
        "name": {"ar": "مكون تجريبي", "en": "Test component " + cid},
        "description": "Fictional component used only by validator tests.",
        "provides": provides,
        "requires": list(requires),
        "parameters": [],
        "tests": [{"id": "unit_basic", "kind": "unit", "path": "tests/basic", "blocking": True}],
        "certification": {"level": "draft"},
        "engineCompatibility": {"adapter": "frappe", "engineRange": ">=1.0.0 <2.0.0", "testedAgainst": ["set-example"]},
        "licence": {"spdx": "LicenseRef-Proprietary"},
        "owner": {"github": "example-owner"},
    }


def manifests():
    return [
        _manifest("core.customer"),
        _manifest("core.item"),
        _manifest("core.sales_order", requires=[{"component": "core.customer", "versionRange": "^0.1.0"}],
                  functions=["compliance.vat.calculate", "core.sales.order_total"]),
        _manifest("core.sales_invoice", requires=[{"capability": "core.sales_order.core", "versionRange": ">=0.1.0 <1.0.0"}]),
        _manifest("compliance.zatca_sa"),
    ]


def registry():
    out = {}
    for m in manifests():
        out.setdefault(m["id"], []).append(m)
    # an older and a newer version, to exercise range selection
    old = copy.deepcopy(out["core.item"][0]); old["version"] = "0.0.9"
    new = copy.deepcopy(out["core.item"][0]); new["version"] = "0.2.0"
    out["core.item"] += [old, new]
    return out


def assets():
    return {"logo-light-0001": {
        "mediaType": "image/png", "bytes": 48213, "widthPx": 512, "heightPx": 512, "sanitised": True,
        "sha256": "0000000000000000000000000000000000000000000000000000000000000001"}}


def load_example():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))
