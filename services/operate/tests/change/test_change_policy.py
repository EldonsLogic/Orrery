"""Review findings on PR #199: the decision is taken on the resulting diff (allow-list), not on the drafted edit;
consume is compare-and-delete; honest apply outcomes; actor passed to the port; bad clocks are coded; refusals audited.
Each probe below was applied by the first version of the service."""
import dataclasses

import pytest

from change import ChangeRefused
from change import edits as ed
from change.models import ApplyRefused
from change.service import digest_of
from helpers import (ADD_FIELD, LABEL, OWNER, SESSION, TENANT, USER, Clock, blueprint, change_decision,
                     confirm_decision, make)
from router.models import RouteDecision


def refused(code, fn, *a, **k):
    with pytest.raises(ChangeRefused) as e:
        fn(*a, **k)
    assert e.value.code == code, e.value.code
    return e.value


def _field(eid, fid):
    ent = next(e for e in blueprint()["entities"] if e["id"] == eid)
    return next(f for f in ent["fields"] if f["id"] == fid)


# the parent field replaced whole, minus `computed` and `readOnly`: no forbidden key in the drafted edit at all
VAT_NO_COMPUTED = {k: v for k, v in _field("sales_order", "vat_amount").items() if k not in ("computed", "readOnly")}

# (name, edits, expected code). Every one of these reached submit_change in the first version.
PROBES = [
    ("A2_parent_replace_drops_computed",
     [{"op": "set", "path": ["entities", "sales_order", "fields", "vat_amount"], "value": VAT_NO_COMPUTED}],
     "change_ledger_tax"),
    ("A4_transition_rewired", [{"op": "set", "path": ["workflows", "sales_order_flow", "transitions", "submit_large",
                                                      "to"], "value": "approved"}], "change_forbidden_path"),
    ("A5_ledger_workflow_unlock", [{"op": "set", "path": ["workflows", "sales_invoice_flow", "states", "submitted",
                                                          "locksEditing"], "value": False}], "change_forbidden_path"),
    ("A5_ledger_workflow_rewired", [{"op": "set", "path": ["workflows", "sales_invoice_flow", "transitions",
                                                           "cancel_invoice", "to"], "value": "draft"}],
     "change_ledger_tax"),
    ("ledger_workflow_label", [{"op": "set", "path": ["workflows", "sales_invoice_flow", "labels", "en"],
                                "value": "Bills"}], "change_ledger_tax"),
    ("plain_state_unlock", [{"op": "set", "path": ["workflows", "sales_order_flow", "states", "approved",
                                                   "locksEditing"], "value": False}], "change_forbidden_path"),
    ("A7_report_sent_by_whatsapp", [{"op": "set", "path": ["reports", "sales_overview", "schedule", "channel"],
                                     "value": "whatsapp"}], "change_forbidden_path"),
    ("A8_tax_default", [{"op": "set", "path": ["entities", "item", "fields", "vat_rate", "default"], "value": 0}],
     "change_ledger_tax"),
    ("A9_transition_kind", [{"op": "add", "path": ["workflows", "sales_order_flow", "transitions", "cancel_approved",
                                                   "kind"], "value": "advance"}], "change_forbidden_path"),
    ("A12_readonly_unlocked", [{"op": "set", "path": ["entities", "customer", "fields", "customer_code", "readOnly"],
                                "value": False}], "change_forbidden_path"),
    ("A17_workflow_detached", [{"op": "remove", "path": ["entities", "sales_order", "workflow"]}],
     "change_needs_review"),
    ("A20_computed_type_changed", [{"op": "set", "path": ["entities", "sales_order", "fields", "total_amount", "type"],
                                    "value": "string"}], "change_ledger_tax"),
    ("report_recipients", [{"op": "set", "path": ["reports", "sales_overview", "schedule", "deliverTo"],
                            "value": ["owner"]}], "change_forbidden_path"),
    ("field_default_plain", [{"op": "set", "path": ["entities", "customer", "fields", "customer_group", "default"],
                              "value": "retail"}], "change_forbidden_path"),
    ("field_required", [{"op": "add", "path": ["entities", "customer", "fields", "phone", "required"], "value": True}],
     "change_forbidden_path"),
    ("entity_numbering", [{"op": "set", "path": ["entities", "customer", "kind"], "value": "document"}],
     "change_forbidden_path"),
    ("labels_removed", [{"op": "remove", "path": ["entities", "customer", "pluralLabels"]}], "change_needs_review"),
    ("readonly_field_maxlength", [{"op": "set", "path": ["entities", "customer", "fields", "customer_code",
                                                         "maxLength"], "value": 40}], "change_forbidden_path"),
    ("stock_workflow_label", [{"op": "set", "path": ["workflows", "stock_transfer_flow", "labels", "en"],
                               "value": "Moves"}], "change_needs_review"),
    ("ledger_title_override", [{"op": "set", "path": ["i18n", "labelOverrides", "sales_invoice.title", "en"],
                                "value": "Bill"}], "change_ledger_tax"),
    ("add_money_field", [{"op": "add", "path": ["entities", "customer", "fields"],
                          "value": {"id": "credit_cap", "type": "money", "labels": {"ar": "س", "en": "Cap"}}}],
     "change_ledger_tax"),
    ("add_link_field", [{"op": "add", "path": ["entities", "customer", "fields"],
                         "value": {"id": "owner_ref", "type": "link", "target": "item",
                                   "labels": {"ar": "س", "en": "Ref"}}}], "change_forbidden_path"),
    ("add_tax_field", [{"op": "add", "path": ["entities", "customer", "fields"],
                        "value": {"id": "tax_reg", "type": "string", "labels": {"ar": "س", "en": "Tax reg"}}}],
     "change_ledger_tax"),
    ("add_required_field", [{"op": "add", "path": ["entities", "customer", "fields"],
                             "value": {"id": "nick", "type": "string", "required": True,
                                       "labels": {"ar": "س", "en": "Nick"}}}], "change_forbidden_path"),
]


