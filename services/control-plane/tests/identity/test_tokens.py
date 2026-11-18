import base64
import hashlib
import hmac
import json

import pytest

from identity import IdentityError, Realm, RealmConfig, TestOnlyHmacSha256Signer
from identity.tokens import decode, encode


def b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def parts(token):
    h, p, s = token.split(".")
    pad = lambda x: x + "=" * (-len(x) % 4)  # noqa: E731
    return (json.loads(base64.urlsafe_b64decode(pad(h))),
            json.loads(base64.urlsafe_b64decode(pad(p))), s)


def forge(header, payload, key=b"c" * 32):
    """Build a correctly signed token with arbitrary contents (attacker who has a key)."""
    dump = lambda o: json.dumps(o, sort_keys=True, separators=(",", ":")).encode()  # noqa: E731
    si = b64(dump(header)) + "." + b64(dump(payload))
    return si + "." + b64(hmac.new(key, si.encode(), hashlib.sha256).digest())


def code(fn):
    with pytest.raises(IdentityError) as exc:
        fn()
    return exc.value.code


def test_happy_path_claims(w):
    pair = w.login("p-owner")
    c = w.idn.verify_customer_token(pair.access_token, "t-a")
    assert (c.subject, c.tenant, c.realm, c.mfa_satisfied) == ("p-owner", "t-a",
                                                              Realm.CUSTOMER, True)
    assert c.audience == "platform-app/tenant/t-a" and c.issuer == "https://id.example.test"
    assert 300 <= c.expires_at - c.issued_at <= 900
    _, payload, _ = parts(pair.access_token)
    assert "roles" not in payload and "permissions" not in payload


def test_cross_tenant_token_rejected(w):
    tok = w.login("p-acct", "t-a").access_token
    assert code(lambda: w.idn.verify_customer_token(tok, "t-b")) == "IDN-007"


def test_cross_tenant_even_with_forged_audience(w):
    h, p, _ = parts(w.login("p-acct", "t-a").access_token)
    p["aud"] = "platform-app/tenant/t-b"
    assert code(lambda: w.idn.verify_customer_token(forge(h, p), "t-b")) == "IDN-007"


def test_staff_token_not_accepted_as_customer(w):
    tok = w.idn.issue_staff_token("s-1", mfa_satisfied=True, auth_time=w.clock()).access_token
    assert code(lambda: w.idn.verify_customer_token(tok, "t-a")) == "IDN-002"  # other key id


def test_cross_realm_rejected_even_with_shared_key(w):
    shared = TestOnlyHmacSha256Signer(b"k" * 32, "same")
    cust = RealmConfig(Realm.CUSTOMER, "iss-c", "aud-c", shared)
    staff = RealmConfig(Realm.STAFF, "iss-s", "aud-s", shared)
    s_tok, _ = encode(staff, subject="s-1", tenant=None, session_version=1,
                      mfa_satisfied=True, auth_time=w.clock(), now=w.clock())
    c_tok, _ = encode(cust, subject="p", tenant="t-a", session_version=1,
                      mfa_satisfied=True, auth_time=w.clock(), now=w.clock())
    assert code(lambda: decode(s_tok, cust, now=w.clock(), tenant="t-a")) == "IDN-006"
    assert code(lambda: decode(c_tok, staff, now=w.clock(), tenant=None)) == "IDN-006"


def test_customer_token_not_accepted_as_staff(w):
    tok = w.login("p-owner").access_token
    assert code(lambda: w.idn.verify_staff_token(tok)) == "IDN-002"


def test_unknown_realm_rejected(w):
    h, p, _ = parts(w.login("p-owner").access_token)
    p["realm"] = "partner"
    assert code(lambda: w.idn.verify_customer_token(forge(h, p), "t-a")) == "IDN-050"


