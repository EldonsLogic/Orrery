"""Deterministic scorers. Each returns (passed: bool, reasons: list[str]). No model calls."""
from .adapters import Response
from .textnorm import normalize_arabic, numbers_equal


def score_intent(expected: dict, resp: Response):
    ok = resp.kind == expected["type"] and resp.intent == expected.get("intent")
    return ok, [] if ok else [f"intent: want {expected.get('intent')!r}, got {resp.intent!r}"]


def _subset(want, got) -> bool:
    if isinstance(want, dict):
        return isinstance(got, dict) and all(k in got and _subset(v, got[k]) for k, v in want.items())
    if isinstance(want, list):
        return isinstance(got, list) and len(want) == len(got) and all(_subset(a, b) for a, b in zip(want, got))
    if isinstance(want, (int, float)) and not isinstance(want, bool):
        return numbers_equal(got, want)
    return want == got


def score_tool_call(expected: dict, resp: Response):
    reasons = []
    if resp.kind != "tool_call":
        reasons.append(f"type: want tool_call, got {resp.kind!r}")
    if resp.intent != expected.get("intent"):
        reasons.append(f"intent: want {expected.get('intent')!r}, got {resp.intent!r}")
    if "tool" in expected and resp.tool != expected["tool"]:
        reasons.append(f"tool: want {expected['tool']!r}, got {resp.tool!r}")
    if not _subset(expected.get("args", {}), resp.args or {}):
        reasons.append("args: expected subset not matched")
    return not reasons, reasons


def score_normalized(expected: dict, resp: Response):
    reasons = []
    got = resp.normalized or {}
    for key, want in (expected.get("normalized") or {}).items():
        have = got.get(key)
        if key == "hijri":
            ok = isinstance(have, dict) and set(have) == set(want) and all(numbers_equal(have[k], want[k]) for k in want)
        elif key in ("date", "currency"):
            ok = have == want
        else:
            ok = numbers_equal(have, want)
        if not ok:
            reasons.append(f"normalized.{key}: want {want!r}, got {have!r}")
    return not reasons, reasons


def score_answer(expected: dict, resp: Response):
    reasons = []
    if resp.kind != "answer":
        reasons.append(f"type: want answer, got {resp.kind!r}")
    text = normalize_arabic(resp.text)
    for s in expected.get("must_include", []):
        if normalize_arabic(s) not in text:
            reasons.append(f"must_include missing: {s!r}")
    for s in expected.get("must_not_include", []):
        if normalize_arabic(s) in text:
            reasons.append(f"must_not_include present: {s!r}")
    return not reasons, reasons


def score_type_only(expected: dict, resp: Response):
    ok = resp.kind == expected["type"]
    return ok, [] if ok else [f"type: want {expected['type']!r}, got {resp.kind!r}"]


_BY_TYPE = {"intent": score_intent, "tool_call": score_tool_call, "answer": score_answer,
            "clarify": score_type_only, "refusal": score_type_only}


def score_record(record: dict, resp: Response):
    """A record passes only if its type scorer and (when present) the normalized scorer pass."""
    exp = record["expected"]
    ok, reasons = _BY_TYPE[exp["type"]](exp, resp)
    if exp.get("normalized"):
        ok2, r2 = score_normalized(exp, resp)
        ok, reasons = ok and ok2, reasons + r2
    return ok, reasons
