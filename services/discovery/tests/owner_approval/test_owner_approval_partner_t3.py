"""PR #224 partner Tier 3 review (sayegh9, at 3606e00): F1 manifest TOCTOU, F2 company name, F3 spent approval,
and the lows (reject past draft follows the gate's step-up; no reject while an apply is pending or in recovery)."""
import json
from pathlib import Path

import pytest

from owner_approval import OwnerApprovalError, labels
from owner_approval.ledger import MemoryStore, SealedLog
from owner_approval.sections import summary_section
from support import BP, KEYS, T, Claims, approve, build, cdigest, seen

ROOT = Path(__file__).resolve().parents[4]


def code(fn, *a, **k):
    with pytest.raises(OwnerApprovalError) as e:
        fn(*a, **k)
    return e.value.code


def args(svc, claims, decision="reject", reason="not_for_us"):
    sb, sq = seen(svc, claims)
    return dict(tenant_id=T, blueprint_id=BP, decision=decision, reason=reason, note="", seen_blueprint_digest=sb, seen_quote_digest=sq)


# ---- F1 (High): one manifest read per append, so the store's CAS on n protects exactly what is written ------------
class RacingStore(MemoryStore):
    """Commits a competing stream (bp-2) through another log at the start of the k-th manifest read after arming."""
    def __init__(self):
        super().__init__()
        self.arm, self.other = None, None

    def manifest(self, tenant):
        if self.arm is not None:
            self.arm -= 1
            if self.arm == 0:
                self.arm = None
                self.other.append(T, "bp-2", {"x": 1})
        return super().manifest(tenant)


@pytest.mark.parametrize("k", [1, 2, 3, 4])
def test_f1_competing_stream_commit_between_manifest_reads_is_never_dropped(k):
    store = RacingStore()
    log, other = SealedLog(dict(KEYS), "k1", store=store), SealedLog(dict(KEYS), "k1", store=store)
    store.other = other
    log.append(T, "bp-0", {"x": 0})          # the tenant already has a manifest
    store.arm = k
    try:
        log.append(T, "bp-1", {"x": 1})
        wrote = True
    except OwnerApprovalError as e:          # a lost race is refused (CAS), never written on a stale manifest
        assert e.code == "OA-004"
        wrote = False
    assert len(other.read(T, "bp-2")) == 1   # bp-2 kept, no OA-009 unanchored
    assert len(log.read(T, "bp-0")) == 1
    assert len(log.read(T, "bp-1")) == (1 if wrote else 0)
    log.append(T, "bp-1", {"x": 2})          # and the tenant stays writable
    other.append(T, "bp-2", {"x": 2})


# ---- F2 (Medium): the company name comes from legalName / tradeName (the schema has no company.labels) ------------
def test_f2_summary_shows_company_legal_and_trade_name_on_the_contract_example():
    content = json.loads((ROOT / "contracts/examples/blueprint-trading-minimal.json").read_text(encoding="utf-8"))
    comp = summary_section(content)["company"]
    assert comp["legalName"] == {"ar": "شركة المثال للتجارة", "en": "Example Trading Co.", "cut": False}
    assert comp["tradeName"] == {"ar": "المثال", "en": "Example", "cut": False}
    assert comp["country"] == "SA" and "labels" not in comp
    en, ar = labels("en"), labels("ar")
    for k in (comp["legalNameKey"], comp["tradeNameKey"]):
        assert en[k] and ar[k]


def test_f2_missing_trade_name_is_none_and_a_cut_name_blocks_approval():
    content = {"company": {"legalName": {"ar": "ش", "en": "A"}, "country": "SA"}}
    comp = summary_section(content)["company"]
    assert comp["tradeName"] is None and comp["legalName"]["en"] == "A"
    long = {"company": {"legalName": {"ar": "ش" * 201, "en": "A"}, "country": "SA"}}
    assert summary_section(long)["moreItems"] >= 1     # a name cut short is never shown as complete


# ---- F3 (Medium): a second owner cannot re-approve a version a rollback spent ------------------------------------
def spent(svc, w):
    approve(svc, Claims("owner-1"))
    svc._gate.roll_back(Claims(), tenant_id=T, blueprint_id=BP, to_state="draft", reason="owner_reopened")
    assert w.machine == "draft"


