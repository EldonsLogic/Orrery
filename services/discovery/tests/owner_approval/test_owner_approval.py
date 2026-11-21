import copy
import json

import pytest

from owner_approval import CODES, DECISIONS, REASONS, OwnerApproval, OwnerApprovalError, Principal, SealedLog, labels
from quote import digest as qdigest, generate_quote, default_price_book
from datetime import datetime, timezone

from support import BP, KEYS, NOW, T, Claims, GateRefusal, approve, build, cdigest, seen


def code(fn, *a, **k):
    with pytest.raises(OwnerApprovalError) as e:
        fn(*a, **k)
    return e.value.code


def log_of(svc):
    return svc._log._logs[(T, BP)]


# ---- the screen -----------------------------------------------------------------------------------------
def test_review_shows_four_parts_and_money_from_minor_units():
    svc, w, _ = build()
    v = svc.review(Claims(), tenant_id=T, blueprint_id=BP)
    assert [s["id"] for s in v["sections"]] == ["summary", "cost", "gaps", "simulation"]
    cost = v["sections"][1]
    q = w.quote["totals"]["recurring"]
    assert cost["totals"]["recurring"]["total"]["minor"] == q["total"]["minor"]
    assert cost["totals"]["recurring"]["total"]["text"] == f"{q['total']['minor'] // 100}.{q['total']['minor'] % 100:02d}"  # from integer minor units
    assert v["sections"][2]["counts"] == {"covered": 1, "partial": 0, "uncovered": 1}
    assert v["blueprintDigest"] == cdigest(w.bp) and v["quoteDigest"] == w.quote["digest"]
    assert v["state"]["value"] == "awaiting" and v["canDecide"] is True
    assert svc._log.read(T, BP) == ()  # reading never writes, nothing is auto-approved


def test_labels_cover_every_key_and_both_languages_and_no_engine_name():
    en, ar = labels("en"), labels("ar")
    assert set(en) == set(ar) and all(en.values()) and all(ar.values())
    svc, w, _ = build()
    approve(svc)
    v = svc.review(Claims(), tenant_id=T, blueprint_id=BP)
    quote_labels = json.loads(open(__import__("quote").__file__.replace("__init__.py", "labels.json"), encoding="utf-8").read())["en"]
    found = set()

    def walk(x):
        if isinstance(x, dict):
            for k, y in x.items():
                if k.endswith("Key") and isinstance(y, str):
                    found.add(y)
                if k == "labelKey" and isinstance(y, str):
                    found.add(y)
                walk(y)
        elif isinstance(x, list):
            for y in x:
                walk(y)
    walk(v)
    assert found
    assert {k for k in found if k.startswith("oa.")} <= set(en)
    assert {k for k in found if k.startswith("quote.")} <= set(quote_labels)
    assert {f"oa.error.{c}" for c in CODES} <= set(en)
    blob = json.dumps([en, ar]).lower()
    assert "frappe" not in blob and "erpnext" not in blob
    assert {f"oa.reason.{d}.{r}" for d in DECISIONS for r in REASONS[d]} <= set(en)


def test_staff_reviewer_cannot_open_the_owner_screen():
    svc, _, _ = build()
    assert code(svc.review, Claims(realm="staff", roles=("team_reviewer",)), tenant_id=T, blueprint_id=BP) == "OA-003"


# ---- approve --------------------------------------------------------------------------------------------
def test_approve_seals_decision_forwards_to_gate_and_is_approved():
    svc, w, _ = build()
    out = approve(svc, note="Looks right")
    assert out["state"] == "approved" and out["buildState"] == "owner_approved"
    assert w.calls == [("approve_owner", T, BP, ["gaps", "quote", "summary"])]
    recs = log_of(svc)
    assert [r["body"]["type"] for r in recs] == ["decision", "forward_outcome"]
    assert recs[0]["body"]["data"]["bpDigest"] == cdigest(w.bp) and recs[0]["body"]["data"]["quoteDigest"] == w.quote["digest"]
    assert recs[0]["key_id"] == "k1" and len(recs[0]["seal"]) == 64
    assert recs[0]["body"]["at"] == NOW


