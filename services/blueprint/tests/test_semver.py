import pytest

from validator import semver

TABLE = [
    ("1.2.3", "1.2.3", True), ("1.2.4", "1.2.3", False), ("1.2.3", "=1.2.3", True),
    ("1.2.3", "^1.2.0", True), ("1.9.0", "^1.2.0", True), ("2.0.0", "^1.2.0", False), ("1.1.9", "^1.2.0", False),
    ("0.2.5", "^0.2.0", True), ("0.3.0", "^0.2.0", False), ("0.0.3", "^0.0.3", True), ("0.0.4", "^0.0.3", False),
    ("0.1.9", "^0.1.0", True), ("0.2.0", "^0.1.0", False),
    ("1.2.9", "~1.2.0", True), ("1.3.0", "~1.2.0", False), ("1.9.0", "~1", True), ("2.0.0", "~1", False),
    ("1.2.0", ">=1.2.0", True), ("1.1.9", ">=1.2.0", False), ("1.2.0", ">1.2.0", False), ("1.2.1", ">1.2.0", True),
    ("1.2.0", "<=1.2.0", True), ("1.2.1", "<=1.2.0", False), ("1.1.9", "<1.2.0", True), ("1.2.0", "<1.2.0", False),
    ("1.5.0", ">=1.2.0 <2.0.0", True), ("2.0.0", ">=1.2.0 <2.0.0", False), ("1.5.0", ">= 1.2.0  < 2.0.0", True),
    ("1.5.0", ">=1.2.0 <1.4.0", False), ("1.0.0", "<1.0.0 || >=1.5.0", False), ("1.6.0", "<1.0.0 || >=1.5.0", True),
    ("1.4.2", "1.x", True), ("2.0.0", "1.x", False), ("1.2.9", "1.2", True), ("1.3.0", "1.2", False), ("9.9.9", "*", True),
    ("1.2.3-beta.1", "^1.2.0", False), ("1.2.3-beta.1", ">=1.2.3-alpha.1 <1.3.0", True),
    ("1.2.3", ">=1.2.3-alpha.1", True), ("1.2.3-beta.2", ">1.2.3-beta.1", True),
]


@pytest.mark.parametrize("version,rng,expected", TABLE)
def test_satisfies(version, rng, expected):
    assert semver.satisfies(version, rng) is expected


@pytest.mark.parametrize("rng", ["banana", "^", ">=a.b.c", "1.2.3.4", "1.02.3"])
def test_invalid_ranges_raise(rng):
    with pytest.raises(ValueError):
        semver.satisfies("1.2.3", rng)


def test_highest_satisfying():
    vs = ["0.0.9", "0.1.2", "0.2.0", "not-a-version"]
    assert semver.highest_satisfying(vs, "^0.1.0") == "0.1.2"
    assert semver.highest_satisfying(vs, "^5.0.0") is None
    assert semver.compare(semver.parse_version("1.0.0-rc.1"), semver.parse_version("1.0.0")) == -1
