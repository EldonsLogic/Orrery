import copy
import json
import random

import pytest
from jsonschema import Draft202012Validator

import bpdiff
from bpdiff import BpdError, apply, diff, invert
from bpdiff.model import KEYED, path_info
import bpdiff_helpers as h

SCHEMA = json.loads(h.DIFF_SCHEMA.read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)


def check(a, b):
    """Round trip both ways, schema-valid diff and inverse, inputs untouched."""
    a0, b0 = copy.deepcopy(a), copy.deepcopy(b)
    d = diff(a, b)
    VALIDATOR.validate(d)
    assert apply(d, a) == b
    inv = invert(d)
    VALIDATOR.validate(inv)
    assert apply(inv, b) == a
    assert invert(inv)["ops"] == d["ops"]
    assert a == a0 and b == b0
    return d


def test_schema_is_valid_draft_2020_12():
    Draft202012Validator.check_schema(SCHEMA)


def test_identity_diff_is_empty():
    a = h.base()
    d = check(a, copy.deepcopy(a))
    assert d["ops"] == [] and d["risk"]["total"] == 0 and d["risk"]["maxImpact"] is None
    assert d["base"]["hash"] == d["target"]["hash"]
    assert not d["risk"]["needsDdlPlanGate"]


@pytest.mark.parametrize("name", sorted(h.CASES))
def test_round_trip_single_mutation(name):
    a, b = h.make_pair(name)
    d = check(a, b)
    assert d["ops"], name


def test_round_trip_mutation_pairs():
    names = sorted(h.CASES)
    rng = random.Random(7)
    for _ in range(40):
        a = h.base()
        b = copy.deepcopy(a)
        for n in rng.sample(names, 3):
            prep, mutate, _ = h.CASES[n]
            if prep:
                prep(a), prep(b)
            try:
                mutate(b)
            except (StopIteration, IndexError, KeyError):
                pass  # an earlier mutation removed what this one needs
        check(a, b)


def test_diff_is_deterministic_and_independent_of_key_order():
    a, b = h.make_pair("add_field")
    shuffled = json.loads(json.dumps(b, sort_keys=True))
    assert diff(a, b) == diff(a, b) == diff(a, shuffled)
    assert json.dumps(diff(a, b), sort_keys=True) == json.dumps(diff(a, b), sort_keys=True)


def _shuffle_keyed(node, rng, sp=()):
    if isinstance(node, dict):
        for k, v in node.items():
            _shuffle_keyed(v, rng, sp + (k,) if sp not in KEYED else sp + ("*",))
    elif isinstance(node, list):
        if sp in KEYED:
            rng.shuffle(node)
        for e in node:
            _shuffle_keyed(e, rng, sp + ("*",) if sp in KEYED else sp)


def test_id_matching_survives_reordering():
    a = h.base()
    b = copy.deepcopy(a)
    _shuffle_keyed(b, random.Random(3))
    assert b != a
    d = check(a, b)
    assert d["ops"] and {o["op"] for o in d["ops"]} == {"reorder"}
    assert all(o["impact"] in ("cosmetic", "config", "access") for o in d["ops"])
    # a real change inside a reordered array is still one op addressed by id
    b["entities"][0]["labels"]["en"] += " x"
    target = b["entities"][0]["id"]
    d = check(a, b)
    reps = [o for o in d["ops"] if o["op"] == "replace"]
    assert len(reps) == 1 and reps[0]["path"][:2] == ["entities", target]
    assert not [o for o in d["ops"] if o["op"] in ("add", "remove")]


def test_reorder_flag_marks_significance():
    a, b = h.make_pair("reorder_approval_steps")
    d = diff(a, b)
    (op,) = d["ops"]
    assert op["orderSignificant"] is True and op["before"] == op["after"][::-1]
    b2 = copy.deepcopy(a)
    b2["roles"].reverse()
    (op2,) = diff(a, b2)["ops"]
    assert op2["orderSignificant"] is False and op2["impact"] == "cosmetic"


def test_base_hash_mismatch_refused():
    a, b = h.make_pair("add_field")
    d = diff(a, b)
    other = copy.deepcopy(a)
    other["meta"]["revision"] = 9
    with pytest.raises(BpdError) as e:
        apply(d, other)
    assert e.value.code == "BPD-BASE-001"
    with pytest.raises(BpdError) as e:
        apply(invert(d), a)  # inverse needs b as its base
    assert e.value.code == "BPD-BASE-001"


def test_tampered_diff_is_refused():
    a, b = h.make_pair("change_branding_colour")
    d = diff(a, b)
    bad = copy.deepcopy(d)
    bad["ops"][0]["before"] = "#000000"
    with pytest.raises(BpdError) as e:
        apply(bad, a)
    assert e.value.code == "BPD-APPLY-001"
    bad = copy.deepcopy(d)
    bad["ops"][0]["after"] = "#123456"
    with pytest.raises(BpdError) as e:
        apply(bad, a)
    assert e.value.code == "BPD-APPLY-002"
    bad = copy.deepcopy(d)
    bad["ops"][0]["path"] = ["nope", "x"]
    with pytest.raises(BpdError) as e:
        apply(bad, a)
    assert e.value.code == "BPD-APPLY-001"
    with pytest.raises(BpdError) as e:
        apply({"ops": []}, a)
    assert e.value.code == "BPD-DIFF-001"