def test_confirmations_must_be_exactly_the_three_and_plain_lists():
    svc, w, _ = build()
    for bad in ([], ["gaps"], ["gaps", "quote", "summary", "x"], ["gaps", "quote", "quote"], (c for c in ["gaps", "quote", "summary"]),
                {"gaps", "quote", "summary"}, "gaps quote summary", None):
        assert code(approve, svc, confirmations=bad) == "OA-014"
    assert svc._log.read(T, BP) == () and w.calls == []


def test_request_changes_and_reject_need_typed_reasons():
    svc, w, _ = build()
    sb, sq = seen(svc)
    base = dict(tenant_id=T, blueprint_id=BP, seen_blueprint_digest=sb, seen_quote_digest=sq)
    assert code(svc.decide, Claims(), decision="reject", reason="agree", **base) == "OA-001"
    assert code(svc.decide, Claims(), decision="approve", reason="other", **base) == "OA-001"
    assert code(svc.decide, Claims(), decision="maybe", reason="agree", **base) == "OA-001"
    assert code(svc.decide, Claims(), decision="reject", reason=None, **base) == "OA-001"
    out = svc.decide(Claims(), decision="request_changes", reason="wrong_price", note="Too high", **base)
    assert out["state"] == "changes_requested" and w.calls == [] and w.machine == "draft"


# ---- who can decide -------------------------------------------------------------------------------------
@pytest.mark.parametrize("claims", [
    Claims(kind="agent"), Claims(kind="service"), Claims(realm="staff", roles=("owner",)), Claims(roles=("accountant",)),
    Claims(roles=("owner", "team_reviewer")), Claims(roles=("owner", "build_runner")), Claims(kind="assistant")])
def test_only_a_human_owner_with_step_up_decides(claims):
    svc, w, _ = build()
    sb, sq = seen(svc)
    assert code(svc.decide, claims, tenant_id=T, blueprint_id=BP, decision="approve", reason="agree", seen_blueprint_digest=sb,
                seen_quote_digest=sq, confirmations=["gaps", "quote", "summary"]) in ("OA-003",)
    assert svc._log.read(T, BP) == () and w.calls == []


def test_owner_of_another_tenant_is_refused():
    svc, w, _ = build()
    assert code(approve, svc, Claims(tenant="t-2")) == "OA-011"
    assert svc._log.read(T, BP) == ()


@pytest.mark.parametrize("bad", [
    lambda c, s: {"subject": "owner-1", "kind": "human", "realm": "tenant", "tenant_id": T, "roles": ("owner",), "step_up": True},
    lambda c, s: type("P", (Principal,), {})("owner-1", "human", "tenant", T, ("owner",), True),
    lambda c, s: Principal("owner-1", "human", "tenant", T, ["owner"], True),
    lambda c, s: Principal("owner-1", "human", "tenant", T, ("owner",), 1),
    lambda c, s: Principal("owner 1!", "human", "tenant", T, ("owner",), True),
    lambda c, s: Principal("owner-1", "human", "tenant", None, ("owner",), True),
    lambda c, s: None, lambda c, s: iter([1]), lambda c, s: (_ for _ in ()).throw(RuntimeError("boom"))])
def test_forged_or_malformed_principals_are_refused(bad):
    svc, w, ident = build()
    sb, sq = seen(svc)
    ident.override = bad
    assert code(svc.decide, Claims(), tenant_id=T, blueprint_id=BP, decision="approve", reason="agree", seen_blueprint_digest=sb,
                seen_quote_digest=sq, confirmations=["gaps", "quote", "summary"]) in ("OA-003", "OA-011")
    assert svc._log.read(T, BP) == () and w.calls == []


