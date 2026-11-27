import copy
import json

import pytest
from pp_support import ACC, EDITS, FDR, FDR2, HAVE_SCHEMA, World, schema_errors

from packpublish import Actor, PublishError
from packpublish.canon import canonical, digest
from packpublish.fakes import fake_signature


def code(fn, *a, **k):
    with pytest.raises(PublishError) as e:
        fn(*a, **k)
    return e.value.code


@pytest.mark.skipif(not HAVE_SCHEMA, reason="needs jsonschema and referencing: uv run --with jsonschema --with referencing")
def test_schemas_checked():
    assert schema_errors("pin", {"v": 1}) != []  # the validator really runs, so [] elsewhere means valid


def test_happy_path_every_output_validates():
    w = World()
    d, r = w.publish()
    assert schema_errors("record", r["record"]) == []
    assert schema_errors("index", r["index"]) == []
    assert r["index"]["indexSeq"] == 1 and r["index"]["predecessorDigest"] is None
    assert r["record"]["contentDigest"] == d.content_digest and r["record"]["predecessor"] is None
    assert not r["replayed"] and r["auditId"] in w.audit.entries
    e = w.audit.entries[r["auditId"]]
    assert e["actor"] == {"kind": "staff", "subject": FDR, "tokenId": "tok:1"}
    assert w.store.indexes["SA"] == canonical(r["index"])


def test_production_happy_path_validates_with_signatures():
    w = World("production")
    _, r = w.publish()
    assert schema_errors("record", r["record"]) == []
    assert all("signerSignature" in s for s in r["record"]["signOffs"])


def test_draft_content_digest_is_exact_and_deterministic():
    w = World()
    a, b = w.draft(), w.draft()
    assert a == b and a.content_digest.startswith("sha256:")
    assert w.draft(edits=EDITS[:1]).content_digest != a.content_digest
    pack = json.loads(a.files["pack.json"])
    assert pack["version"] == "0.2.0" and pack["formats"]["numberSystem"] == "arab"


def test_same_person_both_roles_refused():
    w = World()
    d = w.draft()
    assert code(w.sign, d, FDR, "market_accountant") == "PP-010"  # a founder is never the accountant
    sos = w.signed(d)
    forged = copy.deepcopy(sos)
    forged[0]["signerId"] = FDR
    forged[0]["mfa"]["boundTo"]["signerId"] = FDR
    assert code(w.pub.publish, "r", d, forged, Actor(FDR, "tok:1")) == "PP-011"
    assert w.store.indexes == {} and w.audit.entries == {}


def test_accountant_not_on_roster_refused():
    w = World()
    d = w.draft()
    assert code(w.sign, d, "staff:acct-sa-99", "market_accountant") == "PP-010"
    w.trusted.accountants[("AE", "staff:acct-ae-01")] = "Other market"  # on another market's roster only
    assert code(w.sign, d, "staff:acct-ae-01", "market_accountant") == "PP-010"
    assert code(w.sign, d, "staff:nobody", "founder") == "PP-010"
    sos = w.signed(d)
    del w.trusted.accountants[("SA", ACC)]  # removed from the roster before publish
    assert code(w.pub.publish, "r", d, sos, Actor(FDR, "tok:1")) == "PP-010"


def test_production_without_signatures_refused():
    w = World("production")
    d = w.draft()
    assert code(w.sign, d, ACC, "market_accountant", sig=False) == "PP-014"
    assert code(w.sign, d, FDR, "founder", sig=False) == "PP-014"
    other = fake_signature(ACC, d.statement_digest)  # another person's assertion
    assert code(w.pub.sign_off, d, role="founder", signer_id=FDR, mfa=w.mfa(FDR), signature=other) == "PP-014"
    sos = w.signed(d)  # valid, then a signature stripped before publish
    del sos[1]["signerSignature"]
    assert code(w.pub.publish, "r", d, sos, Actor(FDR, "tok:1")) == "PP-014"
    assert w.store.indexes == {} and w.audit.entries == {}


def test_outside_production_publisher_key_alone_may_publish():
    w = World("staging")
    _, r = w.publish(sos=w.signed(w.draft(), sig=False))
    assert schema_errors("record", r["record"]) == []


def test_audit_failure_refused_and_index_unchanged():
    w = World()
    _, first = w.publish()
    before = dict(w.store.indexes)
    w.audit.fail = True
    d = w.draft(base=w.last_files, version="0.3.0")
    assert code(w.pub.publish, "req-2", d, w.signed(d), Actor(FDR, "tok:1")) == "PP-030"
    assert w.store.indexes == before and len(w.store.records) == 1 and "req-2" not in w.store.requests
    w.audit.fail = False  # the same request id may be tried again once audit is back
    assert w.pub.publish("req-2", d, w.signed(d), Actor(FDR, "tok:1"))["index"]["indexSeq"] == 2


