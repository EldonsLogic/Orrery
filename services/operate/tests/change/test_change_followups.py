"""Follow-ups to the PR #199 re-review: superseded is not replayed, tax ids without separators, maxLength."""
import pytest

from change import ChangeRefused
from helpers import OWNER, SESSION, change_decision, confirm_decision, make


def refused(code, fn, *a, **k):
    with pytest.raises(ChangeRefused) as e:
        fn(*a, **k)
    assert e.value.code == code


def test_old_confirmation_after_a_newer_proposal_is_a_mismatch():
    svc, bps, _, clock, _ = make()
    pv1 = svc.propose(OWNER, SESSION, "x", change_decision())
    dec1 = confirm_decision("yes", pv1, clock)
    clock.t += 1  # a different expiry gives a different digest for the identical edit
    svc.propose(OWNER, SESSION, "y", change_decision())  # supersedes pv1
    refused("change_confirmation_mismatch", svc.confirm, OWNER, SESSION, dec1)
    assert bps.submitted == []


def test_superseded_mid_confirm_is_not_replayed():
    svc, bps, _, clock, _ = make()
    pv1 = svc.propose(OWNER, SESSION, "x", change_decision())
    dec1 = confirm_decision("yes", pv1, clock)
    real = svc.store.consume

    def racing(p):  # a newer proposal lands between the checks and the compare-and-delete
        clock.t += 1
        svc.propose(OWNER, SESSION, "y", change_decision())
        return real(p)
    svc.store.consume = racing
    refused("change_superseded", svc.confirm, OWNER, SESSION, dec1)
    assert bps.submitted == []


def test_really_used_proposal_is_still_replayed():
    svc, bps, _, clock, _ = make()
    pv = svc.propose(OWNER, SESSION, "x", change_decision())
    dec = confirm_decision("yes", pv, clock)
    svc.confirm(OWNER, SESSION, dec)
    refused("change_replayed", svc.confirm, OWNER, SESSION, dec)


def _add(fid):
    return [{"op": "add", "path": ["entities", "customer", "fields"],
             "value": {"id": fid, "type": "boolean", "labels": {"ar": "علم", "en": "Flag"}}}]


@pytest.mark.parametrize("fid", ["vatrate", "zatca_flag", "zatcaflag", "vatexempt", "withholdingpct", "ratevat",
                                 "vat_rate"])
def test_tax_like_field_ids_are_refused_even_without_separators(fid):
    svc, *_ = make(_add(fid))
    refused("change_ledger_tax", svc.propose, OWNER, SESSION, "add a field", change_decision())


def test_plain_field_id_is_still_allowed():
    svc, *_ = make(_add("whatsapp"))
    assert svc.propose(OWNER, SESSION, "add a field", change_decision()).risk == "R2"


def _maxlen(v):
    return [{"op": "set", "path": ["entities", "customer", "fields", "customer_name", "maxLength"], "value": v}]


def test_lowering_max_length_needs_review():
    cur = {"maxLength": 140}  # customer.customer_name in the fixture
    svc, *_ = make(_maxlen(1))
    refused("change_needs_review", svc.propose, OWNER, SESSION, "shorten", change_decision())
    svc, *_ = make(_maxlen(cur["maxLength"] + 10))
    assert svc.propose(OWNER, SESSION, "lengthen", change_decision()).risk == "R2"


# ---- PR #205 review: L1, L2 -----------------------------------------------------------------------------------
@pytest.mark.parametrize("fid", ["salesvatrate", "netvatamt", "itemzatcacode"])
def test_tax_token_inside_a_joined_id_is_refused(fid):
    svc, *_ = make(_add(fid))
    refused("change_ledger_tax", svc.propose, OWNER, SESSION, "add a field", change_decision())


def test_maxlength_added_to_an_unbounded_field_needs_review():
    op = [{"op": "add", "path": ["entities", "customer", "fields", "phone", "maxLength"], "value": 5}]
    svc, *_ = make(op)
    refused("change_needs_review", svc.propose, OWNER, SESSION, "bound it", change_decision())


def test_more_ops_than_the_preview_cap_needs_review():
    two = [{"op": "set", "path": ["entities", "customer", "fields", "phone", "labels", "en"], "value": "A"},
           {"op": "set", "path": ["entities", "customer", "fields", "city", "labels", "en"], "value": "B"}]
    svc, *_ = make(two, max_ops=1)
    refused("change_needs_review", svc.propose, OWNER, SESSION, "x", change_decision())