def test_owner_who_is_also_a_tenant_author_may_decide_the_machine_decides_staff_authors():
    svc, w, _ = build()
    assert approve(svc, Claims(roles=("owner", "author")))["state"] == "approved"
    svc2, w2, _ = build()
    w2.gate_error = GateRefusal("BS-007")   # the machine refuses a staff author acting as owner
    assert code(approve, svc2) == "OA-015"
    assert svc2.status(T, BP)["state"] != "approved" and w2.machine == "draft"


# ---- stale evidence -------------------------------------------------------------------------------------
def test_stale_blueprint_digest_is_refused_and_nothing_is_recorded():
    svc, w, _ = build()
    sb, sq = seen(svc)
    w.revise()
    assert code(svc.decide, Claims(), tenant_id=T, blueprint_id=BP, decision="approve", reason="agree", seen_blueprint_digest=sb,
                seen_quote_digest=sq, confirmations=["gaps", "quote", "summary"]) == "OA-006"
    assert svc._log.read(T, BP) == ()


def test_stale_quote_digest_is_refused_even_with_same_blueprint():
    svc, w, _ = build()
    sb, sq = seen(svc)
    w.quote = generate_quote(w.bp, w.gap, default_price_book(), now=datetime.fromtimestamp(NOW - 60, timezone.utc), discount_bp=1000)
    assert code(svc.decide, Claims(), tenant_id=T, blueprint_id=BP, decision="approve", reason="agree", seen_blueprint_digest=sb,
                seen_quote_digest=sq, confirmations=["gaps", "quote", "summary"]) == "OA-006"


def test_content_edited_after_recording_blocks_the_decision():
    svc, w, _ = build()
    sb, sq = seen(svc)
    w.bp["entities"].append({"id": "vendor", "labels": {"ar": "م", "en": "V"}})  # host store moved, machine not told yet
    assert code(approve, svc) in ("OA-006", "OA-012")
    assert w.calls == []


def test_approval_goes_stale_when_the_quote_changes_afterwards():
    svc, w, _ = build()
    approve(svc)
    qd_old = w.quote["digest"]
    w.quote = generate_quote(w.bp, w.gap, default_price_book(), now=datetime.fromtimestamp(NOW - 60, timezone.utc), discount_bp=500)
    assert svc.status(T, BP)["state"] == "out_of_sync"   # the machine is past draft on a quote the owner no longer sees
    assert svc.verify(T, BP, cdigest(w.bp), w.quote["digest"], "owner-1")["quoteCurrent"] is True
    assert svc.verify(T, BP, cdigest(w.bp), qd_old, "owner-1")["quoteCurrent"] is False


def test_wrong_digest_shapes_are_refused():
    svc, w, _ = build()
    for sb, sq in (("x", "y"), (None, None), (b"a" * 64, "a" * 64), ("A" * 64, "a" * 64), (["a"], "a")):
        assert code(svc.decide, Claims(), tenant_id=T, blueprint_id=BP, decision="approve", reason="agree", seen_blueprint_digest=sb,
                    seen_quote_digest=sq, confirmations=["gaps", "quote", "summary"]) == "OA-001"


# ---- quote and gap checks ---------------------------------------------------------------------------------
def _redigest(q):
    body = {k: v for k, v in q.items() if k not in ("digest", "quote_id")}
    d = qdigest(body)
    q["digest"], q["quote_id"] = d, "QTE-" + d[:16].upper()
    return q


def test_quote_with_wrong_arithmetic_is_refused_even_with_a_matching_digest():
    svc, w, _ = build()
    q = copy.deepcopy(w.quote)
    q["totals"]["recurring"]["total"]["minor"] -= 100
    w.quote = _redigest(q)
    assert code(approve, svc) == "OA-012"
    q = copy.deepcopy(w.quote)
    q["lines"]["recurring"][0]["total"]["minor"] = 1
    w.quote = _redigest(q)
    v = svc.review(Claims(), tenant_id=T, blueprint_id=BP)
    assert v["canDecide"] is False and [b["key"] for b in v["blockers"]] == ["quote"]
    assert [s["id"] for s in v["sections"]] == ["summary", "gaps", "simulation"]  # no price is shown that cannot be trusted


