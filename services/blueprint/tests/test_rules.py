"""At least one failing case per rule code: mutate a deep copy of the example, assert the code appears."""
import copy

import pytest

from fixture_registry import assets, load_example, registry
from test_example import full_ctx
from validator import validate


def m_unreachable(bp):
    w = bp["workflows"][0]
    w["states"].append({"id": "orphan", "kind": "final", "labels": {"ar": "x", "en": "x"}})


def m_dead_end(bp):
    w = bp["workflows"][0]
    w["states"].append({"id": "stuck", "kind": "normal", "labels": {"ar": "x", "en": "x"}})
    w["transitions"].append({"id": "to_stuck", "from": "draft", "to": "stuck", "actionLabels": {"ar": "x", "en": "x"}, "allowedRoles": ["owner"]})


def m_out_of_final(bp):
    bp["workflows"][0]["transitions"].append({"id": "reopen", "from": "delivered", "to": "draft", "actionLabels": {"ar": "x", "en": "x"}, "allowedRoles": ["owner"]})


def m_overlap(bp):
    bp["company"]["locale"]["workingTime"]["reducedPeriods"] = [
        {"id": "p1", "labels": {"ar": "x", "en": "x"}, "rule": "fixed_dates", "gregorianFrom": "2026-03-01", "gregorianTo": "2026-03-20", "hours": {"from": "09:00", "to": "14:00"}},
        {"id": "p2", "labels": {"ar": "x", "en": "x"}, "rule": "fixed_dates", "gregorianFrom": "2026-03-10", "gregorianTo": "2026-03-30", "hours": {"from": "09:00", "to": "14:00"}}]


def m_dup_option(bp):
    opts = bp["entities"][1]["fields"][2]["options"]
    opts.append(copy.deepcopy(opts[0]))


def m_selfapproval(bp):
    bp["approvals"][0]["selfApproval"] = True
    bp["roles"][0]["permissions"][2]["actions"].remove("approve")


def m_extra_component(bp):
    bp["components"].append({"id": "core.ghost", "versionRange": "^1.0.0"})


def reg_requires_missing():
    r = registry()
    r["core.sales_order"][0]["requires"].append({"component": "core.absent", "versionRange": "^1.0.0"})
    return r


def reg_wrong_adapter():
    r = registry()
    r["core.item"][0]["engineCompatibility"]["adapter"] = "other"
    for m in r["core.item"]:
        m["engineCompatibility"]["adapter"] = "other"
    return r


def set_(path, value):
    def f(bp):
        node = bp
        for p in path[:-1]:
            node = node[p]
        node[path[-1]] = value
    return f


def drop(path):
    def f(bp):
        node = bp
        for p in path[:-1]:
            node = node[p]
        del node[path[-1]]
    return f


