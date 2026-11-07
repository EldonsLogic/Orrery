import copy
import json
import os
import shutil

import pytest

from evals.harness import __main__ as cli
from evals.harness.adapters import Response, get_adapter
from evals.harness.records import load_set, validate_record
from evals.harness.runner import gate, load_threshold, run_set
from evals.harness.scorers import (score_answer, score_intent, score_normalized, score_record,
                                   score_tool_call, score_type_only)
from evals.harness.textnorm import normalize_arabic, normalize_digits, numbers_equal, parse_number

SETS = os.path.join(os.path.dirname(__file__), "fixtures", "sets")


def good():
    recs, errs = load_set("synthetic_mini", SETS)
    assert not errs
    return copy.deepcopy(recs[0])


# --- normalisation
def test_digits():
    assert normalize_digits("٠١٢٣٤٥٦٧٨٩") == "0123456789"
    assert normalize_digits("۰۱۲۳۴۵۶۷۸۹") == "0123456789"
    assert normalize_digits("١٢٫٥") == "12.5"


@pytest.mark.parametrize("v,n", [("١٢٬٥٠٠", 12500), ("12,500.50", 12500.5), ("۱۲٫۵", 12.5), (3, 3), ("١٥", 15)])
def test_parse_number(v, n):
    assert parse_number(v) == n


def test_parse_number_rejects():
    assert parse_number("abc") is None and parse_number(True) is None and parse_number(None) is None
    assert numbers_equal("١٢٬٥٠٠", 12500) and not numbers_equal("12", 13)


def test_arabic_normalisation():
    assert normalize_arabic("أَحْمَد") == normalize_arabic("احمد")
    assert normalize_arabic("إدارة") == normalize_arabic("ادارة") == normalize_arabic("آدارة")
    assert normalize_arabic("مـــدينة") == normalize_arabic("مدينه")
    assert normalize_arabic("على") == normalize_arabic("علي")
    assert normalize_arabic("فاتورة") == normalize_arabic("فاتوره")
    assert normalize_arabic("١٥ VAT") == "15 vat"


# --- scorers
def test_score_intent():
    e = {"type": "intent", "intent": "a.b"}
    assert score_intent(e, Response(kind="intent", intent="a.b"))[0]
    assert not score_intent(e, Response(kind="intent", intent="a.c"))[0]
    assert not score_intent(e, Response(kind="answer", intent="a.b"))[0]


def test_score_tool_call_subset():
    e = {"type": "tool_call", "intent": "a.b", "tool": "x.create", "args": {"currency": "SAR", "n": {"q": 3}}}
    ok = Response(kind="tool_call", intent="a.b", tool="x.create", args={"currency": "SAR", "n": {"q": "٣"}, "extra": 1})
    assert score_tool_call(e, ok)[0]
    assert not score_tool_call(e, Response(kind="tool_call", intent="a.b", tool="x.update", args=ok.args))[0]
    assert not score_tool_call(e, Response(kind="tool_call", intent="a.b", tool="x.create", args={"currency": "AED"}))[0]


def test_score_normalized():
    e = {"normalized": {"amount": 12500, "date": "2026-03-01", "hijri": {"y": 1447, "m": 9, "d": 15}, "percent": 15}}
    ok = Response(normalized={"amount": "١٢٬٥٠٠", "date": "2026-03-01", "hijri": {"y": 1447, "m": 9, "d": 15}, "percent": "١٥"})
    assert score_normalized(e, ok)[0]
    bad = Response(normalized={"amount": 12500, "date": "2026-3-1", "hijri": {"y": 1447, "m": 9, "d": 16}, "percent": 15})
    ok2, reasons = score_normalized(e, bad)
    assert not ok2 and len(reasons) == 2


def test_score_answer():
    e = {"type": "answer", "must_include": ["الفاتورة"], "must_not_include": ["مجانا"]}
    assert score_answer(e, Response(kind="answer", text="هذه الفَاتُورَة جاهزة"))[0]
    assert not score_answer(e, Response(kind="answer", text="لا شيء"))[0]
    assert not score_answer(e, Response(kind="answer", text="الفاتورة مجانا"))[0]
    assert not score_answer(e, Response(kind="refusal", text="الفاتورة"))[0]


