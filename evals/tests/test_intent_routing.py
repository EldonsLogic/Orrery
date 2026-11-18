"""QA-020: intent-routing experiment. Offline; checks the case set, the rules arm and the scorer."""
import json
import re
from collections import Counter

import pytest

from evals.harness import intent_routing as ir

CASES, ERRORS = ir.load_cases()
BY_ID = {c["id"]: c for c in CASES}


def _write(tmp_path, rows, name="pred.ndjson"):
    path = tmp_path / name
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return str(path)


def _oracle():
    return {c["id"]: {"id": c["id"], "intent": c["expected_intent"], "risk_class": c["expected_risk_class"],
                      "latency_ms": 1.0, "cost_usd": 0.001} for c in CASES}


# ---- case set ----

def test_case_set_loads_clean():
    assert ERRORS == []


def test_sixty_cases_split_evenly_by_language():
    assert len(CASES) == 60
    counts = Counter(c["lang"] for c in CASES)
    assert counts == {"en": 30, "ar": 30}


def test_ids_are_unique_and_well_formed():
    assert len(BY_ID) == 60
    assert all(ir.ID_RE.match(c["id"]) for c in CASES)


def test_arabic_cases_are_unreviewed_and_english_have_no_review():
    assert all(c["review"] == "unreviewed" for c in CASES if c["lang"] == "ar")
    assert all(c["review"] is None for c in CASES if c["lang"] == "en")


def test_risk_class_follows_intent_map():
    for c in CASES:
        assert c["expected_risk_class"] == ir.INTENT_RISK[c["expected_intent"]], c["id"]


def test_every_vocabulary_intent_is_covered():
    used = {c["expected_intent"] for c in CASES}
    assert used == set(ir.INTENT_RISK), set(ir.INTENT_RISK) - used


def test_every_risk_class_is_covered():
    assert {c["expected_risk_class"] for c in CASES} == set(ir.RISK_CLASSES)


def test_arabic_dialect_spread_and_code_switching():
    dialects = Counter(c["dialect"] for c in CASES if c["lang"] == "ar")
    for d in ("msa", "gulf", "egyptian", "levantine", "mixed"):
        assert dialects[d] >= 2, d
    assert dialects["mixed"] >= 5


def test_ambiguity_flags_are_present_in_both_languages():
    assert sum(c["ambiguous"] for c in CASES if c["lang"] == "en") >= 2
    assert sum(c["ambiguous"] for c in CASES if c["lang"] == "ar") >= 2


def test_no_contact_details_or_real_looking_identifiers():
    iban_like = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{12,}")
    for c in CASES:
        assert "@" not in c["text"], c["id"]
        for m in iban_like.findall(c["text"]):
            assert m.startswith("XX00TEST"), (c["id"], m)


def test_check_case_rejects_bad_records():
    good = dict(CASES[0])
    assert ir.check_case(good) == []
    bad_review = dict(next(c for c in CASES if c["lang"] == "ar"), review=None)
    assert any("unreviewed" in e for e in ir.check_case(bad_review))
    bad_risk = dict(good, expected_risk_class="R0", expected_intent="sales.create_invoice")
    assert any("does not match" in e for e in ir.check_case(bad_risk))
    bad_intent = dict(good, expected_intent="made.up")
    assert any("not in vocabulary" in e for e in ir.check_case(bad_intent))
    missing = {k: v for k, v in good.items() if k != "ambiguous"}
    assert any("missing ambiguous" in e for e in ir.check_case(missing))


def test_load_cases_reports_duplicate_ids(tmp_path):
    line = json.dumps(CASES[0], ensure_ascii=False)
    path = tmp_path / "dup.ndjson"
    path.write_text(line + "\n" + line + "\n", encoding="utf-8")
    _, errors = ir.load_cases(str(path))
    assert any("duplicate id" in e for e in errors)


# ---- rules arm ----

def test_rules_arm_predicts_every_case_and_costs_nothing():
    preds = ir.run_rules(CASES)
    assert len(preds) == 60
    assert all(p["cost_usd"] == 0.0 for p in preds)
    assert all(p["latency_ms"] >= 0 for p in preds)


