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
