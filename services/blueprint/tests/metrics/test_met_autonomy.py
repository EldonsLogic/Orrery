import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from metrics import MetricsError, autonomy_rate
from metrics.elements import ELEMENT_KINDS

BP = Path(__file__).resolve().parents[2]
FIXTURE = BP / "fixtures" / "trading-distribution.blueprint.json"


@pytest.fixture
def draft():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def total_elements(bp):
    n = sum(len(bp.get(k, [])) for k in ("entities", "workflows", "roles", "reports", "integrations"))
    return n + sum(len(e.get("fields", [])) for e in bp["entities"])


def test_identical_is_100_percent(draft):
    r = autonomy_rate(draft, copy.deepcopy(draft))
    assert r.rate == (r.total, r.total) and r.total == total_elements(draft)
    assert r.percent == 100.0 and r.manual == () and r.removed == () and r.exceptions_rows == ()
    assert r.tenant == "trading-distribution-fixture" and r.revision == 1
    assert r.by_kind["print_format"] == {"total": 0, "autonomous": 0}
    assert sum(v["total"] for v in r.by_kind.values()) == r.total


def test_hand_edited_field_counts_against_only_that_field(draft):
    a = copy.deepcopy(draft)
    f = a["entities"][0]["fields"][0]
    f["required"] = not f.get("required", False)
    r = autonomy_rate(draft, a)
    ptr = f"/entities/{a['entities'][0]['id']}/fields/{f['id']}"
    assert r.manual == (ptr,) and r.autonomous == r.total - 1
    assert r.by_kind["field"]["autonomous"] == r.by_kind["field"]["total"] - 1
    assert r.by_kind["entity"]["autonomous"] == r.by_kind["entity"]["total"]
    row = r.exceptions_rows[0]
    assert row == {"tenant": r.tenant, "revision": 1, "pointer": ptr, "change": "edited", "class": None}


def test_hand_edited_entity_property(draft):
    a = copy.deepcopy(draft)
    a["entities"][1]["numbering"] = {"prefix": "ZZ"}
    r = autonomy_rate(draft, a)
    assert r.manual == (f"/entities/{a['entities'][1]['id']}",)


def test_hand_added_role(draft):
    a = copy.deepcopy(draft)
    a["roles"].append({"id": "zz-role"})
    r = autonomy_rate(draft, a)
    assert r.manual == ("/roles/zz-role",) and r.total == total_elements(draft) + 1
    assert r.autonomous == total_elements(draft)
    assert r.exceptions_rows[0]["change"] == "added"
    assert r.by_kind["role"]["total"] == len(a["roles"])


def test_removed_element_is_listed_not_counted(draft):
    a = copy.deepcopy(draft)
    gone = a["entities"][1]["fields"].pop()
    r = autonomy_rate(draft, a)
    assert r.removed == (f"/entities/{a['entities'][1]['id']}/fields/{gone['id']}",)
    assert r.total == total_elements(draft) - 1 and r.autonomous == r.total and r.percent == 100.0


def test_added_entity_counts_its_fields_as_manual(draft):
    a = copy.deepcopy(draft)
    a["entities"].append({"id": "zz_ent", "fields": [{"id": "f1", "type": "text"}, {"id": "f2", "type": "text"}]})
    r = autonomy_rate(draft, a)
    assert set(r.manual) == {"/entities/zz_ent", "/entities/zz_ent/fields/f1", "/entities/zz_ent/fields/f2"}


def test_field_reorder_is_entity_edit(draft):
    a = copy.deepcopy(draft)
    a["entities"][2]["fields"].reverse()
    assert autonomy_rate(draft, a).manual == (f"/entities/{a['entities'][2]['id']}",)


def test_non_element_edits_ignored(draft):
    a = copy.deepcopy(draft)
    a["branding"] = {"displayName": {"ar": "x", "en": "y"}}
    a["meta"]["revision"] = 2
    r = autonomy_rate(draft, a)
    assert r.percent == 100.0 and r.revision == 2


def test_rounding_and_fraction():
    d = {"roles": [{"id": f"r{i}"} for i in range(3)]}
    a = copy.deepcopy(d)
    a["roles"][0]["function"] = "x"
    r = autonomy_rate(d, a, tenant="t1", revision=7)
    assert r.rate == (2, 3) and r.percent == 66.67 and (r.tenant, r.revision) == ("t1", 7)


def test_empty_draft_all_manual():
    r = autonomy_rate({}, {"roles": [{"id": "a"}]})
    assert r.rate == (0, 1) and r.percent == 0.0


def test_determinism_and_no_mutation(draft):
    a = copy.deepcopy(draft)
    a["roles"].append({"id": "zz"})
    d0, a0 = copy.deepcopy(draft), copy.deepcopy(a)
    r1, r2 = autonomy_rate(draft, a), autonomy_rate(draft, a)
    assert r1 == r2 and json.dumps(r1.to_dict()) == json.dumps(r2.to_dict())
    assert draft == d0 and a == a0


def test_kinds_are_data():
    assert [k.name for k in ELEMENT_KINDS] == ["entity", "field", "workflow", "role", "report", "print_format",
                                               "integration"]


@pytest.mark.parametrize("draft_,applied,code", [
    ({}, [], "MET-INPUT-001"),
    ([], {"roles": [{"id": "a"}]}, "MET-INPUT-001"),
    ({}, {}, "MET-AUTO-001"),
    ({}, {"roles": []}, "MET-AUTO-001"),
    ({}, {"roles": "x"}, "MET-INPUT-002"),
    ({}, {"roles": [{"id": 3}]}, "MET-INPUT-002"),
    ({}, {"roles": ["a"]}, "MET-INPUT-002"),
    ({}, {"roles": [{"id": "a"}, {"id": "a"}]}, "MET-INPUT-003"),
    ({"entities": [{"id": "e", "fields": [{"id": "x"}, {"id": "x"}]}]}, {"roles": [{"id": "a"}]}, "MET-INPUT-003"),
    ({}, {"roles": [{"id": "a", "v": float("nan")}]}, "MET-INPUT-004"),
])
def test_refusals(draft_, applied, code):
    with pytest.raises(MetricsError) as e:
        autonomy_rate(draft_, applied)
    assert e.value.code == code


def test_bad_tenant_revision():
    with pytest.raises(MetricsError) as e:
        autonomy_rate({}, {"roles": [{"id": "a"}]}, tenant=5)
    assert e.value.code == "MET-INPUT-001"
    with pytest.raises(MetricsError):
        autonomy_rate({}, {"roles": [{"id": "a"}]}, revision=1.5)


def test_cli(draft, tmp_path):
    a = copy.deepcopy(draft)
    a["roles"].append({"id": "zz-role"})
    (tmp_path / "d.json").write_text(json.dumps(draft))
    (tmp_path / "a.json").write_text(json.dumps(a))
    run = lambda *x: subprocess.run([sys.executable, "-m", "metrics", *x], cwd=BP, capture_output=True, text=True)
    p = run("autonomy", str(tmp_path / "d.json"), str(tmp_path / "a.json"), "--revision", "3")
    out = json.loads(p.stdout)
    assert p.returncode == 0 and out["manual"] == ["/roles/zz-role"] and out["revision"] == 3
    (tmp_path / "e.json").write_text("{}")
    p = run("autonomy", str(tmp_path / "d.json"), str(tmp_path / "e.json"))
    assert p.returncode == 1 and "MET-AUTO-001" in p.stderr