def test_idempotent_replay_changes_nothing():
    w = World()
    d, r = w.publish(rid="req-9")
    snap = (dict(w.store.indexes), dict(w.audit.entries))
    again = w.pub.publish("req-9", d, w.signed(d), Actor(FDR, "tok:1"))
    assert again["replayed"] and again["record"] == r["record"] and again["index"] == r["index"]
    assert (w.store.indexes, w.audit.entries) == snap
    d2 = w.draft(edits=EDITS[:1])  # same request id, other content
    assert code(w.pub.publish, "req-9", d2, w.signed(d2), Actor(FDR, "tok:1")) == "PP-040"


def test_predecessor_chain():
    w = World()
    _, r1 = w.publish()
    base2 = w.last_files
    d2 = w.draft(base=base2, version="0.3.0", edits=[{"file": "pack.json", "path": "tax.codes.0", "op": "set", "value": "E"}])
    _, r2 = w.publish(d2, rid="req-2")
    assert r2["index"]["indexSeq"] == 2 and r2["index"]["predecessorDigest"] == digest(canonical(r1["index"]))
    assert [e["version"] for e in r2["index"]["published"]] == ["0.2.0", "0.3.0"]
    assert r2["record"]["predecessor"] == {"version": "0.2.0", "contentDigest": r1["record"]["contentDigest"]}
    assert schema_errors("index", r2["index"]) == [] and schema_errors("record", r2["record"]) == []
    # a stale version, or a draft not based on the latest release, is refused
    stale = w.draft(base=base2, version="0.2.5", edits=[])
    assert code(w.pub.publish, "r3", stale, w.signed(stale), Actor(FDR, "tok:1")) == "PP-021"
    off_chain = w.draft(version="0.4.0")  # based on 0.1.0, not on 0.3.0
    assert code(w.pub.publish, "r4", off_chain, w.signed(off_chain), Actor(FDR, "tok:1")) == "PP-021"


def test_urgent_needs_review_ref_and_opens_follow_up():
    w = World()
    assert code(w.draft, change_kind="urgent") == "PP-022"
    assert code(w.draft, review_ref="review:sa:1") == "PP-022"
    _, r = w.publish(w.draft(change_kind="urgent", review_ref="review:sa:urgent-01"))
    assert r["record"]["followUp"] == {"required": True, "reviewRef": "review:sa:urgent-01"}
    assert r["index"]["followUpOpen"] == [r["record"]["publishId"]]
    assert schema_errors("record", r["record"]) == []


def test_altered_draft_and_wrong_actor_refused():
    w = World()
    d = w.draft()
    sos = w.signed(d)
    files = dict(d.files)
    files["pack.json"] = files["pack.json"].replace(b"arab", b"latn")
    import dataclasses
    assert code(w.pub.publish, "r", dataclasses.replace(d, files=files), sos, Actor(FDR, "tok:1")) == "PP-020"
    assert code(w.pub.publish, "r", d, sos, Actor(FDR2, "tok:1")) == "PP-012"  # publisher must be a signer
    assert code(w.pub.publish, "r", d, sos[:1], Actor(FDR, "tok:1")) == "PP-012"
    old = w.signed(d)
    old[0]["mfa"]["authTime"] = "2030-03-17T16:00:00Z"  # step-up older than 300 s before signing
    assert code(w.pub.publish, "r", d, old, Actor(FDR, "tok:1")) == "PP-013"


def test_diff_is_deterministic_and_classified():
    w = World()
    a, b = w.draft(), w.draft(edits=list(reversed(EDITS)))
    assert a.changes == b.changes and a.diff_digest == b.diff_digest
    by = {c["path"]: c for c in a.changes}
    assert by["formats.numberSystem"] == {"file": "pack.json", "path": "formats.numberSystem", "op": "changed",
                                          "before": "latn", "after": "arab", "class": "product_choice"}
    assert by["tax.roundingRule"]["class"] == "statutory" and "version" not in by
    assert [c["path"] for c in a.changes] == sorted(by)
    d = w.draft(edits=[{"file": "pack.json", "path": "tax.codes.1", "op": "delete"},
                       {"file": "evidence.json", "path": "facts.0", "op": "set", "value": {"claim": "x"}}] )
    ops = {(c["file"], c["path"]): (c["op"], c["class"]) for c in d.changes}
    assert ops[("pack.json", "tax.codes.1")] == ("removed", "statutory")
    assert ops[("evidence.json", "facts.0")] == ("added", "statutory")


