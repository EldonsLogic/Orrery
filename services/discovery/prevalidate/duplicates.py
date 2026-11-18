"""Deterministic grouping of near-duplicate names. Suggestions for OWNER CONFIRMATION only.

Rules, applied to comparison keys from `normalise_arabic` (a key is never empty here):
  R1 exact_key     equal keys.
  R2 token_set     same multiset of tokens in any order ("النور مؤسسة" style reorderings).
  R3 edit_distance Levenshtein distance d <= threshold AND d <= len(shorter key) // 4
                   (so very short keys need an exact match), AND the digit sequences of
                   both keys are equal ("Store 1" is never merged with "Store 2").
Groups are connected components over those rules (transitive; the owner confirms each).
Nothing is merged or renamed here. Canonical = most frequent display form, ties by first seen.
"""
from __future__ import annotations

from .arabic import normalise_arabic
from .errors import PrevalidationError

MAX_DISTINCT_KEYS = 5000
_RANK = {"exact_key": 0, "token_set": 1, "edit_distance": 2}


def _lev(a: str, b: str, cap: int) -> int:
    """Levenshtein distance, early exit when it exceeds cap (returns cap + 1)."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def _digits(k: str) -> str:
    return "".join(c for c in k if c.isdigit())


def _similar(ka: str, kb: str, threshold: int):
    if ka == kb:
        return "exact_key"
    if sorted(ka.split()) == sorted(kb.split()):
        return "token_set"
    if threshold > 0 and _digits(ka) == _digits(kb):
        cap = min(threshold, min(len(ka), len(kb)) // 4)
        if cap > 0 and _lev(ka, kb, cap) <= cap:
            return "edit_distance"
    return None


def group_duplicates(names, threshold: int = 1) -> list:
    if not isinstance(names, (list, tuple)) or any(not isinstance(n, str) for n in names):
        raise PrevalidationError("PRE-E05")
    if isinstance(threshold, bool) or not isinstance(threshold, int) or not 0 <= threshold <= 3:
        raise PrevalidationError("PRE-E03", "threshold")
    forms = {}  # display -> [count, first_index, key]
    for i, n in enumerate(names):
        key = normalise_arabic(n)
        if not key:
            continue
        if n in forms:
            forms[n][0] += 1
        else:
            forms[n] = [1, i, key]
    keys = {}
    for disp, (c, first, key) in forms.items():
        keys.setdefault(key, []).append(disp)
    klist = sorted(keys, key=lambda k: min(forms[d][1] for d in keys[k]))
    if len(klist) > MAX_DISTINCT_KEYS:
        raise PrevalidationError("PRE-E04", "distinct_names")
    parent = list(range(len(klist)))
    worst = {}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    links = []
    for i in range(len(klist)):
        for j in range(i + 1, len(klist)):
            r = _similar(klist[i], klist[j], threshold)
            if r:
                links.append((i, j, r))
    for i, j, r in links:
        a, b = find(i), find(j)
        if a != b:
            parent[max(a, b)] = min(a, b)
    comps = {}
    for i in range(len(klist)):
        comps.setdefault(find(i), []).append(i)
    for i, j, r in links:
        root = find(i)
        if _RANK[r] > _RANK.get(worst.get(root), -1):
            worst[root] = r
    out = []
    for root, idxs in comps.items():
        disp = [d for i in idxs for d in keys[klist[i]]]
        if len(disp) < 2:
            continue
        disp.sort(key=lambda d: forms[d][1])
        canon = sorted(disp, key=lambda d: (-forms[d][0], forms[d][1]))[0]
        out.append({
            "canonical": canon,
            "members": [{"name": d, "count": forms[d][0], "first_index": forms[d][1]} for d in disp],
            "keys": sorted({klist[i] for i in idxs}),
            "rule": worst.get(root, "exact_key"),
            "needs_owner_confirmation": True,
        })
    out.sort(key=lambda g: g["members"][0]["first_index"])
    return out
