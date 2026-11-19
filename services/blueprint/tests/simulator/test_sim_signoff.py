"""BPL-019: review rules, owner sign-off view model, sign-off records and the gate evidence."""
import copy
import datetime as dt
import json
import re
from decimal import Decimal

import pytest

import sim_helpers as h
from simulator import review, signoff, validate_report
from simulator.codes import CODES

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 11, 19, 10, 0, tzinfo=UTC)
Signer = signoff.Signer


def who(subject, *roles, kind="human", tenant=h.TENANT):
    return Signer(tenant_id=tenant, subject=subject, role_ids=tuple(roles), kind=kind)


OWNER = who("u-owner", "owner")
ACCT = who("u-acct", "accountant")


def base():
    return h.run()[0]


def decide(report, actor, decision="accepted", records=(), role=None, note="checked with accountant", **kw):
    view = review.build_view(report, records=records)
    ack = kw.pop("acknowledged", view["signOff"]["toAcknowledge"])
    return signoff.record_decision(report, records, actor=actor, role=role or actor.role_ids[0], decision=decision,
                                   decided_at=kw.pop("decided_at", T0), now=kw.pop("now", T0), note=note,
                                   acknowledged=ack, **kw)


def row_report(**row):
    r = base()
    r = copy.deepcopy(r)
    r["comparison"] = [dict({"metric": "sales_net", "currency": "SAR", "expectedMinor": 100000, "actualMinor": 100000,
                             "differenceMinor": 0, "toleranceMinor": 0, "documents": 1, "lines": 1,
                             "status": "match", "reason": None}, **row)]
    return r


# ---- review rules (deterministic, integer arithmetic) ----
def _rules(report):
    """Row rules only: a one-row report with a mismatch also has nothing compared (SIM-135), tested apart."""
    return [a for a in review.review_anomalies(report) if a.code != "SIM-135"]


def test_derived_rules():
    flip = _rules(row_report(actualMinor=-5000, differenceMinor=-105000, status="mismatch"))
    assert {a.code for a in flip} == {"SIM-132"}
    zero = _rules(row_report(actualMinor=0, differenceMinor=-100000, status="mismatch"))
    assert {a.code for a in zero} == {"SIM-133"}
    big = _rules(row_report(actualMinor=150000, differenceMinor=50000, status="mismatch"))
    assert [a.code for a in big] == ["SIM-136"] and big[0].params["basisPoints"] == 5000
    edge = _rules(row_report(actualMinor=100002, differenceMinor=2, toleranceMinor=2,
                                              status="within_tolerance"))
    assert [a.code for a in edge] == ["SIM-134"]
    assert _rules(row_report()) == []


def test_nothing_compared_is_blocking():
    r = copy.deepcopy(base())
    for row in r["comparison"]:
        row["status"] = "not_compared"
    assert "SIM-135" in {a.code for a in review.review_anomalies(r)}
    r["comparison"] = []
    assert "SIM-135" in {a.code for a in review.review_anomalies(r)}


def test_no_float_and_huge_numbers():
    big = 10 ** 30
    out = _rules(row_report(expectedMinor=big, actualMinor=big * 2, differenceMinor=big,
                                             status="mismatch"))
    assert out[0].params["basisPoints"] == 10000 and isinstance(out[0].params["basisPoints"], int)


# ---- view model ----
def test_view_money_is_decimal_text_and_exact():
    v = review.build_view(base())
    row = next(r for r in v["rows"] if r["metric"] == "vat_output")
    assert isinstance(row["expected"], str) and isinstance(row["difference"], str)
    assert row["difference"] == "0.01" and row["statusKey"] == "signoff.status.within_tolerance"
    assert Decimal(row["actual"]) - Decimal(row["expected"]) == Decimal("0.01")

    def walk(x):
        assert not isinstance(x, float)
        for y in (x.values() if isinstance(x, dict) else x if isinstance(x, list) else []):
            walk(y)
    walk(v)


def test_view_three_decimal_currency():
    r = row_report(currency="KWD", expectedMinor=1234567, actualMinor=1234567)
    assert review.build_view(r)["rows"][0]["expected"] == "1234.567"


def test_view_deterministic_and_does_not_mutate():
    r = base()
    before = json.dumps(r, sort_keys=True)
    a, b = review.build_view(r), review.build_view(r)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True) and json.dumps(r, sort_keys=True) == before