def test_rules_risk_class_is_always_the_intent_map():
    for p in ir.run_rules(CASES):
        if p["intent"] is not None:
            assert p["risk_class"] == ir.INTENT_RISK[p["intent"]]


def test_rules_baseline_snapshot():
    # Snapshot of the baseline on this set. The rules were written after the cases were drafted, so this is a
    # sanity check, not an out-of-sample estimate (see the research note, threats to validity).
    preds = {p["id"]: p for p in ir.run_rules(CASES)}
    misses = {c["id"] for c in CASES if preds[c["id"]]["intent"] != c["expected_intent"]}
    assert misses == {"ir-en-027", "ir-ar-023"}
    assert all(BY_ID[i]["ambiguous"] for i in misses)


def test_rules_abstain_on_ambiguous_text_with_no_keyword():
    assert ir.route_rules("Show Nile Supplies") is None


def test_rules_abstain_when_two_intents_match():
    # "stock" (inventory) and "return" (returns) both match: abstain rather than guess.
    assert ir.route_rules("Record a return and check the stock") is None


def test_arabic_hamza_forms_route_to_the_same_intent():
    # ئ in دائن loses its hamza mark during matching, so both spellings must route.
    assert ir.route_rules("أصدر إشعار دائن") == "sales.create_credit_note"
    assert ir.route_rules("أصدر إشعار داين") == "sales.create_credit_note"


def test_arabic_digits_and_diacritics_do_not_block_routing():
    assert ir.route_rules("عَايِز أرجع ٢ قطعة") == "sales.record_return"
    assert ir.route_rules("سجل صرف ١٥٠٠ جنيه للكهربا") == "finance.post_disbursement"


def test_rules_dialect_words_route():
    assert ir.route_rules("ودي أضيف عميل جديد") == "customers.create"
    assert ir.route_rules("ازاي أسجل عهدة 2000 جنيه") == "finance.record_custody"


# ---- scorer ----

def test_oracle_scores_perfectly():
    r = ir.score(CASES, _oracle())
    assert r["accuracy"] == 1.0
    assert r["macro_f1"] == 1.0
    assert r["wrong_risk_class_rate"] == 0.0
    assert r["under_classified_rate"] == 0.0
    assert r["abstain_rate"] == 0.0
    assert r["missing_predictions"] == 0
    assert r["cost_per_1000_usd"] == pytest.approx(1.0)


def test_all_abstain_scores_zero_accuracy_and_full_abstain():
    r = ir.score(CASES, {})
    assert r["accuracy"] == 0.0
    assert r["abstain_rate"] == 1.0
    assert r["missing_predictions"] == 60
    assert r["cost_per_1000_usd"] is None
    assert r["latency_ms"]["n"] == 0


def test_under_classified_risk_is_counted_separately():
    preds = _oracle()
    # create_invoice is R3; routing it to create_quote (R1) under-classifies the risk.
    preds["ir-en-005"] = dict(preds["ir-en-005"], intent="sales.create_quote", risk_class="R1")
    r = ir.score(CASES, preds)
    assert r["under_classified_rate"] == pytest.approx(1 / 60, abs=1e-4)
    assert r["wrong_risk_class_rate"] == pytest.approx(1 / 60, abs=1e-4)
    assert r["over_classified_rate"] == 0.0
    assert r["accuracy"] == pytest.approx(59 / 60, abs=1e-4)


def test_over_classified_risk_is_not_under_classified():
    preds = _oracle()
    preds["ir-en-006"] = dict(preds["ir-en-006"], intent="sales.create_invoice", risk_class="R3")
    r = ir.score(CASES, preds)
    assert r["over_classified_rate"] == pytest.approx(1 / 60, abs=1e-4)
    assert r["under_classified_rate"] == 0.0