def test_expired_and_not_before(w):
    tok = w.login("p-owner").access_token
    w.clock.advance(600)
    assert code(lambda: w.idn.verify_customer_token(tok, "t-a")) == "IDN-004"
    h, p, _ = parts(w.login("p-owner").access_token)
    p["nbf"] = p["iat"] = w.clock() + 60
    p["exp"] = w.clock() + 600
    assert code(lambda: w.idn.verify_customer_token(forge(h, p), "t-a")) == "IDN-005"


def test_tampered_signature_and_payload(w):
    tok = w.login("p-clerk", mfa=False).access_token
    h, p, s = tok.split(".")
    bad_sig = s[:-2] + ("AA" if s[-2:] != "AA" else "BA")
    assert code(lambda: w.idn.verify_customer_token(f"{h}.{p}.{bad_sig}", "t-a")) in (
        "IDN-001", "IDN-003")
    hd, pl, _ = parts(tok)
    pl["sub"] = "p-owner"
    swapped = tok.split(".")[0] + "." + forge(hd, pl).split(".")[1] + "." + s
    assert code(lambda: w.idn.verify_customer_token(swapped, "t-a")) == "IDN-003"
    assert code(lambda: w.idn.verify_customer_token(f"{h}.{p}.", "t-a")) == "IDN-003"


def test_wrong_key_rejected(w):
    h, p, _ = parts(w.login("p-owner").access_token)
    assert code(lambda: w.idn.verify_customer_token(forge(h, p, key=b"x" * 32),
                                                    "t-a")) == "IDN-003"


@pytest.mark.parametrize("alg", ["none", "None", "", "RS256", "HS512", "hs256"])
def test_alg_confusion_rejected(w, alg):
    h, p, _ = parts(w.login("p-owner").access_token)
    h["alg"] = alg
    tok = forge(h, p)
    assert code(lambda: w.idn.verify_customer_token(tok, "t-a")) == "IDN-002"
    unsigned = tok.rsplit(".", 1)[0] + "."
    assert code(lambda: w.idn.verify_customer_token(unsigned, "t-a")) == "IDN-002"


def test_header_extras_rejected(w):
    h, p, _ = parts(w.login("p-owner").access_token)
    h["jku"] = "https://evil.example.test/keys"
    assert code(lambda: w.idn.verify_customer_token(forge(h, p), "t-a")) == "IDN-002"


def test_extra_or_missing_claims_rejected(w):
    h, p, _ = parts(w.login("p-clerk", mfa=False).access_token)
    with_roles = dict(p, roles=["owner"])
    assert code(lambda: w.idn.verify_customer_token(forge(h, with_roles), "t-a")) == "IDN-008"
    missing = {k: v for k, v in p.items() if k != "sv"}
    assert code(lambda: w.idn.verify_customer_token(forge(h, missing), "t-a")) == "IDN-008"
    wrong_type = dict(p, mfa=1)
    assert code(lambda: w.idn.verify_customer_token(forge(h, wrong_type), "t-a")) == "IDN-008"


@pytest.mark.parametrize("tok", [None, "", "a.b", "a.b.c.d", "!!.@@.##", "x" * 5000,
                                 "e30.e30.AA="])
def test_malformed_rejected(w, tok):
    assert code(lambda: w.idn.verify_customer_token(tok, "t-a")) in ("IDN-001", "IDN-002")


def test_signer_and_config_validation():
    assert code(lambda: TestOnlyHmacSha256Signer(b"short", "k")) == "IDN-051"
    good = TestOnlyHmacSha256Signer(b"k" * 32, "k")
    assert "k" * 32 not in repr(good)
    assert code(lambda: RealmConfig(Realm.CUSTOMER, "i", "a", good, access_ttl=3600)) == "IDN-051"

    class NoneSigner:
        alg, key_id = "none", "k"
    assert code(lambda: RealmConfig(Realm.CUSTOMER, "i", "a", NoneSigner())) == "IDN-051"


def test_realms_must_differ(w):
    from identity import IdentityService
    assert code(lambda: IdentityService(repo=w.repo, customer=w.customer_cfg,
                                        staff=w.customer_cfg, roles=w.resolver,
                                        audit=w.audit, clock=w.clock)) == "IDN-051"
