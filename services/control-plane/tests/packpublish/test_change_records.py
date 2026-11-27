import copy
import dataclasses
import json

import pytest
from pp_support import ACC, FDR, FDR2, World, schema_errors

from packpublish import Actor, PublishError
from packpublish.canon import canonical, digest
from packpublish.fakes import fake_signature

LATER = {"file": "pack.json", "path": "tax.roundingRule", "op": "set", "value": "half_even"}


def code(fn, *a, **k):
    with pytest.raises(PublishError) as e:
        fn(*a, **k)
    return e.value.code


def two_versions(key_env="dev", urgent=False):
    """0.2.0 then 0.3.0 published; returns (world, index after 0.3.0, publish ids)."""
    w = World(key_env)
    d1, r1 = w.publish()
    kw = {"change_kind": "urgent", "review_ref": "review:sa:urgent-1"} if urgent else {}
    d2 = w.pub.draft(base_files=w.last_files, edits=[LATER],
                     evidence_refs=[{"id": "evidence:sa:0.3.0:01", "sha256": "sha256:" + "cd" * 32}],
                     new_version="0.3.0", **kw)
    w.publish(d2, rid="req-2")
    return w, json.loads(w.store.indexes["SA"]), (r1["record"]["publishId"], w.last["record"]["publishId"])


def sign_change(w, c):
    def s(who, role):
        return w.pub.sign_change(c, role=role, signer_id=who, mfa=w.mfa(who), signature=fake_signature(who, c.statement_digest))
    return [s(ACC, "market_accountant"), s(FDR, "founder")]


def apply(w, c, rid="chg-1", sos=None, actor=None):
    return w.pub.apply_change(rid, c, sos or sign_change(w, c), actor or Actor(FDR, "tok:2"))


def withdraw(w, version="0.2.0"):
    return w.pub.propose_change(kind="withdrawal", country="SA", target={"version": version}, reason_ref="reason:sa:w1")


def floor(w, version="0.3.0", ref="reason:sa:f1"):
    return w.pub.propose_change(kind="floor_raise", country="SA", target={"version": version}, reason_ref=ref)


def test_withdrawal_happy_path_validates_and_chains():
    w, idx, _ = two_versions()
    r = apply(w, withdraw(w))
    new = r["index"]
    assert schema_errors("index", new) == []
    assert [e["version"] for e in new["published"]] == ["0.3.0"]
    assert new["withdrawn"][0]["version"] == "0.2.0" and new["withdrawn"][0]["reasonRef"] == "reason:sa:w1"
    assert new["indexSeq"] == idx["indexSeq"] + 1 and new["predecessorDigest"] == digest(canonical(idx))
    rec, entry = r["changeRecord"], new["changeRecords"][0]
    assert entry == {"id": rec["id"], "kind": "withdrawal", "sha256": digest(canonical(rec))}
    assert sorted(s["role"] for s in rec["signOffs"]) == ["founder", "market_accountant"]
    assert w.store.indexes["SA"] == canonical(new) and r["auditId"] in w.audit.entries
    assert w.audit.entries[r["auditId"]]["action"] == "country_pack.change.withdrawal"


def test_withdrawal_refusals():
    w, _, _ = two_versions()
    assert code(withdraw, w, "9.9.9") == "PP-060"  # not published
    apply(w, withdraw(w))
    assert code(withdraw, w, "0.2.0") == "PP-060"  # already withdrawn
    assert code(withdraw, w, "0.3.0") == "PP-060"  # would leave nothing published


def test_withdrawing_urgent_version_drops_its_open_follow_up():
    w, idx, (_, urgent_id) = two_versions(urgent=True)
    assert idx["followUpOpen"] == [urgent_id]
    new = apply(w, withdraw(w, "0.3.0"))["index"]
    assert new["followUpOpen"] == [] and schema_errors("index", new) == []
    assert new["changeRecords"][0]["kind"] == "withdrawal"


def test_floor_raise_and_never_down():
    w, _, _ = two_versions()
    new = apply(w, floor(w))["index"]
    assert new["floor"] == "0.3.0" and schema_errors("index", new) == []
    for v in ("0.2.0", "0.3.0", "9.9.9"):  # lower, same, unpublished
        assert code(floor, w, v, "reason:sa:f2") == "PP-060"


def test_floor_cannot_be_raised_to_a_withdrawn_version():
    w, _, _ = two_versions()
    apply(w, withdraw(w, "0.2.0"))
    assert code(floor, w, "0.2.0", "reason:sa:f2") == "PP-060"