@pytest.mark.parametrize("name,edits,code", PROBES, ids=[p[0] for p in PROBES])
def test_diff_level_policy_refuses(name, edits, code):
    svc, bps, *_ = make(edits)
    refused(code, svc.propose, OWNER, SESSION, "x", change_decision())
    assert bps.submitted == []


ALLOWED = [
    ("field_label", LABEL),
    ("add_optional_field", ADD_FIELD),
    ("entity_label", [{"op": "set", "path": ["entities", "customer", "labels", "en"], "value": "Client"}]),
    ("state_label", [{"op": "set", "path": ["workflows", "sales_order_flow", "states", "draft", "labels", "en"],
                      "value": "New"}]),
    ("action_label", [{"op": "set", "path": ["workflows", "sales_order_flow", "transitions", "deliver", "actionLabels",
                                             "en"], "value": "Ship"}]),
    ("report_label", [{"op": "set", "path": ["reports", "sales_overview", "labels", "en"], "value": "Sales"}]),
    ("branding_colour", [{"op": "set", "path": ["branding", "accentColour"], "value": "#1A5FB4"}]),  # #112233 is refused by the resolver (TKN-ACCENT-GREY)
    ("plain_override", [{"op": "set", "path": ["i18n", "labelOverrides", "sales_order.title", "en"],
                         "value": "Order"}]),
]


@pytest.mark.parametrize("name,edits", ALLOWED, ids=[a[0] for a in ALLOWED])
def test_low_risk_allow_list_still_applies(name, edits):
    svc, bps, _, clock, _ = make(edits)
    pv = svc.propose(OWNER, SESSION, "x", change_decision())
    svc.confirm(OWNER, SESSION, confirm_decision("yes", pv, clock))
    assert len(bps.submitted) == 1


def test_whole_section_set_is_refused_at_edit_level():
    for path in (["entities"], ["entities", "customer"], ["workflows", "sales_order_flow"], ["reports"]):
        with pytest.raises(ChangeRefused) as e:
            ed.check_allowed((ed.Edit("set", tuple(path), {}),))
        assert e.value.code == "change_forbidden_path"


@pytest.mark.parametrize("key", ["provenance", "permissions", "computed", "guards", "readOnly", "locksEditing"])
def test_forbidden_keys_at_edit_level(key):
    with pytest.raises(ChangeRefused):
        ed.check_allowed((ed.Edit("set", ("entities", "customer", key, "x"), "v"),))
    with pytest.raises(ChangeRefused):
        ed.check_allowed((ed.Edit("add", ("entities", "customer", "fields"), {"id": "z", key: 1}),))


