import copy
import hashlib
import json

import pytest
from jsonschema import Draft202012Validator

from helpers import ANSWERS, BLUEPRINT_SCHEMA, QUESTIONS, QUESTIONS_SCHEMA, TEMPLATE, TEMPLATE_DIR, registry
from instantiate import InstantiationError, instantiate, load_template, main
from validator import ValidationContext, validate

PLACEHOLDER = "{{company.name}}"


def template_files():
    return sorted(p for p in TEMPLATE_DIR.rglob("*") if p.is_file())


def digest():
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in template_files()}


def walk(node, path=""):
    yield path, node
    if isinstance(node, dict):
        for k, v in node.items():
            yield from walk(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, f"{path}/{i}")


def resolve(doc, pointer):
    cur = doc
    if pointer == "":
        return cur
    for raw in pointer.split("/")[1:]:
        key = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(cur, list):
            cur = cur[int(key)]
        elif isinstance(cur, dict):
            cur = cur[key]
        else:
            raise KeyError(pointer)
    return cur


def resolves(doc, pointer):
    try:
        resolve(doc, pointer)
        return True
    except (KeyError, IndexError, ValueError):
        return False


def ctx():
    return ValidationContext(registry=registry())


# ---- template -------------------------------------------------------------------------------
def test_template_files_are_short():
    for p in template_files():
        assert len(p.read_text(encoding="utf-8").splitlines()) < 500, p.name


def test_template_is_schema_valid():
    schema = json.loads(BLUEPRINT_SCHEMA.read_text(encoding="utf-8"))
    errs = list(Draft202012Validator(schema).iter_errors(load_template(TEMPLATE)))
    assert errs == [], [e.message for e in errs[:3]]


def test_every_provenance_is_template_and_draft():
    bp = load_template(TEMPLATE)
    assert bp["meta"]["buildState"] == "draft"
    found = [(p, n) for p, n in walk(bp) if p.endswith("/provenance")]
    assert len(found) > 40
    for p, n in found:
        assert n == {"source": "template", "ref": "trading_distribution@0.1.0", "humanEdited": False}, p
    for key in ("components", "entities", "workflows", "roles", "approvals", "reports"):
        assert all("provenance" in x for x in bp[key]), key
    assert "provenance" in bp["branding"]


def test_localized_text_complete_and_non_empty():
    bp = load_template(TEMPLATE)
    texts = [(p, n) for p, n in walk(bp) if isinstance(n, dict) and p.rsplit("/", 1)[-1] in
             ("labels", "pluralLabels", "actionLabels", "translations", "legalName", "displayName", "headline",
              "footerText")]
    assert len(texts) > 300
    for p, n in texts:
        assert set(n) == {"ar", "en"} and all(isinstance(v, str) and v.strip() for v in n.values()), p
    for p, n in walk(bp["i18n"]["labelOverrides"]):
        if isinstance(n, dict) and "ar" in n:
            assert n["en"].strip() and n["ar"].strip()
    for e in bp["entities"]:
        for f in e["fields"]:
            for o in f.get("options", []):
                assert o["labels"]["ar"].strip() and o["labels"]["en"].strip()


def test_arabic_labels_contain_arabic_letters():
    bp = load_template(TEMPLATE)
    for e in bp["entities"]:
        assert any("؀" <= c <= "ۿ" for c in e["labels"]["ar"]), e["id"]


def test_only_the_name_placeholder_has_braces():
    bp = load_template(TEMPLATE)
    for p, n in walk(bp):
        if isinstance(n, str) and ("{" in n or "}" in n):
            assert PLACEHOLDER in n and n.replace(PLACEHOLDER, "").count("{") == 0, p
            assert p.split("/")[1] in ("company", "branding"), p


def test_no_company_specific_data_left():
    text = TEMPLATE.read_text(encoding="utf-8") + "".join(p.read_text(encoding="utf-8") for p in TEMPLATE_DIR.glob("parts/*.json"))
    for word in ("Riyadh", "Jeddah", "Waha", "الرياض", "جدة", "الواحة", "SAR", "1010000000", "300000000000003", "crNumber", "vatNumber"):
        assert word not in text, word
    bp = load_template(TEMPLATE)
    assert "tradeName" not in bp["company"]
    for e in bp["entities"]:
        for f in e["fields"]:
            if f["id"] == "vat_rate":
                assert "default" not in f  # tax rates come from components and country packs


def test_engine_name_absent_from_template_files():
    for p in template_files():
        assert "frappe" not in p.read_text(encoding="utf-8").lower() and "erpnext" not in p.read_text(encoding="utf-8").lower()


def test_template_covers_the_expected_documents():
    ids = {e["id"] for e in load_template(TEMPLATE)["entities"]}
    assert {"customer", "supplier", "item", "sales_quote", "sales_order", "delivery_note", "sales_invoice", "credit_note",
            "purchase_order", "purchase_receipt", "payment", "stock_transfer"} <= ids