def test_view_keys_are_i18n_keys_with_en_and_ar_labels():
    keys = set()
    v = review.build_view(base())

    def collect(x):
        if isinstance(x, dict):
            for k, y in x.items():
                if k.endswith("Key") and isinstance(y, str):
                    keys.add(y)
                collect(y)
        elif isinstance(x, list):
            for y in x:
                collect(y)
    collect(v)
    keys |= {f"sim.{n}" for n, _ in CODES.values()} | set(signoff.ALL_LABEL_KEYS)
    en, ar = review.labels("en"), review.labels("ar")
    assert keys <= set(en) and keys <= set(ar)
    for k in keys:
        assert re.search(r"[؀-ۿ]", ar[k]), k  # Arabic text, not a copy of English
        assert set(re.findall(r"\{\w+\}", en[k])) == set(re.findall(r"\{\w+\}", ar[k])), k
    with pytest.raises(ValueError):
        review.labels("fr")


def test_hostile_source_text_stays_data():
    r = copy.deepcopy(base())
    r["anomalies"].append({"code": "SIM-106", "severity": "warning", "messageKey": "sim.possible_duplicate",
                           "sourceIds": ["<script>alert(1)</script>‮"], "params": {"party": "'; DROP TABLE x;--‮"}})
    v = review.build_view(r)
    blob = json.dumps(v, ensure_ascii=False)
    assert "‮" not in blob
    a = next(x for x in v["anomalies"] if "<script>" in json.dumps(x))
    assert a["messageKey"] == "sim.possible_duplicate" and "label" not in a  # text only via keys; params are data


def test_arabic_params_survive():
    r = copy.deepcopy(base())
    r["anomalies"].append({"code": "SIM-106", "severity": "warning", "messageKey": "sim.possible_duplicate",
                           "sourceIds": ["فاتورة-١"], "params": {"party": "شركة النور للتجارة"}})
    v = review.build_view(r)
    assert any(a["params"].get("party") == "شركة النور للتجارة" for a in v["anomalies"])


def test_malformed_report_refused():
    for bad in (None, {}, {"comparison": 3}, []):
        with pytest.raises(review.ReviewError):
            review.build_view(bad)
    r = copy.deepcopy(base())
    r["tenantId"] = 5
    with pytest.raises(review.ReviewError):
        review.build_view(r)


def test_view_starts_unsigned_and_never_decides():
    v = review.build_view(base())
    assert v["signOff"]["state"] == "awaiting" and v["signOff"]["records"] == []
    assert v["gate"]["eligible"] is False and v["gate"]["evidenceOnly"] is True


# ---- sign-off ----
def test_accept_records_who_and_when():
    r = base()
    recs = decide(r, OWNER)
    assert len(recs) == 1 and recs[0].user_id == "u-owner" and recs[0].decided_at == "2026-11-19T10:00:00.000Z"
    assert recs[0].report_digest == review.report_digest(r)
    v = review.build_view(r, records=recs)
    assert v["signOff"]["state"] == "accepted"
    assert v["signOff"]["records"][0]["userId"] == "u-owner"


def test_no_default_decision_and_no_auto_accept():
    import inspect
    sig = inspect.signature(signoff.record_decision)
    for name in ("decision", "decided_at", "now", "actor", "acknowledged"):
        assert sig.parameters[name].default is inspect.Parameter.empty
    assert review.build_view(base())["signOff"]["state"] != "accepted"


def test_agents_and_wrong_roles_cannot_sign():
    r = base()
    with pytest.raises(signoff.SignOffError) as e:
        decide(r, who("bot", "owner", kind="agent"), role="owner")
    assert e.value.code == "SO-E02"
    with pytest.raises(signoff.SignOffError) as e:
        decide(r, who("svc", "owner", kind="service"), role="owner")
    assert e.value.code == "SO-E02"
    with pytest.raises(signoff.SignOffError) as e:
        decide(r, who("u2", "clerk"), role="owner")
    assert e.value.code == "SO-E03"
    with pytest.raises(signoff.SignOffError):
        decide(r, who("", "owner"))
    with pytest.raises(signoff.SignOffError):
        decide(r, who("u‮1", "owner"))
    with pytest.raises(signoff.SignOffError) as e:  # a caller-asserted dict is not a verified principal
        decide(r, {"userId": "x", "roles": ["owner"], "kind": "human"}, role="owner")
    assert e.value.code == "SO-E02"


