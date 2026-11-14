"""ADP-C-051 to ADP-C-060: rollback and export."""
import copy
import json
import re
from pathlib import Path

import pytest

from adapter import testkit as t
from adapter.contract import canon, sha
from conftest import assert_no_effect, event_types

FAILED = {"blueprint.apply_failed"}
GOLDEN = Path(__file__).with_name("golden_export_hashes.json")


def applied(h, art, tenant="t_alpha"):
    out = t.apply_artifact(h, art, tenant)
    assert out["result"]["status"] == "applied", out
    return out["result"]


def test_adp_c_051_rollback_restores_the_exact_export(h):
    t.site_at_rev1(h)
    fwd = t.sample("add-field")
    before = t.export(h)["exportHash"]
    applied(h, fwd)
    out = t.rollback(h, fwd)["result"]
    assert out["status"] == "applied" and out["operation"] == "rollback" and out["artifactId"] == fwd["inverse"]["artifactId"]
    assert out["site"]["applied"]["revision"] == fwd["blueprint"]["base"]
    assert out["exportHash"] == t.export(h)["exportHash"] == before


def test_adp_c_051_rollback_of_a_quarantine_restores_the_field(h):
    t.site_at_rev1(h)
    applied(h, t.sample("add-field"))
    mid = t.export(h)["exportHash"]
    applied(h, t.sample("remove-field"))
    assert t.rollback(h, t.sample("remove-field"))["result"]["exportHash"] == mid
    assert t.status(h)["applied"]["revision"] == t.sample("remove-field")["blueprint"]["base"]


def test_adp_c_052_rollback_of_older_artifact(h):
    t.site_at_rev1(h)
    applied(h, t.sample("add-field"))
    applied(h, t.sample("remove-field"))
    before, ev = t.snapshot(h), len(h.events())
    resp = t.rollback(h, t.sample("add-field"))
    err = t.error_of(resp)
    assert err["code"] == "rollback_not_possible" and err["details"]["reasonCode"] == "not_latest"
    assert_no_effect(h, "t_alpha", before, ev, allow=FAILED)


def test_adp_c_053_no_inverse_or_irreversible(h):
    build = t.site_at_rev1(h)
    before, ev = t.snapshot(h), len(h.events())
    assert build["inverse"] is None
    err = t.error_of(t.rollback(h, build))
    assert err["code"] == "rollback_not_possible" and err["details"]["reasonCode"] == "no_inverse"
    assert_no_effect(h, "t_alpha", before, ev, allow=FAILED)
    art = t.sample("add-field")
    art["risk"]["irreversibleSteps"] = 1
    art["steps"][0]["reversible"] = False
    art = t.seal(art)
    applied(h, art)
    err = t.error_of(t.rollback(h, art))
    assert err["code"] == "rollback_not_possible" and err["details"]["reasonCode"] == "irreversible_step"


def test_adp_c_054_altered_inverse(h):
    t.site_at_rev1(h)
    fwd = t.sample("add-field")
    applied(h, fwd)
    before, ev = t.snapshot(h), len(h.events())
    stale_outer = copy.deepcopy(fwd)
    stale_outer["inverse"]["steps"][0]["params"]["definition"]["max"] = 1  # forward hash no longer matches
    resealed_inner = copy.deepcopy(stale_outer)
    t.seal(resealed_inner["inverse"])  # inner is consistent, forward's hash still covers the old inverse
    for bad in (stale_outer, resealed_inner):
        assert t.code_of(t.rollback(h, bad)) == "artifact_integrity_failed"
    assert_no_effect(h, "t_alpha", before, ev)


def test_adp_c_055_rollback_replay_and_conflict(h):
    t.site_at_rev1(h)
    fwd = t.sample("add-field")
    applied(h, fwd)
    approvals, key = {"rollbackApproved": t.ulid()}, t.key()
    first = t.rollback(h, fwd, k=key, approvals=approvals)
    after, ev = t.snapshot(h), len(h.events())
    again = t.rollback(h, fwd, k=key, approvals=approvals)
    assert again["replayed"] is True and again["result"] == first["result"]
    assert t.snapshot(h) == after and len(h.events()) == ev
    assert t.code_of(t.rollback(h, fwd, k=key, approvals=approvals, reason="support_action")) == "idempotency_conflict"
    assert t.snapshot(h) == after and len(h.events()) == ev