def test_f3_review_does_not_offer_approve_on_a_spent_version_to_another_owner():
    svc, w, _ = build()
    spent(svc, w)
    v = svc.review(Claims("owner-2"), tenant_id=T, blueprint_id=BP)
    assert v["state"]["value"] == "approval_spent"
    allowed = {d["key"]: d["allowed"] for d in v["decisions"]}
    assert allowed["approve"] is False and allowed["reject"] is True
    assert "approval_spent" in [b["key"] for b in v["blockers"]]


def test_f3_decide_refuses_a_second_owners_approval_of_a_spent_version():
    svc, w, _ = build()
    spent(svc, w)
    calls = list(w.calls)
    assert code(approve, svc, Claims("owner-2")) == "OA-018"
    assert w.machine == "draft" and w.calls == calls and svc.status(T, BP)["state"] == "approval_spent"
    assert svc.verify(T, BP, cdigest(w.bp), w.quote["digest"], "owner-2")["approvedBy"] is None


def test_f3_a_new_version_can_be_approved_again():
    svc, w, _ = build()
    spent(svc, w)
    w.revise()
    assert approve(svc, Claims("owner-2"))["state"] == "approved"


def test_f3_a_stored_approval_of_a_spent_version_fails_the_read():
    svc, w, _ = build()
    spent(svc, w)
    sb, sq = seen(svc)
    d = {"decision": "approve", "reason": "agree", "note": "", "bpDigest": sb, "quoteDigest": sq,
         "gapDigest": w.quote["inputs"]["gap_report_digest"], "forward": "gate", "rollbacks": w.rollbacks}
    svc._log.append(T, BP, {"type": "decision", "at": w.t, "actor": {"subject": "owner-2", "role": "owner", "kind": "human",
                                                                      "realm": "tenant"}, "data": d})
    assert code(svc.status, T, BP) == "OA-009"


def test_f3_error_and_blocker_have_labels():
    en, ar = labels("en"), labels("ar")
    for k in ("oa.error.OA-018", "oa.blocker.approval_spent"):
        assert en[k] and ar[k]


# ---- Lows: reject past draft follows the gate's step-up; no reject while an apply is pending or in recovery ---------
def test_low_reject_past_draft_without_step_up_does_not_count_and_may_be_made_again():
    svc, w, _ = build()
    approve(svc, Claims("owner-1"))
    w.machine = "team_reviewed"
    weak = Claims("owner-2", step_up=False)
    assert code(svc.decide, weak, **args(svc, Claims("owner-2"))) == "OA-015"   # the gate's step-up refused the rollback
    assert w.machine == "team_reviewed"
    st = svc.status(T, BP)
    assert st["state"] == "approved"                                            # the sealed but refused reject counts for nothing
    assert svc.verify(T, BP, cdigest(w.bp), w.quote["digest"], "owner-1")["blocked"] is False
    out = svc.decide(Claims("owner-2"), **args(svc, Claims("owner-2")))           # same owner, with a step-up now
    assert out["state"] == "rejected" and w.machine == "draft"


@pytest.mark.parametrize("field", ["pending", "recovery"])
@pytest.mark.parametrize("decision,reason", [("reject", "not_for_us"), ("request_changes", "unclear")])
def test_low_no_reject_or_change_request_while_an_apply_is_pending_or_in_recovery(field, decision, reason):
    svc, w, _ = build()
    approve(svc, Claims("owner-1"))
    w.machine = "built_in_sandbox"
    setattr(w, field, {"kind": "sandbox", "status": "unknown"} if field == "pending" else {"kind": "live", "needsRecovery": True})
    before = len(svc._log._logs[(T, BP)])
    assert code(svc.decide, Claims("owner-2"), **args(svc, Claims("owner-2"), decision, reason)) == "OA-005"
    assert len(svc._log._logs[(T, BP)]) == before                               # nothing sealed: resolve_apply is not blocked
    assert svc.verify(T, BP, cdigest(w.bp), w.quote["digest"], "owner-1")["blocked"] is False
    v = svc.review(Claims("owner-2"), tenant_id=T, blueprint_id=BP)
    assert not any(d["allowed"] for d in v["decisions"]) and "apply_pending" in [b["key"] for b in v["blockers"]]


def test_low_gate_status_without_pending_or_recovery_fails_closed():
    svc, w, _ = build()
    real = svc._gate.status
    for k in ("pending", "recovery"):
        svc._gate.status = lambda t, bp, k=k: {x: v for x, v in real(t, bp).items() if x != k}
        assert code(svc.status, T, BP) == "OA-004"
    svc._gate.status = lambda t, bp: {**real(t, bp), "pending": "yes"}
    assert code(svc.status, T, BP) == "OA-004"