# ---- instantiate ---------------------------------------------------------------------------
@pytest.mark.parametrize("country", ["sa", "ae", "eg", "qa"])
def test_instantiate_has_zero_validator_errors(country):
    bp = instantiate(TEMPLATE, ANSWERS[country], now="2026-01-01T00:00:00Z")
    rep = validate(bp, ctx())
    assert rep.errors == [], [str(e) for e in rep.errors]
    assert bp["company"]["country"] == country.upper() == bp["compliance"]["country"]
    assert bp["compliance"]["countryPack"]["id"] == country
    assert "{{" not in json.dumps(bp, ensure_ascii=False)
    assert bp["company"]["legalName"] == {"ar": ANSWERS[country]["name_ar"], "en": ANSWERS[country]["name_en"]}


def test_sa_keeps_zatca_and_others_drop_it():
    sa = instantiate(TEMPLATE, ANSWERS["sa"])
    assert sa["compliance"]["eInvoicing"]["mode"] == "zatca_phase2"
    assert "compliance.zatca_sa" in {c["id"] for c in sa["components"]}
    for key in ("ae", "eg", "qa"):
        other = instantiate(TEMPLATE, ANSWERS[key])
        assert "compliance.zatca_sa" not in json.dumps(other)
        assert "zatca" not in json.dumps(other).lower()


def test_branches_add_locations_and_rebuild_selects():
    bp = instantiate(TEMPLATE, ANSWERS["sa"])
    ids = [x["id"] for x in bp["locations"]]
    assert ids == ["hq", "wh_main", "dept_finance", "branch_2", "wh_2"]
    so = next(e for e in bp["entities"] if e["id"] == "sales_order")
    wh = next(f for f in so["fields"] if f["id"] == "warehouse")
    assert [o["value"] for o in wh["options"]] == ["wh_main", "wh_2"]
    keeper = next(r for r in bp["roles"] if r["id"] == "warehouse_keeper")
    assert keeper["scope"]["values"] == ["wh_main", "wh_2"]
    assert validate(bp, ctx()).errors == []


def test_unregistered_company_has_no_einvoicing():
    bp = instantiate(TEMPLATE, ANSWERS["eg"])
    assert bp["compliance"]["eInvoicing"] == {"mode": "none"} and bp["compliance"]["vat"] == {"registered": False}
    assert bp["company"]["locale"] == {"currency": "EGP"}


def test_arabic_only_and_english_first_languages():
    ar = instantiate(TEMPLATE, {**ANSWERS["sa"], "languages": ["ar"]})
    assert ar["company"]["languages"] == {"primary": "ar"} and ar["compliance"]["documentLanguages"] == ["ar"]
    assert validate(ar, ctx()).errors == []
    en_first = instantiate(TEMPLATE, {**ANSWERS["ae"], "languages": ["en", "ar"]})
    assert en_first["meta"]["defaultLocale"] == "en" == en_first["i18n"]["defaultLocale"]
    assert validate(en_first, ctx()).errors == []


def test_sa_without_vat_number_is_flagged_by_the_validator_not_hidden():
    answers = {k: v for k, v in ANSWERS["sa"].items() if k != "vat_number"}
    rep = validate(instantiate(TEMPLATE, answers), ctx())
    assert [e.code for e in rep.errors] == ["BP-EINV-002"]


def test_default_answers_work_for_every_country():
    for c in ("sa", "ae", "eg", "qa"):
        bp = instantiate(TEMPLATE, {"country": c, "name_ar": "شركة", "name_en": "Co"})
        assert validate(bp, ctx()).errors == []
        assert bp["meta"]["buildState"] == "draft" and len(bp["locations"]) == 3


@pytest.mark.parametrize("bad", [
    {"extra": 1}, {"vat": True}, {"name_ar": ["x"]}, {"name_en": {"a": 1}}, {"name_en": None}, {"branches": [1]},
    {"branches": 0}, {"branches": 1.5}, {"branches": 51}, {"branches": True}, {"country": "qa"}, {"country": 5},
    {"vat_registered": "yes"}, {"currency": "sar1"}, {"languages": ["en"]}, {"languages": ["ar", "ar"]},
    {"languages": [["ar"]]}, {"languages": [{"ar": 1}]}, {"vat_number": "123"}, {"cr_number": 5},
    {"name_en": "{{company.name}}"}, {"name_ar": "x}"}, {"name_en": "a" * 121}, {"branches": float("inf")},
    {"vat_registered": False, "vat_number": "300000000000003"},
])
def test_bad_answers_are_rejected(bad):
    answers = {**ANSWERS["sa"], **bad}
    if "vat_registered" in bad and bad["vat_registered"] is False:
        answers["vat_number"] = bad.get("vat_number", answers["vat_number"])
    with pytest.raises(InstantiationError):
        instantiate(TEMPLATE, answers)