def test_score_type_only():
    assert score_type_only({"type": "refusal"}, Response(kind="refusal"))[0]
    assert not score_type_only({"type": "clarify"}, Response(kind="refusal"))[0]


# --- schema
def test_schema_accepts_fixtures():
    recs, errs = load_set("synthetic_mini", SETS)
    assert len(recs) == 5 and not errs


@pytest.mark.parametrize("mutate", [
    lambda r: r.update(id="Bad_ID"),
    lambda r: r.update(id="ar-core-1"),
    lambda r: r.update(locale="fr"),
    lambda r: r.update(dialect="levantine"),
    lambda r: r.update(category="other"),
    lambda r: r.update(input=""),
    lambda r: r.update(input="x" * 1001),
    lambda r: r["expected"].update(type="guess"),
    lambda r: r["expected"].pop("intent"),
    lambda r: r["expected"].update(tool="a.b"),
    lambda r: r.update(extra=1),
    lambda r: r.pop("review"),
    lambda r: r["review"].update(nativeSpeaker="yes"),
    lambda r: r["expected"].update(normalized={"hijri": {"y": 1447, "m": 13, "d": 1}}),
    lambda r: r["expected"].update(normalized={"currency": "sar"}),
])
def test_schema_rejects(mutate):
    r = good()
    assert validate_record(r) == []
    mutate(r)
    assert validate_record(r)


# --- runner
def test_echo_and_null():
    echo = run_set("synthetic_mini", "echo_expected", SETS)
    assert echo["pass_rate"] == 1.0 and echo["total"] == 5 and not echo["failures"]
    null = run_set("synthetic_mini", "null", SETS)
    assert null["pass_rate"] == 0.0 and len(null["failures"]) == 5
    assert echo["by_category"]["numbers"]["total"] == 1
    assert echo["by_dialect"]["gulf"]["pass_rate"] == 1.0


def test_unknown_adapter():
    with pytest.raises(KeyError):
        get_adapter("nope")


def test_score_record_requires_normalized_too():
    r = next(x for x in load_set("synthetic_mini", SETS)[0] if x["id"] == "syn-mini-003")
    assert not score_record(r, Response(kind="intent", intent="calendar.convert_date"))[0]


def test_gate(tmp_path):
    d = tmp_path / "sets"
    shutil.copytree(SETS, d)
    assert load_threshold("synthetic_mini", str(d)) is None
    rep = run_set("synthetic_mini", "null", str(d))
    assert gate(rep, None)
    (d / "synthetic_mini" / "thresholds.json").write_text(json.dumps({"min_pass_rate": 0.5}))
    assert load_threshold("synthetic_mini", str(d)) == 0.5
    assert not gate(rep, 0.5) and rep["gate_passed"] is False
    assert cli.main(["--sets-dir", str(d), "run", "--set", "synthetic_mini", "--adapter", "null"]) == 1
    assert cli.main(["--sets-dir", str(d), "run", "--set", "synthetic_mini", "--adapter", "echo_expected"]) == 0


# --- CLI check
def test_check_fixtures(capsys):
    assert cli.main(["--sets-dir", SETS, "check"]) == 0
    out = capsys.readouterr().out
    assert "records: 5" in out and "category numbers: 1" in out


def test_check_empty(tmp_path, capsys):
    assert cli.main(["--sets-dir", str(tmp_path / "missing"), "check"]) == 0
    assert "records: 0" in capsys.readouterr().out


def test_check_errors(tmp_path, capsys):
    d = tmp_path / "sets" / "synthetic_mini"
    d.mkdir(parents=True)
    src = open(os.path.join(SETS, "synthetic_mini", "records.jsonl"), encoding="utf-8").read().splitlines()
    wrong_set = json.loads(src[0]); wrong_set["set"] = "other"; wrong_set["id"] = "syn-mini-010"
    (d / "a.jsonl").write_text("\n".join([src[0], src[0], "{not json", json.dumps(wrong_set)]) + "\n", encoding="utf-8")
    assert cli.main(["--sets-dir", str(tmp_path / "sets"), "check"]) == 1
    err = capsys.readouterr().err
    assert "duplicate id" in err and "invalid JSON" in err and "does not match folder" in err


def test_real_sets_validate():
    assert cli.main(["check"]) == 0


def test_run_missing_set_errors():
    assert cli.main(["--sets-dir", SETS, "run", "--set", "nope", "--adapter", "null"]) == 2
