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


# Rigid-zone terms (AGENTS.md principle 3): a key whose name holds one of these as a substring or as a
# camelCase or snake_case token is a formula, posting, costing, tax, payroll or pricing knob.
RIGID_SUBSTRINGS = ("formula", "expression", "posting", "valuation", "account", "ledger", "payroll")
RIGID_TOKENS = ("cost", "tax", "rate", "price", "amount")


def _tokens(key):
    return [t.lower() for t in re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", key)]


def is_rigid_key(key):
    low = key.lower()
    return (any(t in low for t in RIGID_SUBSTRINGS)
            or any(tok.startswith(t) for tok in _tokens(key) for t in RIGID_TOKENS))


def _property_names(node, seen):
    """Every property name reachable from a schema node, following local $refs once each."""
    if isinstance(node, list):
        for n in node:
            yield from _property_names(n, seen)
        return
    if not isinstance(node, dict):
        return
    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/") and ref not in seen:
        seen.add(ref)
        yield from _property_names(SCHEMA["$defs"][ref.split("/")[-1]], seen)
    for key, value in node.items():
        if key == "properties" and isinstance(value, dict):
            yield from value
        if key not in ("description", "enum", "const", "examples"):
            yield from _property_names(value, seen)


@pytest.mark.parametrize("key", ["rmCostBasis", "taxTemplate", "valuationRate", "wipAccount", "billing_rate",
                                 "costing_rate", "priceList", "amount", "payrollPeriod", "ratePercent",
                                 "postingDate", "rate_formula", "ledgerHead", "operating_cost"])
def test_rigid_matcher_catches(key):
    assert is_rigid_key(key)


@pytest.mark.parametrize("key", ["integration", "probabilityPercent", "separate", "accurate", "stages", "labels"])
def test_rigid_matcher_spares(key):
    assert not is_rigid_key(key)


def test_module_settings_carry_no_formula_or_posting_keys():
    """Rigid zone (AGENTS.md principle 3): no module definition offers a formula, posting, costing, tax,
    payroll, rate, price or amount knob, at any depth (shared module defs included)."""
    for module, ref in SCHEMA["$defs"]["modules"]["properties"].items():
        keys = set(_property_names(ref, set()))
        assert keys and not sorted(k for k in keys if is_rigid_key(k)), (module, sorted(k for k in keys if is_rigid_key(k)))


def test_module_roles_description_grants_nothing():
    """ADR-0079 item 2: role lists name who the module screens treat as manager, worker or viewer; they grant nothing."""
    text = SCHEMA["$defs"]["moduleRoles"]["description"]
    assert "grants nothing" in text
    assert not re.search(r"\b(sees|see|reassign\w*|can|may|edit\w*|read\w*)\b", text, re.I), text


# Shared concepts (#395 review M1): a concept another part also owns may be implemented by that part's component.
FIXTURE_REGISTRY = C.parent / "services" / "blueprint" / "fixtures" / "registry"


def _capabilities(component_id):
    f = FIXTURE_REGISTRY / f"{component_id}.json"
    if not f.exists():
        return set()
    return {p["capability"] for p in json.loads(f.read_text(encoding="utf-8"))["provides"]}


def test_shared_concepts_are_declared_and_documented():
    shared = SCHEMA["x-module-shared-concepts"]
    assert {"crm.customer", "crm.campaign"} <= set(shared)
    for concept, caps in shared.items():
        module, name = concept.split(".")
        assert module in SCHEMA["$defs"]["modules"]["properties"], concept
        assert name in SCHEMA["$defs"][f"{module}Module"]["properties"]["entities"]["properties"], concept
        assert caps and all("." in c and not c.startswith(module + ".") for c in caps), concept
        for c in caps:
            assert f"`{c}`" in DOC, (concept, c)


def test_example_concept_bindings_follow_the_shared_concept_rule():
    """Every concept entity implements the module component, or (shared concept) a component providing a listed
    capability, never both. The fixture manifest for core.customer provides core.customer.entities, not crm.customer."""
    bp = load("blueprint-modules-minimal.json")
    shared = SCHEMA["x-module-shared-concepts"]
    ents = {e["id"]: e for e in bp["entities"]}
    for key, mod in bp["modules"].items():
        for concept, eid in mod["entities"].items():
            impl = {b["component"] for b in ents[eid].get("components", []) if b["mode"] == "implements"}
            via_module = mod["component"] in impl
            via_shared = any(set(shared.get(f"{key}.{concept}", [])) & _capabilities(c) for c in impl)
            assert via_module or via_shared, (key, concept, eid, impl)
            assert not (via_module and via_shared), ("one implementer per concept", concept)
    customer = ents[bp["modules"]["crm"]["entities"]["customer"]]
    assert [b["component"] for b in customer["components"]] == ["core.customer"]


def test_one_concept_binds_one_entity():
    """Intended (#395 review Low): a concept names exactly one Blueprint entity; two concepts never name the same
    entity (that half is a validator cross-rule, BPL-060)."""
    for module in SCHEMA["$defs"]["modules"]["properties"]:
        for concept, ref in SCHEMA["$defs"][f"{module}Module"]["properties"]["entities"]["properties"].items():
            assert ref == {"$ref": "#/$defs/id"}, (module, concept)
    assert any("never name the same entity" in r for r in SCHEMA["x-validator-rules"])