def test_unknown_key_message_and_missing_required():
    with pytest.raises(InstantiationError, match="unknown answer key"):
        instantiate(TEMPLATE, {**ANSWERS["sa"], "company_name": "x"})
    with pytest.raises(InstantiationError, match="missing"):
        instantiate(TEMPLATE, {"country": "sa"})
    with pytest.raises(InstantiationError):
        instantiate(TEMPLATE, ["not", "a", "dict"])


def test_answers_are_not_mutated_and_template_untouched():
    before = digest()
    answers = copy.deepcopy(ANSWERS["sa"])
    snapshot = copy.deepcopy(answers)
    bp1 = instantiate(TEMPLATE, answers, now="2026-01-01T00:00:00Z")
    bp1["entities"].clear()  # mutating a result must not leak into the next call
    bp2 = instantiate(TEMPLATE, answers, now="2026-01-01T00:00:00Z")
    assert answers == snapshot and bp2["entities"]
    assert digest() == before
    assert "{{company.name}}" in TEMPLATE.read_text(encoding="utf-8")


def test_includes_cannot_leave_the_template_folder(tmp_path):
    (tmp_path / "outside.json").write_text("[]", encoding="utf-8")
    sub = tmp_path / "t"
    sub.mkdir()
    (sub / "b.json").write_text(json.dumps({"entities": [{"$include": "../outside.json"}]}), encoding="utf-8")
    with pytest.raises(InstantiationError, match="outside"):
        load_template(sub / "b.json")


def test_cli_stdout_and_out_file(tmp_path, capsys):
    base = ["--country", "ae", "--name-ar", "شركة", "--name-en", "Co", "--vat-registered", "no"]
    assert main(base) == 0
    out = capsys.readouterr()
    assert json.loads(out.out)["company"]["country"] == "AE"
    target = tmp_path / "bp.json"
    assert main(base + ["--out", str(target)]) == 0
    assert json.loads(target.read_text(encoding="utf-8"))["meta"]["buildState"] == "draft"
    assert capsys.readouterr().out == ""
    assert main(["--country", "xx", "--name-ar", "a", "--name-en", "b"]) == 1


# ---- questions -----------------------------------------------------------------------------
def test_questions_validate_against_their_schema():
    schema = json.loads(QUESTIONS_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    doc = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    errs = list(Draft202012Validator(schema).iter_errors(doc))
    assert errs == [], [e.message for e in errs[:3]]


def test_questions_cover_all_sections_with_both_languages():
    doc = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    assert [s["id"] for s in doc["sections"]] == ["company", "locations", "roles_approvals", "sales_flow",
                                                  "purchase_flow", "stock", "pricing", "compliance"]
    ids = [q["id"] for s in doc["sections"] for q in s["questions"]]
    assert len(ids) == len(set(ids))
    for s in doc["sections"]:
        for q in s["questions"]:
            assert q["text"]["ar"].strip() and q["text"]["en"].strip()
            if q["required"]:  # no safe default: the value is null; optional facts may also be null (leave empty)
                assert q["defaultIfUnknown"]["value"] is None, q["id"]


def test_every_pointer_resolves_in_the_template():
    bp = load_template(TEMPLATE)
    doc = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    for s in doc["sections"]:
        for q in s["questions"]:
            for p in q["pointers"]:
                assert resolves(bp, p), (q["id"], p)
            for p in q.get("createsAt", []):
                assert not resolves(bp, p), (q["id"], p, "already exists, move it to pointers")
                assert resolves(bp, p.rsplit("/", 1)[0]), (q["id"], p, "parent missing")


def test_answer_keys_in_questions_are_exactly_the_instantiate_keys():
    from instantiate import ANSWER_KEYS
    doc = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    keys = {k for s in doc["sections"] for q in s["questions"] for k in q.get("answerKeys", [])}
    assert keys == ANSWER_KEYS


def test_select_options_in_questions_cover_their_defaults():
    doc = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    for s in doc["sections"]:
        for q in s["questions"]:
            d = q["defaultIfUnknown"]["value"]
            if q["type"] == "choice" and d not in (None, "country_pack"):
                assert d in [o["value"] for o in q["options"]], q["id"]


def test_only_known_warnings_remain():
    for c in ("sa", "ae", "eg"):
        rep = validate(instantiate(TEMPLATE, ANSWERS[c]), ctx())
        # metrics are not checked (no metric registry yet); the platform colour is auto-adjusted in dark theme
        assert {w.code for w in rep.warnings} <= {"BP-REF-002", "BP-BRAND-002"}, [str(w) for w in rep.warnings]


def test_qa_has_no_vat_or_einvoicing_assumption():
    bp = instantiate(TEMPLATE, ANSWERS["qa"])
    assert bp["compliance"]["eInvoicing"] == {"mode": "none"}
    assert bp["compliance"]["vat"] == {"registered": False}
    assert "BP-EINV-001" not in {e.code for e in validate(bp, ctx()).errors}
    with pytest.raises(InstantiationError):
        instantiate(TEMPLATE, {**ANSWERS["qa"], "vat_registered": True})