def test_decision_and_time_validation():
    r = base()
    with pytest.raises(signoff.SignOffError):
        decide(r, OWNER, decision="auto")
    with pytest.raises(signoff.SignOffError):
        decide(r, OWNER, decision=True)
    with pytest.raises(signoff.SignOffError):
        decide(r, OWNER, decided_at=dt.datetime(2026, 11, 19))  # naive
    with pytest.raises(signoff.SignOffError):
        decide(r, OWNER, decided_at="2026-11-19")


def test_accept_needs_acknowledgement_of_every_warning():
    r = base()
    ack = review.build_view(r)["signOff"]["toAcknowledge"]
    assert ack, "the synthetic month has warnings (held posting)"
    with pytest.raises(signoff.SignOffError) as e:
        decide(r, OWNER, acknowledged=ack[:-1])
    assert e.value.code == "SO-E06"
    with pytest.raises(signoff.SignOffError):
        decide(r, OWNER, acknowledged=[])
    with pytest.raises(signoff.SignOffError) as e:
        decide(r, OWNER, note="  ")
    assert e.value.code == "SO-E07"


def test_cannot_accept_blocked_or_aborted_but_can_reject():
    r = copy.deepcopy(base())
    r["verdict"] = "blocked"
    r["summary"]["blocking"] = 1
    assert review.build_view(r)["signOff"]["canAccept"] is False
    with pytest.raises(signoff.SignOffError) as e:
        decide(r, OWNER, acknowledged=[])
    assert e.value.code == "SO-E05"
    assert decide(r, OWNER, decision="rejected", acknowledged=[])[0].decision == "rejected"
    a = copy.deepcopy(base())
    a["verdict"], a["status"] = "aborted", "aborted"
    assert review.build_view(a)["signOff"]["canAccept"] is False


def test_derived_blocking_rule_blocks_accept():
    r = row_report(actualMinor=0, differenceMinor=-100000, status="mismatch")
    v = review.build_view(r)
    assert v["verdict"] == "blocked" and v["signOff"]["canAccept"] is False


def test_decision_is_final_per_role_and_append_only():
    r = base()
    recs = decide(r, OWNER)
    with pytest.raises(signoff.SignOffError) as e:
        decide(r, OWNER, records=recs, decision="rejected")
    assert e.value.code == "SO-E04"
    assert isinstance(recs, tuple)
    more = decide(r, ACCT, records=recs)
    assert more[:1] == recs and len(more) == 2


def test_same_person_cannot_hold_both_roles():
    both = who("u1", "owner", "accountant")
    r = base()
    recs = decide(r, both, role="owner")
    with pytest.raises(signoff.SignOffError) as e:
        decide(r, both, role="accountant", records=recs)
    assert e.value.code == "SO-E08"


def test_signoff_is_bound_to_the_report_content():
    r = base()
    recs = decide(r, OWNER)
    changed = copy.deepcopy(r)
    changed["comparison"][0]["expectedMinor"] += 1
    assert review.report_digest(changed) != review.report_digest(r)
    v = review.build_view(changed, records=recs)
    assert v["signOff"]["state"] == "awaiting" and v["signOff"]["staleRecords"] == 1
    assert signoff.gate_evidence(changed, recs)["eligible"] is False
    # filling sign-off fields in the report does not change its digest
    assert review.report_digest(signoff.apply_signoffs(r, recs)) == review.report_digest(r)


def test_apply_signoffs_fills_schema_valid_report():
    r = base()
    recs = decide(r, OWNER)
    recs = decide(r, ACCT, records=recs)
    out = signoff.apply_signoffs(r, recs)
    assert validate_report(out) == []
    assert out["signOff"]["owner"] == {"userId": "u-owner", "decision": "accepted",
                                       "decidedAt": "2026-11-19T10:00:00.000Z", "note": "checked with accountant"}
    assert r["signOff"]["owner"]["userId"] is None  # input untouched


def test_hostile_note_is_cleaned_and_capped():
    r = base()
    recs = decide(r, OWNER, note="ok‮\x00 " + "ا" * 5000)
    assert "‮" not in recs[0].note and "\x00" not in recs[0].note and len(recs[0].note) <= 2000
    assert "ا" in recs[0].note