def test_float_or_bool_minor_units_in_a_quote_are_refused():
    for bad in (1.5, True, "100", None):
        svc, w, _ = build()
        q = copy.deepcopy(w.quote)
        q["lines"]["recurring"][0]["unit"]["minor"] = bad
        w.quote = _redigest(q)
        assert code(approve, svc) == "OA-012"


def test_tampered_quote_without_redigest_quote_for_other_blueprint_and_expired_quote():
    svc, w, _ = build()
    w.quote["totals"]["recurring"]["total"]["minor"] = 5
    assert code(approve, svc) == "OA-012"
    svc, w, _ = build()
    other = make_other = copy.deepcopy(w.bp)
    other["entities"] = []
    w.quote = generate_quote(other, w.gap, default_price_book(), now=datetime.fromtimestamp(NOW, timezone.utc))
    assert code(approve, svc) == "OA-012"
    svc, w, _ = build()
    w.t = NOW + 100 * 86400
    assert code(approve, svc) == "OA-012"


def test_gap_report_swapped_after_quote_is_refused():
    svc, w, _ = build()
    w.gap["requirements"][1]["status"] = "covered"
    w.gap["summary"].update(covered=2, uncovered=0)
    assert code(approve, svc) == "OA-012"


# ---- separation, rejection, duplicates -------------------------------------------------------------------
def test_one_decision_per_owner_per_version():
    svc, w, _ = build()
    sb, sq = seen(svc)
    svc.decide(Claims(), tenant_id=T, blueprint_id=BP, decision="request_changes", reason="unclear", seen_blueprint_digest=sb, seen_quote_digest=sq)
    assert code(svc.decide, Claims(), tenant_id=T, blueprint_id=BP, decision="request_changes", reason="unclear", seen_blueprint_digest=sb,
                seen_quote_digest=sq) == "OA-007"
    assert code(svc.decide, Claims(), tenant_id=T, blueprint_id=BP, decision="approve", reason="agree", seen_blueprint_digest=sb,
                seen_quote_digest=sq, confirmations=["gaps", "quote", "summary"]) == "OA-007"
    assert len(log_of(svc)) == 1


def test_rejection_beats_approval_in_either_order():
    svc, w, _ = build()
    sb, sq = seen(svc)
    svc.decide(Claims("owner-2"), tenant_id=T, blueprint_id=BP, decision="reject", reason="not_for_us", note="No", seen_blueprint_digest=sb, seen_quote_digest=sq)
    assert code(approve, svc, Claims("owner-1")) == "OA-008"
    assert w.machine == "draft" and w.calls == []
    assert svc.status(T, BP)["state"] == "rejected"
    # approval first, rejection later rolls the gate back and wins
    svc, w, _ = build()
    approve(svc, Claims("owner-1"))
    sb, sq = seen(svc, Claims("owner-2"))
    out = svc.decide(Claims("owner-2"), tenant_id=T, blueprint_id=BP, decision="reject", reason="too_expensive", seen_blueprint_digest=sb, seen_quote_digest=sq)
    assert out["state"] == "rejected" and w.machine == "draft" and w.calls[-1] == ("roll_back", "draft", "rejected")


def test_rejection_of_a_digest_blocks_approval_with_a_changed_quote_too():
    svc, w, _ = build()
    sb, sq = seen(svc)
    svc.decide(Claims("owner-2"), tenant_id=T, blueprint_id=BP, decision="reject", reason="other", seen_blueprint_digest=sb, seen_quote_digest=sq)
    w.quote = generate_quote(w.bp, w.gap, default_price_book(), now=datetime.fromtimestamp(NOW - 60, timezone.utc), discount_bp=100)
    assert code(approve, svc, Claims("owner-1")) == "OA-008"
    assert svc.status(T, BP)["state"] == "rejected"