def test_input_limits():
    a = h.base()
    deep = {}
    cur = deep
    for _ in range(70):
        cur["x"] = {}
        cur = cur["x"]
    b = copy.deepcopy(a)
    b["company"]["industry"] = deep
    with pytest.raises(BpdError) as e:
        diff(a, b)
    assert e.value.code == "BPD-INPUT-001"
    ok = copy.deepcopy(a)
    chain = {}
    node = chain
    for _ in range(40):
        node["x"] = {}
        node = node["x"]
    ok["company"]["industry"] = chain
    diff(a, ok)  # deep but within the limit
    for bad in ([], "x", None):
        with pytest.raises(BpdError) as e:
            diff(a, bad)
        assert e.value.code == "BPD-INPUT-003"
    b = copy.deepcopy(a)
    b["meta"]["revision"] = float("nan")
    with pytest.raises(BpdError) as e:
        diff(a, b)
    assert e.value.code == "BPD-INPUT-002"
    b["meta"]["revision"] = (1, 2)
    with pytest.raises(BpdError) as e:
        diff(a, b)
    assert e.value.code == "BPD-INPUT-002"


def test_bool_int_float_are_different_values():
    a, b = h.base(), h.base()
    a["entities"][0]["fields"][0]["default"] = 1
    b["entities"][0]["fields"][0]["default"] = True
    assert diff(a, b)["ops"]
    b["entities"][0]["fields"][0]["default"] = 1.0
    assert diff(a, b)["ops"]
    check(a, b)


def test_duplicate_or_missing_ids_fall_back_to_positions():
    a = h.base()
    b = copy.deepcopy(a)
    a["locations"].append(copy.deepcopy(a["locations"][0]))  # duplicate id: invalid, still diffable
    b["locations"].append(copy.deepcopy(b["locations"][0]))
    b["locations"][-1]["city"] = "Elsewhere"
    d = check(a, b)
    assert all(isinstance(o["path"][-2], int) or isinstance(o["path"][1], int) for o in d["ops"])
    c = copy.deepcopy(b)
    del c["entities"][3]["id"]
    check(b, c)
    check(c, a)


def test_scalar_arrays_are_one_value():
    a, b = h.base(), h.base()
    b["company"]["locale"]["workingTime"]["workDays"].append("fri")
    d = check(a, b)
    (op,) = d["ops"]
    assert op["op"] == "replace" and op["path"][-1] == "workDays"


def test_explanation_material():
    a, b = h.make_pair("add_entity")
    (op,) = diff(a, b)["ops"]
    assert op["subject"] == {"kind": "entity", "id": "warranty_claim", "parents": []}
    assert op["property"] == "" and op["after"]["id"] == "warranty_claim"
    assert op["labels"] == {"before": None, "after": {"ar": "اختبار", "en": "Warranty claim"}}
    assert op["pointer"] == "/entities/warranty_claim" and op["index"] == len(b["entities"]) - 1
    assert "before" not in op
    a, b = h.make_pair("rename_entity_label")
    (op,) = diff(a, b)["ops"]
    assert op["pointer"] == "/entities/item/labels/en" and op["property"] == "labels/en"
    assert op["labels"]["before"]["en"] != op["labels"]["after"]["en"]
    assert op["before"] != op["after"]
    a, b = h.make_pair("change_field_type")
    ops = diff(a, b)["ops"]
    f = next(o for o in ops if o["code"] == "BPD-FIELD-TYPE-CHANGED")
    assert f["subject"]["kind"] == "field" and f["subject"]["parents"] == [{"kind": "entity", "id": "customer"}]
    assert f["schemaPath"] == "/entities/*/fields/*/type"
    a, b = h.make_pair("remove_entity")
    (op,) = diff(a, b)["ops"]
    assert op["labels"]["after"] is None and op["labels"]["before"]["en"]


def test_risk_counts_come_from_ops():
    a, b = h.make_pair("add_field")
    b["branding"]["primaryColour"] = "#0A6B61"
    b["compliance"]["vat"]["defaultRatePercent"] = 14
    by_id = h.by_id(b["roles"], "sales_rep")
    by_id["scope"] = {"type": "company"}
    r = diff(a, b)["risk"]
    assert r["counts"] == {"cosmetic": 0, "config": 0, "data_shape": 1, "destructive": 0, "compliance": 1,
                           "access": 1, "branding": 1}
    assert r["total"] == 4 and r["needsDdlPlanGate"] and r["touchesCompliance"] and r["touchesAccess"]
    assert r["maxImpact"] == "data_shape"


def test_inverse_reclassifies():
    a, b = h.make_pair("add_field")
    assert diff(a, b)["risk"]["maxImpact"] == "data_shape"
    inv = invert(diff(a, b))
    assert inv["risk"]["maxImpact"] == "destructive"
    assert inv["ops"][0]["code"] == "BPD-FIELD-REMOVED"
    assert inv["base"] == diff(a, b)["target"] and inv["target"] == diff(a, b)["base"]


def test_path_info_matches_table():
    sp, elems = path_info(["entities", "customer", "fields", "customer_name", "labels", "en"])
    assert sp == ("entities", "*", "fields", "*", "labels", "en")
    assert [(n, k) for _, n, k in elems] == [("entity", "customer"), ("field", "customer_name")]


def test_public_api():
    for name in ("diff", "apply", "invert", "diff_validated"):
        assert callable(getattr(bpdiff, name))
