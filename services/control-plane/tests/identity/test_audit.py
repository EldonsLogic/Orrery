import pytest

from identity import IdentityError


def test_every_decision_is_audited(w):
    tok = w.login("p-owner")
    w.idn.verify_customer_token(tok.access_token, "t-a")
    with pytest.raises(IdentityError):
        w.idn.verify_customer_token(tok.access_token, "t-b")
    with pytest.raises(IdentityError):
        w.login("p-owner", mfa=False)
    ev = w.audit.events()
    assert [(e.action, e.decision, e.code) for e in ev] == [
        ("token.issue", "allow", "OK"), ("token.verify", "allow", "OK"),
        ("token.verify", "deny", "IDN-007"), ("token.issue", "deny", "IDN-013")]
    assert [e.seq for e in ev] == [1, 2, 3, 4]


def test_audit_is_append_only_and_secret_free(w):
    pair = w.login("p-owner")
    ev = w.audit.events()
    assert isinstance(ev, tuple)
    with pytest.raises(AttributeError):
        ev[0].decision = "allow"  # frozen
    assert not hasattr(w.audit, "delete") and not hasattr(w.audit, "clear")
    text = repr(ev)
    assert pair.access_token not in text and pair.refresh_token not in text
    with pytest.raises(ValueError):
        w.audit.record(at=1, action="x", decision="maybe", code="OK", realm="customer",
                       subject=None, tenant=None)


def test_error_messages_carry_no_secrets(w):
    pair = w.login("p-owner")
    with pytest.raises(IdentityError) as exc:
        w.idn.verify_customer_token(pair.access_token + "x", "t-a")
    assert pair.access_token not in str(exc.value)
    assert str(exc.value).startswith("IDN-")