# (expected code, mutation, ctx kwargs, severity bucket)
CASES = [
    ("BP-SCHEMA-001", set_(["meta", "revision"], 0), {}, "errors"),
    ("BP-LOC-001", set_(["company", "locale", "week", "weekendDays"], ["fri", "thu"]), {}, "errors"),
    ("BP-LOC-002", set_(["company", "locale", "workingTime", "reducedPeriods", 0, "rule"], "fixed_dates"), {}, "errors"),
    ("BP-LOC-003", set_(["company", "locale", "workingTime", "hours", "to"], "07:00"), {}, "errors"),
    ("BP-LOC-004", m_overlap, {}, "errors"),
    ("BP-CTRY-001", set_(["compliance", "country"], "AE"), {}, "errors"),
    ("BP-CTRY-002", set_(["compliance", "countryPack", "id"], "ae"), {}, "errors"),
    ("BP-CTRY-003", set_(["company", "locale", "holidays", "calendarRef", "id"], "ae.holidays"), {}, "errors"),
    ("BP-ID-001", lambda bp: bp["roles"].append(copy.deepcopy(bp["roles"][1])), {}, "errors"),
    ("BP-ID-001", m_dup_option, {}, "errors"),
    ("BP-REF-001", set_(["entities", 2, "workflow"], "nope"), {}, "errors"),
    ("BP-REF-001", set_(["roles", 1, "permissions", 0, "hiddenFields", 0], "no_such_field"), {}, "errors"),
    ("BP-REF-001", set_(["workflows", 0, "transitions", 0, "guards", 0, "field"], "lines.nope"), {}, "errors"),
    ("BP-REF-001", set_(["entities", 2, "fields", 4, "computed", "inputs"], ["ghost"]), {}, "errors"),
    ("BP-REF-001", set_(["integrations", 0, "mappings", 0, "target"], "customer.ghost"), {}, "errors"),
    ("BP-REF-001", set_(["reports", 0, "metrics", 2, "groupBy"], ["ghost"]), {}, "errors"),
    ("BP-REF-001", set_(["entities", 0, "components", 0, "component"], "core.unlisted"), {}, "errors"),
    ("BP-REF-002", lambda bp: None, {"metrics": None, "connectors": None}, "warnings"),
    ("BP-REF-003", set_(["reports", 0, "metrics", 0, "ref"], "sales.unknown"), {}, "errors"),
    ("BP-REF-003", set_(["integrations", 0, "connector"], "file.unknown"), {}, "errors"),
    ("BP-I18N-001", set_(["meta", "locales"], ["ar", "en", "fr"]), {}, "errors"),
    ("BP-I18N-002", set_(["meta", "defaultLocale"], "fr"), {}, "errors"),
    ("BP-I18N-002", set_(["i18n", "defaultLocale"], "fr"), {}, "errors"),
    ("BP-I18N-003", set_(["company", "languages", "secondary"], ["fr"]), {}, "errors"),
    ("BP-WF-001", set_(["workflows", 0, "states", 0, "kind"], "normal"), {}, "errors"),
    ("BP-WF-002", lambda bp: [s.update(kind="normal") for s in bp["workflows"][0]["states"][3:]], {}, "errors"),
    ("BP-WF-003", m_unreachable, {}, "errors"),
    ("BP-WF-004", m_dead_end, {}, "errors"),
    ("BP-WF-005", m_out_of_final, {}, "warnings"),
    ("BP-APR-002", set_(["approvals", 0, "steps", 0, "order"], 2), {}, "errors"),
    ("BP-APR-003", m_selfapproval, {}, "errors"),
    ("BP-ROLE-001", set_(["roles", 2, "scope", "values"], ["hq_riyadh"]), {}, "errors"),
    ("BP-ROLE-001", set_(["roles", 2, "scope", "values"], ["nowhere"]), {}, "errors"),
    ("BP-ROLE-002", set_(["roles", 0, "isAdmin"], False), {}, "errors"),
    ("BP-ROLE-003", set_(["roles", 0, "function"], "general_manager"), {}, "warnings"),
    ("BP-CMP-001", m_extra_component, {}, "errors"),
    ("BP-CMP-002", set_(["components", 0, "versionRange"], "^9.0.0"), {}, "errors"),
    ("BP-CMP-003", lambda bp: None, {"registry": reg_requires_missing()}, "errors"),
    ("BP-CMP-004", lambda bp: None, {"registry": reg_wrong_adapter()}, "errors"),
    ("BP-CMP-004", set_(["meta", "engineTarget", "versionSet"], "set-other"), {}, "errors"),
    ("BP-CMP-005", lambda bp: None, {"registry": None}, "warnings"),
    ("BP-CMP-006", drop(["meta", "engineTarget"]), {}, "warnings"),
    ("BP-CMP-007", set_(["components", 0, "versionRange"], "banana"), {}, "errors"),
    ("BP-FN-001", set_(["entities", 2, "fields", 3, "computed", "function"], "core.sales.unknown"), {}, "errors"),
    ("BP-FN-002", lambda bp: None, {"registry": None}, "warnings"),
    ("BP-BRAND-001", set_(["branding", "primaryColour"], "#FFFFFF"), {}, "errors"),
    ("BP-BRAND-002", set_(["branding", "primaryColour"], "#FFFF00"), {}, "warnings"),
    ("BP-ASSET-001", set_(["branding", "logo", "onLight", "bytes"], 999), {}, "errors"),
    ("BP-ASSET-002", lambda bp: None, {"assets": {}}, "errors"),
    ("BP-ASSET-003", lambda bp: None, {"assets": None}, "warnings"),
    ("BP-WL-001", set_(["branding", "poweredBy", "show"], False), {}, "errors"),
    ("BP-EINV-001", set_(["compliance", "documentLanguages"], ["en"]), {}, "errors"),
    ("BP-EINV-002", drop(["company", "vatNumber"]), {}, "errors"),
]