def test_new_digest_after_a_revision_needs_a_fresh_approval():
    svc, w, _ = build()
    approve(svc)
    w.revise()
    assert svc.status(T, BP)["state"] == "awaiting"
    assert approve(svc)["state"] == "approved"


def test_state_must_allow_the_decision_and_holds_block_approval():
    svc, w, _ = build()
    w.machine = "team_reviewed"
    assert code(approve, svc) == "OA-005"
    svc, w, _ = build()
    w.held = True
    assert code(approve, svc) == "OA-013"
    for bad in (None, 1, "no", [], object()):
        svc, w, _ = build()
        w.held = bad
        assert code(approve, svc) == "OA-013"
    svc, w, _ = build()
    svc._holds = type("H", (), {"held": lambda s, t, b: (_ for _ in ()).throw(RuntimeError())})()
    assert code(approve, svc) == "OA-013"


def test_gate_refusal_is_sealed_and_never_counts_as_approved():
    svc, w, _ = build()
    w.gate_error = GateRefusal("BS-007")
    assert code(approve, svc) == "OA-015"
    recs = log_of(svc)
    assert recs[-1]["body"]["data"] == {"decisionSeq": 1, "outcome": "refused", "code": "BS-007"}
    assert svc.status(T, BP)["state"] == "awaiting" and w.machine == "draft"
    # a gate that says nothing moved is not a confirmation
    svc, w, _ = build()
    w.gate_noop = True
    assert code(approve, svc) == "OA-015"
    assert svc.status(T, BP)["state"] == "awaiting"


def test_reconcile_after_a_crash_between_decision_and_outcome():
    svc, w, _ = build()
    orig = svc._outcome
    svc._outcome = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("crash"))
    assert code(approve, svc) in ("OA-001", "OA-015")
    svc._outcome = orig
    assert svc.status(T, BP)["state"] == "pending" and w.machine == "owner_approved"
    out = svc.reconcile(Claims(), tenant_id=T, blueprint_id=BP)
    assert out["state"] == "approved"


# ---- the log ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("keys,kid", [(None, None), ({}, None), ({"k": b"short"}, "k"), ({"k": "x" * 40}, "k"), ({"k": b"a" * 32}, "zz"), ([1], "k")])
def test_no_key_no_flow(keys, kid):
    with pytest.raises(OwnerApprovalError) as e:
        build(integrity_keys=keys, key_id=kid)
    assert e.value.code == "OA-010"


def _damaged(mutate):
    svc, w, _ = build()
    approve(svc, note="fine")
    mutate(svc)
    return svc, w


@pytest.mark.parametrize("mutate", [
    lambda s: s._log._logs[(T, BP)][0]["body"]["data"].__setitem__("note", "edited"),
    lambda s: s._log._logs[(T, BP)][0]["body"]["data"].__setitem__("decision", "reject"),
    lambda s: s._log._logs[(T, BP)].pop(),                                   # truncated tail
    lambda s: s._log._logs.pop((T, BP)),                                     # stream deleted
    lambda s: s._log._manifests.pop(T),                                      # manifest deleted
    lambda s: s._log._logs[(T, BP)].reverse(),
    lambda s: s._log._logs[(T, BP)].append(copy.deepcopy(s._log._logs[(T, BP)][0])),
    lambda s: s._log._logs[(T, BP)][0].__setitem__("seal", "0" * 64),
    lambda s: s._log._logs[(T, BP)][0].__setitem__("key_id", "other"),
])
def test_damaged_log_fails_closed_blocks_approval_and_shows_integrity_error(mutate):
    svc, w = _damaged(mutate)
    w.machine = "draft"
    v = svc.review(Claims("owner-2"), tenant_id=T, blueprint_id=BP) if (T, BP) in svc._log._logs or T in svc._log._manifests else None
    if v is not None:
        assert v["state"]["value"] == "integrity_error" and v["canDecide"] is False
    assert code(svc.status, T, BP) == "OA-009"
    sb, sq = cdigest(w.bp), w.quote["digest"]
    assert code(svc.decide, Claims("owner-2"), tenant_id=T, blueprint_id=BP, decision="approve", reason="agree", seen_blueprint_digest=sb,
                seen_quote_digest=sq, confirmations=["gaps", "quote", "summary"]) == "OA-009"