def test_per_intent_f1_reflects_a_single_confusion():
    preds = _oracle()
    preds["ir-en-005"] = dict(preds["ir-en-005"], intent="sales.create_quote", risk_class="R1")
    r = ir.score(CASES, preds)
    # sales.create_invoice has three gold cases (en-005, ar-004, ar-014); one miss leaves recall at 2/3.
    assert r["per_intent"]["sales.create_invoice"]["support"] == 3
    assert r["per_intent"]["sales.create_invoice"]["recall"] == pytest.approx(2 / 3, abs=1e-4)
    # sales.create_quote has two gold cases (en-006, ar-005) and one false positive (en-005): precision 2/3, recall 1.
    assert r["per_intent"]["sales.create_quote"]["precision"] == pytest.approx(2 / 3, abs=1e-4)
    assert r["per_intent"]["sales.create_quote"]["recall"] == 1.0


def test_abstain_counts_as_false_negative_for_its_gold_intent():
    preds = _oracle()
    preds["ir-en-001"] = dict(preds["ir-en-001"], intent=None, risk_class=None)
    r = ir.score(CASES, preds)
    assert r["abstain_rate"] == pytest.approx(1 / 60, abs=1e-4)
    # finance.vat_summary has three gold cases (en-001, ar-001, ar-025); abstaining on one leaves recall at 2/3.
    assert r["per_intent"]["finance.vat_summary"]["recall"] == pytest.approx(2 / 3, abs=1e-4)


def test_latency_percentiles_and_cost_per_1000(tmp_path):
    preds = []
    for i, c in enumerate(CASES):
        preds.append({"id": c["id"], "intent": c["expected_intent"], "latency_ms": float(i + 1), "cost_usd": 0.002})
    r = ir.score(CASES, {p["id"]: p for p in preds})
    assert r["latency_ms"]["p50"] == 30.0
    assert r["latency_ms"]["p95"] == 57.0
    assert r["cost_per_1000_usd"] == pytest.approx(2.0)


def test_unknown_intent_is_counted_and_scores_wrong():
    preds = _oracle()
    preds["ir-en-001"] = {"id": "ir-en-001", "intent": "made.up", "latency_ms": 1.0}
    r = ir.score(CASES, preds)
    assert r["unknown_intents"] == 1
    assert r["accuracy"] == pytest.approx(59 / 60, abs=1e-4)


def test_group_breakdowns_have_both_languages_and_dialects():
    r = ir.score(CASES, _oracle())
    assert set(r["by_lang"]) == {"en", "ar"}
    assert set(r["by_dialect"]) == {"none", "msa", "gulf", "egyptian", "levantine", "mixed"}
    assert r["by_lang"]["ar"]["n"] == 30


# ---- predictions file and CLI ----

def test_load_predictions_rejects_unknown_and_duplicate_ids(tmp_path):
    unknown = _write(tmp_path, [{"id": "ir-en-999", "intent": None}], "u.ndjson")
    with pytest.raises(ValueError, match="not in the case set"):
        ir.load_predictions(unknown, CASES)
    dup = _write(tmp_path, [{"id": "ir-en-001", "intent": None}, {"id": "ir-en-001", "intent": None}], "d.ndjson")
    with pytest.raises(ValueError, match="duplicate"):
        ir.load_predictions(dup, CASES)


def test_load_predictions_rejects_bad_risk_class(tmp_path):
    bad = _write(tmp_path, [{"id": "ir-en-001", "intent": "finance.vat_summary", "risk_class": "R9"}], "r.ndjson")
    with pytest.raises(ValueError, match="R0 to R4"):
        ir.load_predictions(bad, CASES)


def test_cli_rules_then_score_round_trip(tmp_path, capsys):
    out_pred = tmp_path / "rules.ndjson"
    out_score = tmp_path / "score.json"
    assert ir.main(["rules", "--out", str(out_pred)]) == 0
    assert ir.main(["score", "--predictions", str(out_pred), "--out", str(out_score)]) == 0
    report = json.loads(out_score.read_text(encoding="utf-8"))
    assert report["cases"] == 60
    assert report["accuracy"] == pytest.approx(58 / 60, abs=1e-4)


def test_cli_score_exits_2_on_bad_predictions(tmp_path):
    bad = _write(tmp_path, [{"id": "nope", "intent": None}], "bad.ndjson")
    assert ir.main(["score", "--predictions", bad]) == 2
