import json

import pytest

from bpdiff import diff
from bpdiff.classify import IMPACTS, impact_of
from bpdiff.model import KEYED, NOUN, spath
import bpdiff_helpers as h

CONTRACT = json.loads((h.REPO / "contracts" / "blueprint.schema.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", sorted(h.CASES))
def test_classification_table(name):
    a, b = h.make_pair(name)
    got = {(o["op"], o["code"], o["impact"]) for o in diff(a, b)["ops"]}
    assert got == h.CASES[name][2]


@pytest.mark.parametrize("kind,path,expected", [
    ("remove", "entities/*", "destructive"),
    ("remove", "entities/*/fields/*", "destructive"),
    ("remove", "entities/*/relations/*", "destructive"),
    ("remove", "workflows/*/states/*", "destructive"),
    ("remove", "workflows/*/transitions/*", "access"),
    ("remove", "entities/*/fields/*/maxLength", "data_shape"),
    ("add", "entities/*", "data_shape"),
    ("add", "entities/*/relations/*", "data_shape"),
    ("replace", "entities/*/relations/*/onDelete", "data_shape"),
    ("replace", "entities/*/kind", "data_shape"),
    ("replace", "entities/*/fields/*/unique", "data_shape"),
    ("replace", "entities/*/fields/*/computed", "data_shape"),
    ("replace", "entities/*/fields/*/default", "config"),
    ("replace", "entities/*/fields/*/readOnly", "config"),
    ("add", "entities/*/fields/*/options/*", "config"),
    ("replace", "entities/*/numbering/prefix", "config"),
    ("replace", "entities/*/workflow", "config"),
    ("replace", "entities/*/labels/en", "cosmetic"),
    ("replace", "entities/*/fields/*/labels/ar", "cosmetic"),
    ("replace", "workflows/*/transitions/*/actionLabels/en", "cosmetic"),
    ("replace", "workflows/*/transitions/*/allowedRoles", "access"),
    ("replace", "workflows/*/transitions/*/approval", "access"),
    ("replace", "workflows/*/transitions/*/notify", "config"),
    ("replace", "entities/*/fields/*/visibleToRoles", "access"),
    ("replace", "reports/*/visibleToRoles", "access"),
    ("replace", "reports/*/schedule/channel", "config"),
    ("replace", "roles/*/labels/en", "cosmetic"),
    ("replace", "roles/*/permissions/*/actions", "access"),
    ("remove", "roles/*", "access"),
    ("replace", "approvals/*/steps/*/approverRole", "access"),
    ("replace", "branding/primaryColour", "branding"),
    ("replace", "branding/displayName/en", "branding"),
    ("replace", "compliance/vat/defaultRatePercent", "compliance"),
    ("replace", "compliance/documentLanguages", "compliance"),
    ("replace", "company/country", "compliance"),
    ("replace", "company/locale/fiscalYear/startMonth", "compliance"),
    ("replace", "company/locale", "compliance"),
    ("replace", "company/locale/timezone", "config"),
    ("replace", "company/tradeName/en", "config"),
    ("replace", "i18n/glossary/*/translations/en", "cosmetic"),
    ("add", "i18n/glossary/*", "cosmetic"),
    ("replace", "i18n/defaultLocale", "config"),
    ("replace", "meta/revision", "cosmetic"),
    ("replace", "meta/updatedAt", "cosmetic"),
    ("replace", "meta/buildState", "config"),
    ("replace", "meta/engineTarget/versionSet", "config"),
    ("replace", "entities/*/provenance/humanEdited", "cosmetic"),
    ("remove", "locations/*", "destructive"),
    ("replace", "locations/*/city", "cosmetic"),
    ("remove", "components/*", "destructive"),
    ("replace", "components/*/versionRange", "config"),
    ("remove", "integrations/*", "config"),
    ("remove", "reports/*", "config"),
    ("reorder", "approvals/*/steps", "access"),
    ("reorder", "entities/*/fields", "config"),
    ("reorder", "workflows/*/states", "config"),
    ("reorder", "entities", "cosmetic"),
    ("reorder", "roles", "cosmetic"),
    ("add", "modules/crm/roles/manage/*", "access"),
    ("replace", "modules/crm/roles/work", "access"),
    ("remove", "modules/crm/roles/view", "access"),
    ("replace", "modules/crm/roles", "access"),
    ("replace", "modules/crm/pipeline/stages/*/probabilityPercent", "config"),
    ("replace", "modules/manufacturing/warehouses/workInProgress", "compliance"),
    ("add", "modules/manufacturing/warehouses/scrap", "compliance"),
    ("replace", "modules/manufacturing/warehouses", "compliance"),
    ("replace", "modules/manufacturing", "compliance"),
    ("replace", "modules/manufacturing/roles/manage", "access"),
    ("replace", "modules/manufacturing/materialTransfer", "config"),
])
def test_impact_rules(kind, path, expected):
    assert impact_of(kind, spath(path)) == expected


def test_every_impact_is_reachable():
    seen = set()
    for name in h.CASES:
        a, b = h.make_pair(name)
        seen |= {o["impact"] for o in diff(a, b)["ops"]}
    assert seen == set(IMPACTS)


def test_ddl_gate_flag():
    for name in h.CASES:
        a, b = h.make_pair(name)
        r = diff(a, b)["risk"]
        c = r["counts"]
        assert r["needsDdlPlanGate"] == bool(c["data_shape"] or c["destructive"]), name
        assert r["touchesCompliance"] == bool(c["compliance"]) and r["touchesAccess"] == bool(c["access"])
        assert r["total"] == sum(c.values())


def _walk(node, path, out):
    """Find every array of objects in the contract: (schema path of the array, item schema)."""
    if "$ref" in node:
        target = CONTRACT
        for part in node["$ref"].split("/")[1:]:
            target = target[part]
        node = target
    if node.get("type") == "array":
        items = node.get("items", {})
        if "$ref" in items:
            ref = CONTRACT
            for part in items["$ref"].split("/")[1:]:
                ref = ref[part]
            items = ref
        if items.get("type") == "object":
            out.append((path, items))
        _walk(node.get("items", {}), path + ("*",), out)
    for k, v in node.get("properties", {}).items():
        _walk(v, path + (k,), out)
    if isinstance(node.get("additionalProperties"), dict):
        pass  # labelOverrides maps keys to localizedText, not arrays of objects


def test_key_table_covers_every_object_array_in_the_contract():
    found = []
    _walk({"properties": CONTRACT["properties"]}, (), found)
    arrays = {p for p, _ in found}
    # reducedPeriods / overrides sit under company.locale ($ref companyLocale)
    assert arrays == set(KEYED), arrays ^ set(KEYED)
    for path, items in found:
        required = set(items.get("required", []))
        assert set(KEYED[path]) <= required, (path, KEYED[path], required)
        assert path + ("*",) in NOUN


def _modules_example():
    return json.loads((h.REPO / "contracts" / "examples" / "blueprint-modules-minimal.json").read_text(encoding="utf-8"))


def test_module_role_change_is_access():
    """#395 review: promoting a role to module manager takes the access-review path, not config."""
    a = _modules_example()
    b = json.loads(json.dumps(a))
    b["modules"]["crm"]["roles"]["manage"].append("sales_rep")
    ops = diff(a, b)["ops"]
    assert ops and {o["impact"] for o in ops} == {"access"}


def test_manufacturing_warehouse_change_is_compliance():
    """#397 review: a warehouse choice moves stock and, through the warehouse account, ledger value."""
    a = _modules_example()
    b = json.loads(json.dumps(a))
    b["modules"]["manufacturing"]["warehouses"]["workInProgress"] = "fg_store"
    ops = diff(a, b)["ops"]
    assert ops and {o["impact"] for o in ops} == {"compliance"}
