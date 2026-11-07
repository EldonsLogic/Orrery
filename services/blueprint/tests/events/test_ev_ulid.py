import re

from evstream import UlidGenerator, is_valid_ulid, new_ulid
from evstream.ulid import ulid_time_ms


def test_format():
    u = new_ulid()
    assert len(u) == 26 and re.fullmatch(r"[0-7][0-9A-HJKMNP-TV-Z]{25}", u)
    assert is_valid_ulid(u)


def test_invalid_values():
    for bad in ["", "x" * 26, "8" + "0" * 25, "0" * 25, "0" * 27, "0000000000000000000000000I",
                "0000000000000000000000000l", None, 5, "0" * 25 + "\n", ("0" * 26).lower() + "a"]:
        assert not is_valid_ulid(bad)


def test_monotonic_in_same_millisecond():
    g = UlidGenerator(clock_ms=lambda: 1_700_000_000_000)
    ids = [g.generate() for _ in range(2000)]
    assert ids == sorted(ids) and len(set(ids)) == 2000
    assert {ulid_time_ms(i) for i in ids} == {1_700_000_000_000}


def test_monotonic_when_clock_steps_back():
    times = iter([1000, 999, 998, 1001])
    g = UlidGenerator(clock_ms=lambda: next(times))
    ids = [g.generate() for _ in range(4)]
    assert ids == sorted(ids) and len(set(ids)) == 4


def test_random_overflow_moves_to_next_millisecond():
    g = UlidGenerator(clock_ms=lambda: 5, randbytes=lambda n: b"\xff" * n)
    a, b = g.generate(), g.generate()
    assert a < b and ulid_time_ms(b) == 6


def test_time_roundtrip_and_global_order():
    assert ulid_time_ms(UlidGenerator(clock_ms=lambda: 123456789).generate()) == 123456789
    a = UlidGenerator(clock_ms=lambda: 10).generate()
    b = UlidGenerator(clock_ms=lambda: 11).generate()
    assert a < b