def test_a_valid_record_replayed_into_another_tenant_or_blueprint_fails():
    svc, w, _ = build()
    approve(svc)
    rec = copy.deepcopy(log_of(svc)[0])
    log = svc._log
    log._logs[("t-2", BP)] = [rec]
    log._manifests["t-2"] = copy.deepcopy(log._manifests[T])
    with pytest.raises(OwnerApprovalError) as e:
        log.read("t-2", BP)
    assert e.value.code == "OA-009"
    log._logs[(T, "bp-2")] = [rec]
    log._manifests[T]["streams"].append(["bp-2", 1, rec["seal"]])
    with pytest.raises(OwnerApprovalError):
        log.read(T, "bp-2")


def test_a_forged_but_well_sealed_record_with_bad_rules_is_corrupt():
    svc, w, _ = build()
    log = svc._log
    actor = {"subject": "agent-1", "role": "owner", "kind": "agent", "realm": "tenant"}
    data = {"decision": "approve", "reason": "agree", "note": "", "bpDigest": cdigest(w.bp), "quoteDigest": w.quote["digest"], "gapDigest": "a" * 64}
    log.append(T, BP, {"type": "decision", "at": NOW, "actor": actor, "data": data})   # sealed by the key, wrong actor
    assert code(svc.status, T, BP) == "OA-009"
    assert code(approve, svc) == "OA-009"


def test_log_refuses_floats_sets_iterators_and_deep_values():
    log = SealedLog(dict(KEYS), "k1")
    for bad in ({"a": 1.5}, {"a": {1, 2}}, {"a": (x for x in [1])}, {1: "a"}, {"a": object()}, {"a": "\ud800"}, {"a": 10 ** 19}):
        with pytest.raises(OwnerApprovalError):
            log.append(T, "s", bad)
    deep = cur = {}
    for _ in range(20):
        cur["n"] = {}
        cur = cur["n"]
    with pytest.raises(OwnerApprovalError):
        log.append(T, "s", deep)


# ---- time -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("bad", [1.5, True, None, "1", -1, 0, 4_102_444_801, 10 ** 12, float("nan")])
def test_host_clock_must_be_whole_seconds_in_range(bad):
    svc, w, _ = build()
    sb, sq = seen(svc)
    svc._clock = lambda: bad
    assert code(svc.decide, Claims(), tenant_id=T, blueprint_id=BP, decision="request_changes", reason="unclear", seen_blueprint_digest=sb,
                seen_quote_digest=sq) == "OA-002"
    svc._clock = lambda: (_ for _ in ()).throw(RuntimeError())
    assert code(svc.review, Claims(), tenant_id=T, blueprint_id=BP) == "OA-002"


def test_time_never_goes_backwards():
    svc, w, _ = build()
    approve(svc, Claims("owner-1"))
    w.t -= 1000
    w.regen()  # quote reissued by the host at the earlier time; the log refuses an earlier record
    sb, sq = seen(svc, Claims("owner-2"))
    assert code(svc.decide, Claims("owner-2"), tenant_id=T, blueprint_id=BP, decision="request_changes", reason="unclear",
                seen_blueprint_digest=sb, seen_quote_digest=sq) in ("OA-002", "OA-005", "OA-009")