def test_edits_cannot_touch_identity_or_missing_paths_or_floats():
    w = World()
    for e in ({"file": "pack.json", "path": "countryCode", "op": "set", "value": "AE"},
              {"file": "pack.json", "path": "nope.deep", "op": "set", "value": 1},
              {"file": "pack.json", "path": "tax.rate", "op": "set", "value": 0.15},
              {"file": "other.json", "path": "a", "op": "set", "value": 1}):
        assert code(w.draft, edits=[e]) in ("PP-002", "PP-003")


def _pin(w, tenant="tenant-1", version="0.3.0", seq=4):
    pid = w.last["record"]["publishId"]
    w.store.pins[(tenant, "SA")] = {
        "v": 1, "typ": "country_pack_pin", "tenantId": tenant, "source": "store", "countryCode": "SA", "packId": "sa",
        "version": version, "contentDigest": w.last["record"]["contentDigest"], "publishId": pid, "indexSeqAtPin": 2,
        "pinSeq": seq, "changeKind": "upgrade", "changedBy": {"actorKind": "staff", "subject": FDR, "tokenId": "t"},
        "approval": {"kind": "accountant_boundary", "ref": "approval:1", "scheduleRef": "schedule:1"},
        "changedAt": "2030-03-17T17:46:40Z", "auditId": "audit:x"}


def _two_releases(w):
    w.publish()
    d = w.draft(base=w.last_files, version="0.3.0", edits=[{"file": "pack.json", "path": "tax.codes.0", "op": "set", "value": "E"}])
    w.publish(d, rid="req-2")
    _pin(w)


def rollback(w, **kw):
    args = dict(tenant_id="tenant-1", country="SA", target_version="0.2.0", actor=Actor(FDR, "tok:9"),
                step_up={"ref": "stepup:staff:founder-a:09", "authTime": "2030-03-17T17:45:40Z"},
                reason_ref="reason:sa:rollback-01", approval_ref="approval:sa:rollback-01")
    args.update(kw)
    return w.pub.rollback_pin("rb-1", **args)


def test_rollback_happy_path_validates_and_is_idempotent():
    w = World()
    _two_releases(w)
    r = rollback(w)
    pin = r["pin"]
    assert schema_errors("pin", pin) == [] and pin["pinSeq"] == 5 and pin["version"] == "0.2.0"
    assert pin["auditId"] == r["auditId"] in w.audit.entries and pin["indexSeqAtPin"] == 2
    assert w.audit.entries[r["auditId"]]["actor"]["tokenId"] == "tok:9"
    assert rollback(w)["replayed"] and len(w.store.pin_log) == 1


def test_rollback_approval_rules():
    w = World()
    _two_releases(w)
    assert code(rollback, w, actor=Actor(ACC, "t")) == "PP-051"  # an accountant cannot approve a rollback
    assert code(rollback, w, actor=Actor("staff:someone", "t")) == "PP-051"
    assert code(rollback, w, step_up={"ref": "stepup:1", "authTime": "2030-03-17T17:30:00Z"}) == "PP-051"  # stale
    assert code(rollback, w, step_up={"ref": "stepup:1", "authTime": "2030-03-17T17:50:00Z"}) == "PP-051"  # future
    assert code(rollback, w, reason_ref="") == "PP-051"
    assert code(rollback, w, target_version="0.3.0") == "PP-050"  # not an earlier version
    assert code(rollback, w, target_version="0.1.5") == "PP-050"  # never published
    w.audit.fail = True
    assert code(rollback, w) == "PP-030" and w.store.pin_log == []
    w.audit.fail = False
    idx = json.loads(w.store.indexes["SA"])
    idx["withdrawn"].append({"version": "0.2.0", "contentDigest": idx["published"][0]["contentDigest"], "reasonRef": "r:1"})
    idx["published"] = idx["published"][1:]
    w.store.indexes["SA"] = canonical(idx)
    assert code(rollback, w) == "PP-050"  # withdrawn
    idx["withdrawn"], idx["floor"] = [], "0.3.0"
    idx["published"] = [{"version": "0.2.0", "contentDigest": "sha256:" + "0" * 64, "publishId": "0" * 26}, idx["published"][0]]
    w.store.indexes["SA"] = canonical(idx)
    assert code(rollback, w) == "PP-050"  # below the floor
