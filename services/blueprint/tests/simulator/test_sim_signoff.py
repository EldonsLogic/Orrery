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
OWNER = {"userId": "u-owner", "roles": ["owner"], "kind": "human"}
ACCT = {"userId": "u-acct", "roles": ["accountant"], "kind": "human"}


def base():
    return h.run()[0]


def decide(report, actor, decision="accepted", records=(), role=None, note="checked with accountant", **kw):
    view = review.build_view(report, records=records)
    ack = kw.pop("acknowledged", view["signOff"]["toAcknowledge"])
    return signoff.record_decision(report, records, actor=actor, role=role or actor["roles"][0], decision=decision,
                                   decided_at=kw.pop("decided_at", T0), note=note, acknowledged=ack, **kw)


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
    assert len(recs) == 1 and recs[0].user_id == "u-owner" and recs[0].decided_at == "2026-11-19T10:00:00Z"
    assert recs[0].report_digest == review.report_digest(r)
    v = review.build_view(r, records=recs)
    assert v["signOff"]["state"] == "accepted"
    assert v["signOff"]["records"][0]["userId"] == "u-owner"


def test_no_default_decision_and_no_auto_accept():
    import inspect
    sig = inspect.signature(signoff.record_decision)
    for name in ("decision", "decided_at", "actor", "acknowledged"):
        assert sig.parameters[name].default is inspect.Parameter.empty
    assert review.build_view(base())["signOff"]["state"] != "accepted"


def test_agents_and_wrong_roles_cannot_sign():
    r = base()
    with pytest.raises(signoff.SignOffError) as e:
        decide(r, {"userId": "bot", "roles": ["owner"], "kind": "agent"}, role="owner")
    assert e.value.code == "SO-E02"
    with pytest.raises(signoff.SignOffError) as e:
        decide(r, {"userId": "u2", "roles": ["clerk"], "kind": "human"}, role="owner")
    assert e.value.code == "SO-E03"
    with pytest.raises(signoff.SignOffError):
        decide(r, {"userId": "", "roles": ["owner"], "kind": "human"})
    with pytest.raises(signoff.SignOffError):
        decide(r, {"userId": "u‮1", "roles": ["owner"], "kind": "human"})


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
    both = {"userId": "u1", "roles": ["owner", "accountant"], "kind": "human"}
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
                                       "decidedAt": "2026-11-19T10:00:00Z", "note": "checked with accountant"}
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
