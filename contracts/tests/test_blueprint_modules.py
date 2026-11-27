"""Contract tests for Blueprint modules (ADR-0079, contracts/blueprint-modules.md).

The valid example must pass the Blueprint schema; every case in examples/invalid/blueprint-modules-*-cases.json
edits that example by JSON pointer and must fail at the path it names, so each case fails for its own reason.
Run: python3 -m pytest contracts/tests -q (needs jsonschema).
"""
import copy
import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

C = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((C / "blueprint.schema.json").read_text(encoding="utf-8"))
DOC = (C / "blueprint-modules.md").read_text(encoding="utf-8")
V = Draft202012Validator(SCHEMA)
CASE_FILES = sorted((C / "examples" / "invalid").glob("blueprint-modules-*-cases.json"))


def load(name):
    return json.loads((C / "examples" / name).read_text(encoding="utf-8"))


def _walk(doc, pointer):
    parts = [p.replace("~1", "/").replace("~0", "~") for p in pointer.lstrip("/").split("/")]
    node = doc
    for p in parts[:-1]:
        node = node[int(p)] if isinstance(node, list) else node[p]
    return node, parts[-1]


def apply(base, case):
    doc = copy.deepcopy(base)
    for pointer, value in case.get("set", {}).items():
        node, key = _walk(doc, pointer)
        if isinstance(node, list):
            node[int(key)] = value
        else:
            node[key] = value
    for pointer in case.get("remove", []):
        node, key = _walk(doc, pointer)
        del node[int(key) if isinstance(node, list) else key]
    return doc


def cases():
    out = []
    for f in CASE_FILES:
        spec = json.loads(f.read_text(encoding="utf-8"))
        out += [pytest.param(spec["base"], c, id=f"{f.stem}:{c['name']}") for c in spec["cases"]]
    return out


def test_valid_example_passes():
    errors = [f"{'/'.join(map(str, e.absolute_path))}: {e.message[:120]}" for e in V.iter_errors(load("blueprint-modules-minimal.json"))]
    assert not errors, errors


def test_modules_are_optional():
    bp = load("blueprint-trading-minimal.json")
    assert "modules" not in bp and V.is_valid(bp)


def test_case_files_exist():
    assert CASE_FILES


@pytest.mark.parametrize("base,case", cases())
def test_invalid_case_fails_at_named_path(base, case):
    errors = list(V.iter_errors(apply(load(base), case)))
    assert errors, f"{case['name']} unexpectedly validates"
    paths = ["/".join(map(str, e.absolute_path)) for e in errors]
    assert any(p.startswith(case["expect"]) for p in paths), (case["name"], paths)


def test_versions_agree():
    version = SCHEMA["version"]
    assert SCHEMA["$id"].endswith(":" + version)
    assert re.search(rf"^Version: {re.escape(version)}$", DOC, re.M)
    readme = (C / "README.md").read_text(encoding="utf-8")
    assert re.search(rf"\| 1 \| Blueprint schema.*\| {re.escape(version)} \|", readme)
    assert re.search(rf"^- {re.escape(version)} ", DOC, re.M), "changelog entry missing"


def test_every_module_is_documented_with_metrics():
    for module in SCHEMA["$defs"]["modules"]["properties"]:
        assert re.search(rf"^## Module `{module}`", DOC, re.M), module
        assert re.search(rf"^Metrics: .*`{module}\.[a-z_]+`", DOC, re.M), module


def test_example_module_metrics_are_in_the_vocabulary():
    bp = load("blueprint-modules-minimal.json")
    modules = tuple(f"{m}." for m in SCHEMA["$defs"]["modules"]["properties"])
    vocab = set(re.findall(r"`([a-z]+\.[a-z_]+)`", "\n".join(l for l in DOC.splitlines() if l.startswith("Metrics: "))))
    refs = [m["ref"] for r in bp.get("reports", []) for m in r["metrics"] if m["ref"].startswith(modules)]
    assert refs and set(refs) <= vocab, set(refs) - vocab


def test_module_settings_carry_no_formula_or_posting_keys():
    """Rigid zone (AGENTS.md principle 3): no module definition offers a formula, posting or valuation knob."""
    banned = re.compile(r"formula|expression|posting|valuation|account|ledger|rate_formula", re.I)
    for module, ref in SCHEMA["$defs"]["modules"]["properties"].items():
        text = json.dumps(SCHEMA["$defs"][ref["$ref"].split("/")[-1]]["properties"])
        keys = re.findall(r'"([A-Za-z_]+)": \{', text)
        assert not [k for k in keys if banned.search(k)], module