# ---- M1: compare-and-delete consume ------------------------------------------------------------------------------
def test_superseded_proposal_cannot_be_applied_by_a_racing_confirm():
    svc, bps, drafter, clock, _ = make()
    pv1 = svc.propose(OWNER, SESSION, "x", change_decision())
    p1 = svc.store.active(TENANT, USER, SESSION)
    drafter.out = [{"op": "set", "path": ["entities", "customer", "fields", "phone", "labels", "en"], "value": "Other"}]
    svc.propose(OWNER, SESSION, "y", change_decision())  # P2 supersedes P1 while a confirm of P1 is in flight
    assert svc.store.consume(p1) is False
    assert svc.store.active(TENANT, USER, SESSION).digest != pv1.digest  # P2 stays active
    assert bps.submitted == []


def test_consume_is_once_and_deletes():
    svc, *_ = make()
    svc.propose(OWNER, SESSION, "x", change_decision())
    p = svc.store.active(TENANT, USER, SESSION)
    assert svc.store.consume(p) is True and svc.store.consume(p) is False
    assert svc.store.active(TENANT, USER, SESSION) is None and svc.store.used(p.digest)


# ---- M2: honest outcome after submit_change ----------------------------------------------------------------------
def test_definite_refusal_says_nothing_changed():
    svc, bps, _, clock, audit = make(fail=ApplyRefused())
    pv = svc.propose(OWNER, SESSION, "x", change_decision())
    e = refused("change_apply_failed", svc.confirm, OWNER, SESSION, confirm_decision("yes", pv, clock))
    assert "Nothing was changed" in e.text("en")


def test_unknown_outcome_never_claims_nothing_changed():
    svc, bps, _, clock, audit = make(fail=TimeoutError("late"))
    pv = svc.propose(OWNER, SESSION, "x", change_decision())
    e = refused("change_outcome_unknown", svc.confirm, OWNER, SESSION, confirm_decision("yes", pv, clock))
    assert "Nothing was changed" not in e.text("en") and "لم يتم تغيير" not in e.text("ar")
    assert [a["kind"] for a in audit][-2:] == ["change.outcome_unknown", "change.refused"]


def test_unknown_outcome_is_resolved_by_idempotency_key_lookup():
    svc, bps, _, clock, _ = make(fail=TimeoutError("late"))
    bps.status = "applied"
    pv = svc.propose(OWNER, SESSION, "x", change_decision())
    assert svc.confirm(OWNER, SESSION, confirm_decision("yes", pv, clock)).status == "applied"
    assert bps.status_queries == [(TENANT, pv.digest)]
    svc, bps, _, clock, _ = make(fail=TimeoutError("late"))
    bps.status = "not_applied"
    pv = svc.propose(OWNER, SESSION, "x", change_decision())
    refused("change_apply_failed", svc.confirm, OWNER, SESSION, confirm_decision("yes", pv, clock))


# ---- M3: actor and risk reach the port; idempotency key and base are the proposal's -----------------------------
def test_port_receives_actor_risk_key_and_base():
    svc, bps, _, clock, _ = make()
    pv = svc.propose(OWNER, SESSION, "x", change_decision())
    svc.confirm(OWNER, SESSION, confirm_decision("yes", pv, clock))
    call = bps.calls[0]
    assert call["idempotency_key"] == pv.digest and call["proposal_digest"] == pv.digest
    assert call["actor"] == {"tenant": TENANT, "subject": USER, "roles": ["owner"], "session": SESSION}
    assert call["risk"] == pv.risk
    from change._deps import blueprint_hash
    assert call["diff"]["base"]["hash"] == blueprint_hash(blueprint())


# ---- M6: bad clocks and ttl --------------------------------------------------------------------------------------
@pytest.mark.parametrize("t", [float("nan"), None, float("inf"), True, "1000"])
def test_bad_clock_in_propose_is_coded(t):
    svc, bps, *_ = make(clock=Clock(t))
    refused("change_unavailable", svc.propose, OWNER, SESSION, "x", change_decision())


