import copy
import random

from jsonschema import Draft202012Validator
import json

from bpdiff import apply, diff, invert
from bpdiff.model import eq
import bpdiff_helpers as h
from instantiate import instantiate

VALIDATOR = Draft202012Validator(json.loads(h.DIFF_SCHEMA.read_text(encoding="utf-8")))
SEED = 20260101
NOW = "2026-01-01T00:00:00Z"
SA = {"country": "sa", "name_ar": "شركة اختبار للتجارة", "name_en": "Sample Trading Co.", "branches": 2,
      "vat_registered": True, "vat_number": "300000000000003", "languages": ["ar", "en"]}


def _nodes(node, path=()):
    yield path, node
    if isinstance(node, dict):
        for k in sorted(node):
            yield from _nodes(node[k], path + (k,))
    elif isinstance(node, list):
        for i, e in enumerate(node):
            yield from _nodes(e, path + (i,))


def _mutate(doc, rng):
    """One random structural edit on plain JSON; may also break ids on purpose (invalid input is allowed)."""
    nodes = [(p, n) for p, n in _nodes(doc) if p]
    path, node = rng.choice(nodes)
    parent = doc
    for seg in path[:-1]:
        parent = parent[seg]
    last = path[-1]
    action = rng.choice(["scalar", "delete", "swap", "shuffle", "clone", "append", "retype"])
    if action == "scalar":
        if isinstance(node, bool):
            parent[last] = not node
        elif isinstance(node, int):
            parent[last] = node + 1
        elif isinstance(node, str):
            parent[last] = node + "x"
    elif action == "delete":
        if isinstance(parent, dict):
            del parent[last]
        elif len(parent) > 1:
            parent.pop(last)
    elif action == "swap" and isinstance(parent, list) and len(parent) > 1:
        j = rng.randrange(len(parent))
        parent[last], parent[j] = parent[j], parent[last]
    elif action == "shuffle" and isinstance(node, list):
        rng.shuffle(node)
    elif action == "clone" and isinstance(parent, list) and isinstance(node, dict):
        c = copy.deepcopy(node)
        if "id" in c and rng.random() < 0.7:
            c["id"] = c["id"] + "_copy"  # usually a valid new id, sometimes a duplicate
        parent.insert(rng.randrange(len(parent) + 1), c)
    elif action == "append" and isinstance(node, list):
        node.append(copy.deepcopy(rng.choice(node)) if node and rng.random() < 0.5 else "new")
    elif action == "retype":
        parent[last] = rng.choice([None, 0, "", [], {}, [1, 2], {"k": 1}])


def test_random_mutation_sequences():
    rng = random.Random(SEED)
    for n in range(60):
        a = h.base()
        revs = [a]
        cur = copy.deepcopy(a)
        for _ in range(rng.randint(1, 6)):
            _mutate(cur, rng)
            revs.append(copy.deepcopy(cur))
        for x, y in zip(revs, revs[1:]):
            x0, y0 = copy.deepcopy(x), copy.deepcopy(y)
            d = diff(x, y)
            VALIDATOR.validate(d)
            assert apply(d, x) == y, n
            assert apply(invert(d), y) == x, n
            assert x == x0 and y == y0
            assert d == diff(x0, y0)
            assert (not d["ops"]) == eq(x, y)
        # across several steps at once, and back
        d = diff(revs[0], revs[-1])
        assert apply(d, revs[0]) == revs[-1]
        assert apply(invert(d), revs[-1]) == revs[0]


def test_two_instantiated_sa_revisions():
    r1 = instantiate(h.TEMPLATE, SA, now=NOW)
    more = dict(SA, branches=3, name_en="Sample Trading Group Co.")
    r2 = instantiate(h.TEMPLATE, more, now=NOW)
    d = diff(r1, r2)
    VALIDATOR.validate(d)
    assert apply(d, r1) == r2 and apply(invert(d), r2) == r1
    codes = [o["code"] for o in d["ops"]]
    # one more branch = a branch and a warehouse, their select options, and the warehouse role scope
    assert codes.count("BPD-LOCATION-ADDED") == 2 and codes.count("BPD-OPTION-ADDED") == 10
    assert "BPD-ROLE-SCOPE-CHANGED" in codes and codes.count("BPD-BRANDING-CHANGED") == 2
    assert not {"remove"} & {o["op"] for o in d["ops"]} and not d["risk"]["needsDdlPlanGate"]
    assert d["risk"]["counts"]["compliance"] == 0 and not d["risk"]["touchesCompliance"]
    added = next(o for o in d["ops"] if o["code"] == "BPD-LOCATION-ADDED")
    assert added["labels"]["after"] and added["labels"]["before"] is None
    # branch scoped roles grow with the new branch: access changes exist and come from code
    assert d["risk"]["touchesAccess"] == bool(d["risk"]["counts"]["access"])
    assert diff(r1, instantiate(h.TEMPLATE, SA, now=NOW))["ops"] == []


def test_sa_to_ae_touches_compliance():
    sa = instantiate(h.TEMPLATE, SA, now=NOW)
    ae = instantiate(h.TEMPLATE, {"country": "ae", "name_ar": SA["name_ar"], "name_en": "Sample Trading LLC",
                                  "branches": 2, "vat_registered": True, "vat_number": "100000000000003",
                                  "currency": "AED"}, now=NOW)
    d = diff(sa, ae)
    VALIDATOR.validate(d)
    assert apply(d, sa) == ae and apply(invert(d), ae) == sa
    r = d["risk"]
    assert r["touchesCompliance"] and r["counts"]["compliance"] >= 3
    assert any(o["code"] == "BPD-COMPLIANCE-CHANGED" for o in d["ops"])