def test_gate_evidence_is_evidence_only():
    r = base()
    assert signoff.gate_evidence(r, ())["eligible"] is False
    assert signoff.gate_evidence(r, ())["missingRoles"] == ["owner"]
    recs = decide(r, OWNER)
    g = signoff.gate_evidence(r, recs)
    assert g["eligible"] is True and g["evidenceOnly"] is True and g["gate"] == "BPL-020"
    assert g["reportDigest"] == review.report_digest(r) and g["simulationId"] == r["simulationId"]
    assert "approved" not in g and "live" not in json.dumps(g).replace("BPL-020", "")
    two = signoff.gate_evidence(r, recs, required_roles=("owner", "accountant"))
    assert two["eligible"] is False and two["missingRoles"] == ["accountant"]
    rej = decide(r, OWNER, decision="rejected")
    assert signoff.gate_evidence(r, rej)["eligible"] is False


def test_unknown_required_role_refused():
    with pytest.raises(signoff.SignOffError):
        signoff.gate_evidence(base(), (), required_roles=("janitor",))


# ---- review fixes: records are validated, never trusted (H1, M1) ----
def forged(report, role="owner", user="u-x", decision="accepted", **kw):
    f = dict(tenant_id=report["tenantId"], simulation_id=report["simulationId"], report_digest=review.report_digest(report),
             role=role, user_id=user, decision=decision, decided_at="2026-11-19T10:00:00.000Z", note="", acknowledged=())
    f.update(kw)
    return review.SignOffRecord(**f)


def raw(report, actor, records, decision="accepted", ack=None):
    """record_decision without reading `records` first (they may be a one-shot iterator)."""
    ack = review.build_view(report)["signOff"]["toAcknowledge"] if ack is None else ack
    return signoff.record_decision(report, records, actor=actor, role=actor.role_ids[0], decision=decision,
                                   decided_at=T0, now=T0, note="checked", acknowledged=ack)


def test_malformed_records_fail_closed():
    r = base()
    bad = [forged(r, decided_at="x"), forged(r, role="janitor"), forged(r, decision="auto"), forged(r, user="u‮"),
           forged(r, report_digest="abc"), forged(r, decision="rejected", acknowledged=("0" * 16,)),
           forged(r, acknowledged=(1,)), forged(r, decided_at="0005-01-01T00:00:00.000Z")]
    for rec in bad + [{"role": "owner"}]:
        with pytest.raises(review.ReviewError) as e:
            review.build_view(r, records=[rec])
        assert e.value.code == "RV-E03"
        with pytest.raises(signoff.SignOffError):
            signoff.gate_evidence(r, [rec])
    for junk in (None, "owner", {"a": 1}, 5):
        with pytest.raises(review.ReviewError):
            review.build_view(r, records=junk)


def test_duplicate_role_cannot_hide_a_rejection():
    r = base()
    rej, acc = forged(r, user="u-a", decision="rejected"), forged(r, user="u-b")
    for recs in ([rej, acc], [acc, rej]):
        with pytest.raises(review.ReviewError) as e:
            review.build_view(r, records=recs)
        assert e.value.code == "RV-E04"
        with pytest.raises(signoff.SignOffError):
            signoff.gate_evidence(r, recs)
        with pytest.raises(signoff.SignOffError) as e:
            raw(r, ACCT, recs)
        assert e.value.code == "SO-E09"
    same_user = [forged(r), forged(r, role="accountant")]
    with pytest.raises(review.ReviewError):
        review.build_view(r, records=same_user)


def test_any_rejection_wins_in_any_order():
    r = base()
    o, a = forged(r, user="u-o"), forged(r, role="accountant", user="u-a", decision="rejected")
    for recs in ((o, a), (a, o)):
        assert review.sign_off_state(recs, ("owner",)) == "rejected"
        assert signoff.gate_evidence(r, recs)["eligible"] is False
    # Defence in depth: even if duplicates slipped past the integrity check, a rejection is never overridden.
    rej, acc = forged(r, user="u-a", decision="rejected"), forged(r, user="u-b")
    assert review.sign_off_state((rej, acc), ("owner",)) == "rejected"
    assert review.sign_off_state((acc, rej), ("owner",)) == "rejected"


def test_record_from_another_tenant_fails_closed():
    r = base()
    with pytest.raises(review.ReviewError) as e:
        review.build_view(r, records=[forged(r, tenant_id="other-tenant")])
    assert e.value.code == "RV-E04"


def test_records_for_another_simulation_are_stale():
    r = base()
    v = review.build_view(r, records=[forged(r, simulation_id="sim-other")])
    assert v["signOff"]["state"] == "awaiting" and v["signOff"]["staleRecords"] == 1