def test_adp_c_056_rollback_event(h):
    t.site_at_rev1(h)
    fwd = t.sample("add-field")
    applied(h, fwd)
    ev = len(h.events())
    out = t.rollback(h, fwd)["result"]
    new = h.events()[ev:]
    assert [e["type"] for e in new] == ["blueprint.rolled_back"]
    assert new[0]["data"] == {"change_id": fwd["artifactId"], "revision": fwd["blueprint"]["base"]["revision"]}
    assert out["eventIds"] == [new[0]["eventId"]]


# ---------------------------------------------------------------- export
def test_adp_c_057_export_is_canonical_and_stable(h):
    t.site_at_rev1(h)
    a, b = t.export(h), t.export(h)
    assert canon(a["export"]) == canon(b["export"])
    assert a["exportHash"] == sha(a["export"]) == "sha256:" + __import__("hashlib").sha256(
        json.dumps(a["export"], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def test_adp_c_058_same_artifacts_same_bytes(h):
    for tenant in ("t_alpha", "t_beta"):
        t.site_at_rev1(h, tenant)
        applied(h, t.sample("add-field"), tenant)
    t.rollback(h, t.sample("add-field"), "t_beta")
    t.apply_artifact(h, t.sample("add-field"), "t_beta")
    a, b = t.export(h, "t_alpha"), t.export(h, "t_beta")
    assert a["exportHash"] == b["exportHash"] and canon(a["export"]) == canon(b["export"])


SECTION_KIND = {"components": "component", "locations": "location", "entities": "entity", "roles": "role",
                "workflows": "workflow", "approvals": "approval", "reports": "report"}
CHILD = {"entity": {"fields": "field", "relations": "relation"}, "workflow": {"states": "state", "transitions": "transition"}}
ORDERED = {"fields", "options", "states", "steps", "metrics"}
STAMPS = {"createdAt", "updatedAt", "creation", "modified", "modified_by", "owner", "timestamp", "provenance", "name"}
ISO = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d")


def walk_keys(value, path=""):
    if isinstance(value, dict):
        for k, v in value.items():
            yield path + "/" + k, k
            yield from walk_keys(v, path + "/" + k)
    elif isinstance(value, list):
        for v in value:
            yield from walk_keys(v, path)


def test_adp_c_059_export_content_rules(h):
    t.site_at_rev1(h)
    applied(h, t.sample("add-field"))
    exported = t.export(h)["export"]
    props = h.call("capabilities", t.ctx("platform"), {})["result"]["exportedProperties"]
    sections = exported["sections"]
    assert set(sections) >= set(SECTION_KIND) | {"settings"}

    def check(kind, element):
        assert set(element) <= set(props[kind]), (kind, set(element) - set(props[kind]))
        for name, child in CHILD.get(kind, {}).items():
            if name in element and child in props:
                items = element[name]
                if name not in ORDERED:
                    assert [i["id"] for i in items] == sorted(i["id"] for i in items)
                for item in items:
                    check(child, item)

    for section, kind in SECTION_KIND.items():
        ids = [e["id"] for e in sections[section]]
        assert ids == sorted(ids), section
        for element in sections[section]:
            check(kind, element)
    bp = t.blueprint()
    assert [f["id"] for f in sections["entities"][0]["fields"]] == [f["id"] for f in bp["entities"][0]["fields"]] + ["payment_terms_days"]
    assert [s["id"] for s in next(w for w in sections["workflows"] if w["id"] == "sales_order_flow")["states"]] == [
        s["id"] for s in bp["workflows"][0]["states"]]
    text = json.dumps(exported, ensure_ascii=False)
    assert not ISO.search(text)
    assert not ({k for _, k in walk_keys(exported)} & STAMPS)


def sample_sequence_hashes(h):
    t.provision(h)
    hashes = {}
    for label, art in (("initial_build", t.initial_build()), ("add_field", t.sample("add-field")),
                       ("remove_field", t.sample("remove-field"))):
        applied(h, art)
        hashes[label] = t.export(h)["exportHash"]
    t.rollback(h, t.sample("remove-field"))
    hashes["rollback_remove_field"] = t.export(h)["exportHash"]
    return hashes


def test_adp_c_060_export_hashes_match_the_fake(h):
    """For the fake this checks determinism against the golden file. At BPL-027 the real adapter must match the same
    hashes (reported from BPL-012). The hashes depend on the fake's exportedProperties lists (open question 16.3)."""
    golden = json.loads(GOLDEN.read_text())
    assert sample_sequence_hashes(h) == golden