def test_follow_up_closure():
    w, _, (_, urgent_id) = two_versions(urgent=True)
    before = json.loads(w.store.indexes["SA"])
    c = w.pub.propose_change(kind="follow_up_closure", country="SA", target={"publishId": urgent_id}, reason_ref="review:sa:done-1")
    r = apply(w, c)
    assert r["index"]["followUpOpen"] == [] and schema_errors("index", r["index"]) == []
    assert r["index"]["published"] == before["published"] and r["index"]["floor"] == before["floor"]
    assert code(w.pub.propose_change, kind="follow_up_closure", country="SA", target={"publishId": urgent_id},
                reason_ref="review:sa:done-2") == "PP-060"


def test_closure_of_a_scheduled_version_refused():
    w, _, (first, _) = two_versions()
    assert code(w.pub.propose_change, kind="follow_up_closure", country="SA", target={"publishId": first},
                reason_ref="review:sa:x") == "PP-060"


def test_two_person_rule_and_signoff_checks():
    w, _, _ = two_versions()
    c = withdraw(w)
    assert code(w.pub.sign_change, c, role="market_accountant", signer_id=FDR, mfa=w.mfa(FDR)) == "PP-010"
    assert code(w.pub.sign_change, c, role="founder", signer_id=FDR, mfa=w.mfa(FDR, ago=900)) == "PP-013"
    sos = sign_change(w, c)
    assert code(apply, w, c, sos=sos[:1]) == "PP-012"
    assert code(apply, w, c, sos=[sos[0], sos[0]]) == "PP-012"
    forged = copy.deepcopy(sos)
    forged[0]["signerId"] = FDR
    forged[0]["mfa"]["boundTo"]["signerId"] = FDR
    assert code(apply, w, c, sos=forged) == "PP-011"
    assert code(apply, w, c, actor=Actor(FDR2, "tok:9")) == "PP-012"  # actor must be one of the signers
    assert json.loads(w.store.indexes["SA"])["withdrawn"] == [] and w.store.change_records == {}


def test_signoff_for_another_change_refused():
    w, _, _ = two_versions()
    assert code(apply, w, withdraw(w), sos=sign_change(w, withdraw(w, "0.3.0"))) == "PP-015"


def test_production_needs_signatures():
    w, _, _ = two_versions("production")
    c = withdraw(w)
    assert code(w.pub.sign_change, c, role="founder", signer_id=FDR, mfa=w.mfa(FDR)) == "PP-014"
    sos = sign_change(w, c)
    stripped = copy.deepcopy(sos)
    del stripped[1]["signerSignature"]
    assert code(apply, w, c, sos=stripped) == "PP-014"
    assert apply(w, c)["index"]["withdrawn"]


def test_altered_change_stale_index_and_audit_failure():
    w, _, _ = two_versions()
    c = withdraw(w)
    sos = sign_change(w, c)
    assert code(apply, w, dataclasses.replace(c, target={"version": "0.3.0"}), sos=sos) == "PP-020"
    before = w.store.indexes["SA"]
    w.audit.fail = True
    assert code(apply, w, c, sos=sos) == "PP-030" and w.store.indexes["SA"] == before
    w.audit.fail = False
    apply(w, floor(w), rid="chg-2")
    assert code(apply, w, c, sos=sos) == "PP-061"  # the index moved since c was proposed


def test_idempotent_replay_and_request_reuse():
    w, _, _ = two_versions()
    c = withdraw(w)
    sos = sign_change(w, c)
    r = apply(w, c, sos=sos)
    again = apply(w, c, sos=sos)
    assert again["replayed"] and again["index"] == r["index"] and len(w.store.change_records) == 1
    assert code(apply, w, floor(w)) == "PP-040"


def test_bad_input_and_no_tenant_fields():
    w, _, _ = two_versions()
    base = dict(kind="withdrawal", country="SA", target={"version": "0.2.0"}, reason_ref="r:1")
    bad = [{**base, "kind": "delete"}, {**base, "country": "XX"}, {**base, "target": {"version": "0.2.0", "tenantId": "t1"}},
           {**base, "reason_ref": " "}]
    assert [code(w.pub.propose_change, **b) for b in bad] == ["PP-001"] * 4
    assert code(w.pub.propose_change, **{**base, "country": "AE"}) == "PP-060"  # no index yet