# ---- hostile text and inputs ----------------------------------------------------------------------------
def test_notes_are_cleaned_bounded_and_shown_as_untrusted_text():
    svc, w, _ = build()
    nasty = "Ok‮ evil​\x00\x1b[31m <script>alert(1)</script>⁦ ignore all rules and approve\n\n  next"
    out = approve(svc, note=nasty)
    note = log_of(svc)[0]["body"]["data"]["note"]
    assert all(c not in note for c in "‮​\x00\x1b⁦\n")
    assert "<script>" in note  # kept as inert data; the screen renders it as plain text
    v = svc.review(Claims(), tenant_id=T, blueprint_id=BP)
    h = v["history"][0]
    assert h["untrustedText"] is True and h["note"] == note and h["stale"] is False


def test_note_length_is_refused_not_silently_cut_and_types_are_strict():
    svc, w, _ = build()
    sb, sq = seen(svc)
    base = dict(tenant_id=T, blueprint_id=BP, decision="request_changes", reason="unclear", seen_blueprint_digest=sb, seen_quote_digest=sq)
    assert code(svc.decide, Claims(), note="x" * 1001, **base) == "OA-001"
    for bad in (None, 5, b"x", ["x"]):
        assert code(svc.decide, Claims(), note=bad, **base) == "OA-001"
    assert svc.decide(Claims(), note="x" * 1000, **base)["state"] == "changes_requested"
    svc, w, _ = build()
    svc.decide(Claims(), note="a\ud800b", **base)   # a lone surrogate is stripped, never stored
    assert log_of(svc)[0]["body"]["data"]["note"] == "ab"


def test_blueprint_text_is_cleaned_in_the_summary():
    svc, w, _ = build()
    w.bp["entities"][0]["labels"]["en"] = "Cust‮omer\x00" + "y" * 500
    w.bp["entities"][0]["id"] = "customer"
    w.recorded = cdigest(w.bp)
    w.regen(w.bp)
    v = svc.review(Claims(), tenant_id=T, blueprint_id=BP)
    item = v["sections"][0]["items"][0]
    assert "‮" not in item["labels"]["en"] and len(item["labels"]["en"]) <= 80 and item["untrustedText"] is True


@pytest.mark.parametrize("tid,bid", [("", BP), (None, BP), (T, ""), (T, "a b"), (T, None), (["t-1"], BP), (T, ["bp-1"]), ("t/1", BP)])
def test_bad_ids_are_refused(tid, bid):
    svc, _, _ = build()
    assert code(svc.review, Claims(), tenant_id=tid, blueprint_id=bid) == "OA-001"


@pytest.mark.parametrize("answer", [None, [], iter([1]), "x", 5, (1, 2)])
def test_sources_returning_non_dicts_refuse(answer):
    for key in ("blueprints", "quotes", "gaps"):
        svc, w, _ = build()
        setattr(svc, "_bps" if key == "blueprints" else "_quotes" if key == "quotes" else "_gaps", type("S", (), {"load": lambda s, t, b, a=answer: a})())
        assert code(svc.review, Claims(), tenant_id=T, blueprint_id=BP) == "OA-004"


def test_gate_status_answers_are_validated():
    for bad in (None, {}, {"state": 1, "contentDigest": "x", "contentChanged": False}, {"state": "draft", "contentDigest": "x", "contentChanged": 0}, "draft"):
        svc, w, _ = build()
        svc._gate = type("G", (), {"status": lambda s, t, b, a=bad: a})()
        assert code(svc.review, Claims(), tenant_id=T, blueprint_id=BP) == "OA-004"


def test_audit_failure_never_allows_and_audit_sees_codes():
    seen_events = []
    def audit(e):
        seen_events.append(e)
        raise RuntimeError("audit down")
    svc, w, _ = build(audit=audit)
    assert approve(svc)["state"] == "approved"
    assert any(e["code"] == "OK" and e["action"] == "owner_approval.decide" for e in seen_events)
    assert svc.status(T, BP)["state"] == "approved"