@pytest.mark.parametrize("t", [float("nan"), None, True])
def test_bad_clock_in_confirm_is_coded(t):
    svc, bps, _, clock, _ = make()
    pv = svc.propose(OWNER, SESSION, "x", change_decision())
    dec = confirm_decision("yes", pv, clock)
    clock.t = t
    refused("change_unavailable", svc.confirm, OWNER, SESSION, dec)
    assert bps.submitted == []


@pytest.mark.parametrize("ttl", [0, -5, float("inf"), float("nan")])
def test_bad_ttl_refused(ttl):
    with pytest.raises(ChangeRefused) as e:
        make(ttl_s=ttl)
    assert e.value.code == "change_unavailable"


# ---- M7: confirm refusals are audited ----------------------------------------------------------------------------
def test_confirm_refusals_are_audited():
    svc, bps, _, clock, audit = make()
    pv = svc.propose(OWNER, SESSION, "x", change_decision())
    dec = confirm_decision("yes", pv, clock)
    forged = dataclasses.replace(dec, confirms_args_hash="sha256:" + "0" * 64)
    refused("change_confirmation_mismatch", svc.confirm, OWNER, SESSION, forged)
    svc.confirm(OWNER, SESSION, dec)
    refused("change_replayed", svc.confirm, OWNER, SESSION, dec)
    refusals = [a for a in audit if a["kind"] == "change.refused"]
    assert [a["code"] for a in refusals] == ["change_confirmation_mismatch", "change_replayed"]
    assert refusals[1]["digest"] == pv.digest[:23] and "Mobile" not in str(audit)


# ---- mutations the first tests did not catch ---------------------------------------------------------------------
def test_digest_changes_with_every_bound_field():
    base = dict(tenant_id="t", user_id="u", session_id="s", base_hash="b", target_hash="g", diff_hash="d", risk="R2",
                expires_at=1.0)
    seen = {digest_of(**base)}
    for k, v in (("tenant_id", "t2"), ("user_id", "u2"), ("session_id", "s2"), ("base_hash", "b2"),
                 ("target_hash", "g2"), ("diff_hash", "d2"), ("risk", "R1"), ("expires_at", 2.0)):
        seen.add(digest_of(**dict(base, **{k: v})))
    assert len(seen) == 9


def test_expiry_boundary_is_exclusive():
    svc, bps, _, clock, _ = make()
    pv = svc.propose(OWNER, SESSION, "x", change_decision())
    dec = confirm_decision("yes", pv, clock)
    clock.t = pv.expires_at
    refused("change_expired", svc.confirm, OWNER, SESSION, dec)
    assert bps.submitted == []


def test_lowered_stored_risk_is_refused_on_confirm():
    svc, bps, _, clock, _ = make(ADD_FIELD)
    svc.propose(OWNER, SESSION, "x", change_decision())
    p = svc.store.active(TENANT, USER, SESSION)
    d = digest_of(p.tenant_id, p.user_id, p.session_id, p.base_hash, p.target_hash, p.diff_hash, "R1", p.expires_at)
    low = dataclasses.replace(p, risk="R1", digest=d)  # self-consistent digest, but risk below the derived R2
    svc.store.put(low)
    refused("change_tampered", svc.confirm, OWNER, SESSION, confirm_decision("yes", low, clock))
    assert bps.submitted == []


def test_live_base_revalidated_on_confirm(monkeypatch):
    import change.service as service
    from change._deps import blueprint_hash
    svc, bps, _, clock, _ = make()
    pv = svc.propose(OWNER, SESSION, "x", change_decision())
    base = blueprint_hash(blueprint())
    real = service.validate

    def picky(bp, ctx):
        r = real(bp, ctx)
        return type("Bad", (), {"ok": False})() if blueprint_hash(bp) == base else r
    monkeypatch.setattr(service, "validate", picky)
    refused("change_base_invalid", svc.confirm, OWNER, SESSION, confirm_decision("yes", pv, clock))
    assert bps.submitted == []


def test_confirm_requires_change_mode_even_with_the_right_ids():
    svc, bps, _, clock, _ = make()
    pv = svc.propose(OWNER, SESSION, "x", change_decision())
    act = RouteDecision("act", "high", ("confirmation_of_pending",), confirms_action_id=pv.action_id,
                        confirms_args_hash=pv.digest)
    refused("change_confirmation_mismatch", svc.confirm, OWNER, SESSION, act)
    assert bps.submitted == []