def test_iterator_records_keep_earlier_decisions():
    r = base()
    recs = decide(r, OWNER)
    with pytest.raises(signoff.SignOffError) as e:
        raw(r, OWNER, iter(recs), decision="rejected", ack=[])
    assert e.value.code == "SO-E04"
    more = raw(r, ACCT, iter(recs))
    assert [x.role for x in more] == ["owner", "accountant"]
    assert signoff.gate_evidence(r, iter(recs))["eligible"] is True
    assert review.build_view(r, records=iter(recs))["signOff"]["state"] == "accepted"
    assert signoff.apply_signoffs(r, iter(recs))["signOff"]["owner"]["decision"] == "accepted"


# ---- the verdict is recomputed, never trusted (H2) ----
def test_inconsistent_report_verdict_is_recomputed():
    a = copy.deepcopy(base())
    a["status"], a["verdict"] = "aborted", "pass"
    assert review.build_view(a)["verdict"] == "aborted"
    b = copy.deepcopy(base())
    b["anomalies"].append({"code": "SIM-121", "severity": "blocking", "messageKey": "sim.total_mismatch",
                           "sourceIds": [], "params": {}})
    b["summary"]["blocking"] = 5
    assert review.build_view(b)["verdict"] == "blocked"
    with pytest.raises(signoff.SignOffError) as e:
        decide(b, OWNER)
    assert e.value.code == "SO-E05"
    for key in ("blocking", "mismatched", "inDoubt"):
        c = copy.deepcopy(base())
        c["summary"][key], c["verdict"] = 1, "pass"
        assert review.build_view(c)["signOff"]["canAccept"] is False, key
    d = copy.deepcopy(base())
    d["inDoubt"] = ["step-1"]
    assert review.build_view(d)["verdict"] == "blocked"
    e2 = copy.deepcopy(base())
    e2["verdict"] = "blocked"  # a stored verdict can only make it stricter
    assert review.build_view(e2)["verdict"] == "blocked"
    clean = row_report()
    for k in ("held", "parked", "warnings", "notCompared"):
        clean["summary"][k] = 0
    clean["anomalies"], clean["verdict"] = [], "pass_with_warnings"
    assert review.build_view(clean)["verdict"] == "pass_with_warnings"


def test_accepted_record_on_blocked_report_is_not_eligible():
    b = copy.deepcopy(base())
    b["summary"]["blocking"] = 1
    g = signoff.gate_evidence(b, [forged(b)])
    assert g["verdict"] == "blocked" and g["eligible"] is False


def test_unknown_anomaly_code_blocks():
    r = copy.deepcopy(base())
    before = review.build_view(r)["signOff"]["toAcknowledge"]
    r["anomalies"].append({"code": "SIM-199", "severity": "warning", "messageKey": "sim.future",
                           "sourceIds": ["x1"], "params": {}})
    v = review.build_view(r)
    assert any(a["code"] == "SIM-138" and a["params"]["code"] == "SIM-199" for a in v["anomalies"])
    assert v["verdict"] == "blocked" and v["signOff"]["canAccept"] is False
    assert v["signOff"]["toAcknowledge"] == before
    assert decide(r, OWNER, decision="rejected", acknowledged=[])[0].decision == "rejected"


# ---- the signer is a verified human of the report's tenant (H3) ----
def test_signer_from_another_tenant_is_refused():
    with pytest.raises(signoff.SignOffError) as e:
        decide(base(), who("u-owner", "owner", tenant="other-tenant"))
    assert e.value.code == "SO-E11"


# ---- time bounds (M3) ----
class _NoOffset(dt.tzinfo):
    def utcoffset(self, d):
        return None


def test_decided_at_bounds():
    r = base()
    for when, now in ((T0 + dt.timedelta(hours=1), T0), (T0 - dt.timedelta(days=30), T0),
                      (dt.datetime(5, 1, 1, tzinfo=UTC), dt.datetime(5, 1, 1, tzinfo=UTC)),
                      (T0.replace(tzinfo=_NoOffset()), T0.replace(tzinfo=_NoOffset())),
                      (T0, T0.replace(tzinfo=None)), (T0, "now")):
        with pytest.raises(signoff.SignOffError) as e:
            decide(r, OWNER, decided_at=when, now=now)
        assert e.value.code == "SO-E01"
    ok = decide(r, OWNER, decided_at=T0 + dt.timedelta(microseconds=123456), now=T0)
    assert ok[0].decided_at == "2026-11-19T10:00:00.123Z"
    riyadh = dt.timezone(dt.timedelta(hours=3))
    assert decide(r, OWNER, decided_at=T0.astimezone(riyadh))[0].decided_at == "2026-11-19T10:00:00.000Z"


