"""Small npm-style semver range matcher: exact, ^, ~, >=, <=, >, <, x-ranges, space = AND, || = OR."""
from __future__ import annotations

import re

_VER = r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?"
_VER_RE = re.compile(rf"^{_VER}$")
_TOKEN_RE = re.compile(r"(\^|~|>=|<=|>|<|=)?\s*(v?[0-9xX*][0-9A-Za-z.*+-]*|\*)")


def parse_version(text: str):
    """Return (major, minor, patch, prerelease_tuple) or raise ValueError."""
    m = _VER_RE.match(text.strip()) if isinstance(text, str) else None
    if not m:
        raise ValueError(f"invalid version: {text!r}")
    pre = tuple(m.group(4).split(".")) if m.group(4) else ()
    return int(m.group(1)), int(m.group(2)), int(m.group(3)), pre


def _cmp_pre(a: tuple, b: tuple) -> int:
    if not a and not b:
        return 0
    if not a:
        return 1  # a release is greater than its prerelease
    if not b:
        return -1
    for x, y in zip(a, b):
        if x == y:
            continue
        xn, yn = x.isdigit(), y.isdigit()
        if xn and yn:
            return -1 if int(x) < int(y) else 1
        if xn != yn:
            return -1 if xn else 1
        return -1 if x < y else 1
    return (len(a) > len(b)) - (len(a) < len(b))


def compare(a, b) -> int:
    if a[:3] != b[:3]:
        return -1 if a[:3] < b[:3] else 1
    return _cmp_pre(a[3], b[3])


def _partial(text: str):
    """Parse '1', '1.2', '1.2.x', '*', '1.2.3-beta' into (major, minor, patch, pre) with None wildcards."""
    t = text.lstrip("v")
    if t in ("*", "x", "X", ""):
        return None, None, None, ()
    pre: tuple = ()
    if "-" in t:
        t, p = t.split("-", 1)
        pre = tuple(p.split("."))
    t = t.split("+", 1)[0]
    parts = t.split(".")
    if len(parts) > 3:
        raise ValueError(f"invalid range part: {text!r}")
    nums: list = []
    for p in parts:
        if p in ("x", "X", "*"):
            nums.append(None)
        elif p.isdigit() and (p == "0" or not p.startswith("0")):
            nums.append(int(p))
        else:
            raise ValueError(f"invalid range part: {text!r}")
    while len(nums) < 3:
        nums.append(None)
    # a wildcard hides everything to its right
    for i in range(3):
        if nums[i] is None:
            nums[i:] = [None] * (3 - i)
            break
    return nums[0], nums[1], nums[2], pre


def _ge(maj, mn, pat, pre):
    return (">=", (maj or 0, mn or 0, pat or 0, pre))


def _lt(maj, mn, pat):
    return ("<", (maj, mn, pat, ()))


def _comparators(op: str, part: str) -> list[tuple]:
    maj, mn, pat, pre = _partial(part)
    if maj is None:  # any version
        return [] if op in ("", "=", ">=", "<=", "^", "~") else [("<", (0, 0, 0, ()))]
    if op == "^":
        if maj > 0 or mn is None:
            hi = (maj + 1, 0, 0)
        elif mn > 0 or pat is None:
            hi = (0, mn + 1, 0)
        else:
            hi = (0, 0, pat + 1)
        return [_ge(maj, mn, pat, pre), _lt(*hi)]
    if op == "~":
        hi = (maj + 1, 0, 0) if mn is None else (maj, mn + 1, 0)
        return [_ge(maj, mn, pat, pre), _lt(*hi)]
    if op in ("", "="):
        if pat is not None:
            return [("=", (maj, mn, pat, pre))]
        hi = (maj + 1, 0, 0) if mn is None else (maj, mn + 1, 0)
        return [_ge(maj, mn, pat, pre), _lt(*hi)]
    if op == ">=":
        return [_ge(maj, mn, pat, pre)]
    if op == "<":
        return [("<", (maj, mn or 0, pat or 0, pre))]
    if op == ">":
        if pat is None:  # >1.2 means >=1.3.0
            nxt = (maj + 1, 0, 0) if mn is None else (maj, mn + 1, 0)
            return [(">=", (*nxt, ()))]
        return [(">", (maj, mn, pat, pre))]
    if op == "<=":
        if pat is None:  # <=1.2 means <1.3.0
            hi = (maj + 1, 0, 0) if mn is None else (maj, mn + 1, 0)
            return [_lt(*hi)]
        return [("<=", (maj, mn, pat, pre))]
    raise ValueError(f"invalid operator: {op!r}")


def _parse_set(text: str) -> list[tuple]:
    text = text.strip()
    pos, comps = 0, []
    if not text:
        return comps  # empty set means any
    while pos < len(text):
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos >= len(text):
            break
        m = _TOKEN_RE.match(text, pos)
        if not m or m.start() != pos:
            raise ValueError(f"invalid range: {text!r}")
        comps.extend(_comparators(m.group(1) or "", m.group(2)))
        pos = m.end()
    return comps


def _holds(version, comp) -> bool:
    op, target = comp
    c = compare(version, target)
    return {"=": c == 0, ">=": c >= 0, ">": c > 0, "<=": c <= 0, "<": c < 0}[op]


def satisfies(version: str, range_text: str) -> bool:
    """True when `version` is inside `range_text`. Raises ValueError for invalid input.

    As in npm, a prerelease version only matches a set that contains a comparator with the same
    major.minor.patch and a prerelease tag.
    """
    v = parse_version(version)
    if not isinstance(range_text, str) or len(range_text) > 200:
        raise ValueError("invalid range")
    for alt in range_text.split("||"):
        comps = _parse_set(alt)
        if not all(_holds(v, c) for c in comps):
            continue
        if v[3] and not any(c[1][3] and c[1][:3] == v[:3] for c in comps):
            continue
        return True
    return False


def highest_satisfying(versions, range_text: str):
    """Highest version string from `versions` inside the range, or None. Invalid ranges raise ValueError."""
    best = None
    for s in versions:
        try:
            pv = parse_version(s)
        except ValueError:
            continue
        if satisfies(s, range_text) and (best is None or compare(pv, best[0]) > 0):
            best = (pv, s)
    return best[1] if best else None
