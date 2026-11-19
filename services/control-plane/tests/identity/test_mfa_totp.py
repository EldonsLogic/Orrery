import secrets

import pytest

from identity.mfa import recovery, totp

KEY = ("1234567890" * 2).encode()  # RFC 6238 appendix B SHA1 test key


@pytest.mark.parametrize("t,expected", [(59, "94287082"), (1111111109, "07081804"),
                                        (1111111111, "14050471"), (1234567890, "89005924"),
                                        (2000000000, "69279037")])
def test_rfc6238_vectors(t, expected):
    assert totp.hotp(KEY, totp.counter_at(t), 8) == expected


def test_rfc4226_vector():
    assert totp.hotp(KEY, 0) == "755224" and totp.hotp(KEY, 9) == "520489"


def test_drift_window_is_one_step():
    now = 1_900_000_000
    c = totp.counter_at(now)
    for off in (-1, 0, 1):
        assert totp.verify(KEY, totp.hotp(KEY, c + off), now, -1) == c + off
    for off in (-2, 2):
        assert totp.verify(KEY, totp.hotp(KEY, c + off), now, -1) is None


def test_replay_and_older_counters_refused():
    now = 1_900_000_000
    c = totp.counter_at(now)
    assert totp.verify(KEY, totp.hotp(KEY, c), now, c) is None
    assert totp.verify(KEY, totp.hotp(KEY, c - 1), now, c) is None
    assert totp.verify(KEY, totp.hotp(KEY, c + 1), now, c) == c + 1


@pytest.mark.parametrize("bad", ["", "12345", "1234567", "12345a", "١٢٣٤٥٦", " 123456", None,
                                 123456, b"123456"])
def test_malformed_codes_refused(bad):
    assert totp.verify(KEY, bad, 1_900_000_000, -1) is None


def test_uri_has_issuer_and_params():
    uri = totp.provisioning_uri(KEY, "a b@example.test", "Plat form")
    assert uri.startswith("otpauth://totp/Plat%20form:a%20b%40example.test?secret=")
    assert "digits=6" in uri and "period=30" in uri


def test_recovery_code_shape_and_normalise():
    c = recovery.new_code(secrets.token_bytes)
    assert len(c) == 11 and c[5] == "-"
    assert recovery.normalise(c.lower().replace("-", " ")) == c.replace("-", "")
    for bad in (None, "", "short", "0" * 10, c + "X", 5):
        assert recovery.normalise(bad) is None


def test_recovery_hash_depends_on_salt():
    assert (recovery.hash_code("ABCDEFGHJK", b"a" * 16, 10)
            != recovery.hash_code("ABCDEFGHJK", b"b" * 16, 10))