# ---- numbers (M4 and LOW) ----
def test_floats_huge_integers_and_deep_nesting_refused():
    for mutate in (lambda x: x["comparison"][0].__setitem__("expectedMinor", float(x["comparison"][0]["expectedMinor"])),
                   lambda x: x["comparison"][0].__setitem__("documents", 1.0),
                   lambda x: x["comparison"][0].__setitem__("expectedMinor", 10 ** 40)):
        r = copy.deepcopy(base())
        mutate(r)
        with pytest.raises(review.ReviewError) as e:
            review.build_view(r)
        assert e.value.code == "RV-E01"
    deep = {}
    cur = deep
    for _ in range(3000):
        cur["a"] = {}
        cur = cur["a"]
    r = copy.deepcopy(base())
    r["anomalies"].append({"code": "SIM-106", "severity": "warning", "messageKey": "sim.possible_duplicate",
                           "sourceIds": [], "params": deep})
    with pytest.raises(review.ReviewError):
        review.build_view(r)


# ---- nothing compared and the rule edges (M5) ----
def test_trivial_zero_row_does_not_count_as_compared():
    r = copy.deepcopy(base())
    for row in r["comparison"]:
        row["status"] = "not_compared"
    r["comparison"].append({"metric": "sales_net", "currency": "SAR", "expectedMinor": 0, "actualMinor": 0,
                            "differenceMinor": 0, "toleranceMinor": 0, "documents": 0, "lines": 0,
                            "status": "match", "reason": None})
    assert "SIM-135" in {a.code for a in review.review_anomalies(r)}
    assert review.build_view(r)["signOff"]["canAccept"] is False


def test_mismatch_rows_do_not_count_as_compared():
    r = row_report(actualMinor=150000, differenceMinor=50000, status="mismatch")
    assert "SIM-135" in {a.code for a in review.review_anomalies(r)}


def test_large_difference_threshold_is_inclusive():
    at = _rules(row_report(actualMinor=110000, differenceMinor=10000, status="mismatch"))
    assert [a.code for a in at] == ["SIM-136"] and at[0].params["basisPoints"] == 1000
    assert at[0].params["percent"] == review.LARGE_BASIS_POINTS // 100
    assert _rules(row_report(actualMinor=109990, differenceMinor=9990, status="mismatch")) == []


def test_unknown_currency_blocks_and_shows_no_amount():
    r = row_report(currency="XYZ")
    v = review.build_view(r)
    assert v["rows"][0]["expected"] is None and v["rows"][0]["status"] == "match"
    assert "SIM-137" in {a["code"] for a in v["anomalies"]} and v["signOff"]["canAccept"] is False


# ---- acknowledgements (mutation: superset or garbage accepted) ----
def test_acknowledgement_must_be_exact():
    r = base()
    ack = review.build_view(r)["signOff"]["toAcknowledge"]
    for bad in ([*ack, "0" * 16], [*ack, 1], [*ack, ack[0]], ["zz"] * len(ack)):
        with pytest.raises(signoff.SignOffError) as e:
            decide(r, OWNER, acknowledged=bad)
        assert e.value.code == "SO-E06"


def test_identical_warnings_are_acknowledged_once():
    r = copy.deepcopy(base())
    w = {"code": "SIM-106", "severity": "warning", "messageKey": "sim.possible_duplicate", "sourceIds": ["d1"],
         "params": {}}
    r["anomalies"] += [w, copy.deepcopy(w)]
    ack = review.build_view(r)["signOff"]["toAcknowledge"]
    assert len(ack) == len(set(ack))
    assert decide(r, OWNER)[0].decision == "accepted"


# ---- gate evidence names its policy (M6) ----
def test_gate_evidence_records_required_roles_and_tenant():
    r = base()
    g = signoff.gate_evidence(r, (), required_roles=("owner", "accountant"))
    assert g["requiredRoles"] == ["owner", "accountant"] and g["tenantId"] == r["tenantId"]
    with pytest.raises(signoff.SignOffError):
        signoff.gate_evidence(r, (), required_roles=("owner", "owner"))