@pytest.mark.parametrize("code,mutate,ctx_kw,bucket", CASES, ids=[f"{c[0]}-{i}" for i, c in enumerate(CASES)])
def test_rule_fires(code, mutate, ctx_kw, bucket):
    bp = load_example()
    mutate(bp)
    rep = validate(bp, full_ctx(**ctx_kw))
    assert code in {i.code for i in getattr(rep, bucket)}, [str(i) for i in rep.errors + rep.warnings]
    if bucket == "warnings":
        assert not [e for e in rep.errors if e.code == code]


def test_white_label_allowed_with_entitlement():
    bp = load_example()
    bp["branding"]["poweredBy"]["show"] = False
    assert validate(bp, full_ctx(entitlements={"white_label"})).ok
    assert "BP-WL-001" in {e.code for e in validate(bp).errors}  # no ctx: fail closed


def test_self_approval_allowed_when_owner_holds_approve():
    bp = load_example()
    bp["approvals"][0]["selfApproval"] = True
    assert validate(bp, full_ctx()).ok


def test_non_sa_country_skips_einvoicing_rule():
    bp = load_example()
    bp["company"]["country"] = bp["compliance"]["country"] = "AE"
    bp["compliance"]["countryPack"]["id"] = "ae"
    bp["company"]["locale"]["holidays"]["calendarRef"]["id"] = "ae.holidays"
    del bp["company"]["vatNumber"]
    bp["compliance"]["documentLanguages"] = ["en", "ar"]
    codes = {e.code for e in validate(bp, full_ctx()).errors}
    assert "BP-EINV-001" not in codes and "BP-EINV-002" not in codes


def test_resolve_locale_fills_defaults_and_checks_them():
    from validator import resolve_locale, DEFAULT_PACK_LOCALES
    bp = load_example()
    del bp["company"]["locale"]
    loc = resolve_locale(bp)
    assert loc["workingTime"]["workDays"] == DEFAULT_PACK_LOCALES["sa"]["workingTime"]["workDays"]
    assert set(DEFAULT_PACK_LOCALES) == {"sa", "ae", "eg"}
    # explicit weekend that collides with the defaulted work days is caught
    bp["company"]["locale"] = {"week": {"weekendDays": ["sun"]}}
    assert "BP-LOC-001" in {e.code for e in validate(bp, full_ctx()).errors}


def test_localized_text_found_in_every_position():
    bp = load_example()
    bp["meta"]["locales"] = ["ar", "en", "fr"]
    paths = {e.path for e in validate(bp, full_ctx()).errors if e.code == "BP-I18N-001"}
    for p in ("/company/legalName", "/locations/0/labels", "/entities/2/fields/0/labels",
              "/entities/1/fields/2/options/0/labels", "/workflows/0/transitions/0/actionLabels",
              "/i18n/labelOverrides/sales_order.title", "/i18n/glossary/0/translations",
              "/branding/documentHeader/footerText", "/company/locale/workingTime/reducedPeriods/0/labels"):
        assert p in paths, p
