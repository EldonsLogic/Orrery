"""PR #202 review follow-up regressions: name-key twins and IMP-AUTH failure logging (ERP-013, Tier 3)."""
from contextlib import ExitStack
import json
from unittest.mock import patch

import pytest

from change_engine.importer import ImportFailure, OpeningImporter
from change_engine.tests.test_erp_013_opening_importer import apply, backend, batch, refuses
from change_engine.tests.test_erp_013_review_round4 import _near_duplicate_source


NAME_TWIN_SUFFIXES = (
    ("trailing_space", " "),
    ("nbsp", "\u00a0"),
    ("em_space", "\u2003"),
    ("hangul_filler", "\u3164"),
    ("cgj", "\u034f"),
    ("vs16", "\ufe0f"),
    ("mark_masked_trailing_space", " \u200f"),
)


def _name_twin(base: str, kind: str) -> str:
    if kind == "leading_space":
        return f" {base}"
    if kind == "mark_masked_leading_space":
        return f"\u200f {base}"
    if kind == "internal_nbsp":
        return base.replace(" ", "\u00a0", 1) if " " in base else f"{base[:2]}\u00a0{base[2:]}"
    if kind == "double_space":
        return base.replace(" ", "  ", 1) if " " in base else f"{base[:2]}  {base[2:]}"
    if kind == "mark_masked_double_space":
        return base.replace(" ", " \u200f ", 1) if " " in base else f"{base[:2]} \u200f {base[2:]}"
    return base + dict(NAME_TWIN_SUFFIXES)[kind]


ALL_NAME_TWIN_KINDS = (
    "trailing_space",
    "leading_space",
    "nbsp",
    "internal_nbsp",
    "em_space",
    "hangul_filler",
    "cgj",
    "vs16",
    "double_space",
    "mark_masked_leading_space",
    "mark_masked_trailing_space",
    "mark_masked_double_space",
)


@pytest.mark.parametrize("kind", ALL_NAME_TWIN_KINDS)
def test_account_name_refuses_twins_within_one_batch(backend, kind):
    importer = OpeningImporter(backend)
    base = "Cash Box" if "double" in kind or kind == "internal_nbsp" else "Cash"
    twin = _name_twin(base, kind)
    datasets = {
        "Account": [
            {"account_name": base, "account_type": "Other"},
            {"account_name": twin, "account_type": "Other"},
        ],
    }
    refuses(importer, batch(datasets), "IMP-SCHEMA")
    assert backend.records("tenant-a", "Synthetic Trading") == []


@pytest.mark.parametrize("kind", ALL_NAME_TWIN_KINDS)
def test_customer_name_refuses_twins_within_one_batch(backend, kind):
    importer = OpeningImporter(backend)
    twin = _name_twin("Alpha Trading", kind)
    datasets = {
        "Customer": [
            {"customer_name": "Alpha Trading"},
            {"customer_name": twin},
        ],
    }
    refuses(importer, batch(datasets), "IMP-SCHEMA")
    assert backend.records("tenant-a", "Synthetic Trading") == []


@pytest.mark.parametrize("kind", ALL_NAME_TWIN_KINDS)
def test_stored_customer_master_refuses_name_twins_in_later_batch(backend, kind):
    importer = OpeningImporter(backend)
    apply(importer, batch({"Customer": [{"customer_name": "Alpha Trading"}]}, batch_id="seed-cust"))
    before = backend.records("tenant-a", "Synthetic Trading")
    twin = _name_twin("Alpha Trading", kind)
    refuses(importer, batch({"Customer": [{"customer_name": twin}]}, batch_id="twin-cust"), "IMP-SCHEMA")
    assert backend.records("tenant-a", "Synthetic Trading") == before


@pytest.mark.parametrize("kind", ("trailing_space", "nbsp", "hangul_filler", "double_space"))
def test_stored_account_master_refuses_name_twins_in_later_batch(backend, kind):
    importer = OpeningImporter(backend)
    apply(importer, batch(
        {"Account": [{"account_name": "Cash Box", "account_type": "Other"}]},
        batch_id="seed-acct",
    ))
    before = backend.records("tenant-a", "Synthetic Trading")
    twin = _name_twin("Cash Box", kind)
    refuses(
        importer,
        batch({"Account": [{"account_name": twin, "account_type": "Other"}]}, batch_id="twin-acct"),
        "IMP-SCHEMA",
    )
    assert backend.records("tenant-a", "Synthetic Trading") == before


@pytest.mark.parametrize("entity,row_base,field,base", [
    ("Customer", {"customer_code": "C1"}, "customer_type", "Company Group"),
    ("Supplier", {}, "supplier_name", "Gulf Supply"),
    ("Supplier", {"supplier_code": "S1"}, "supplier_type", "Local Vendor"),
    ("Item", {"item_code": "I1"}, "item_name", "Widget Pro"),
])
@pytest.mark.parametrize("kind", ("trailing_space", "leading_space", "nbsp", "hangul_filler", "cgj", "double_space"))
def test_all_name_text_fields_refuse_twins(backend, entity, row_base, field, base, kind):
    importer = OpeningImporter(backend)
    row = dict(row_base, **{field: _name_twin(base, kind)})
    refuses(importer, batch({entity: [row]}), "IMP-SCHEMA")
    assert backend.records("tenant-a", "Synthetic Trading") == []


@pytest.mark.parametrize("mark", ["\u200c", "\u200d", "\u200e", "\u200f", "\u061c"])
def test_arabic_names_with_safe_marks_and_single_inner_spaces_pass(backend, mark):
    importer = OpeningImporter(backend)
    acct_ar = f"{mark}الصندوق الرئيسي"
    cust_ar = f"شركة{mark} النور للتجارة"
    supp_en = "Gulf Trading Partners"
    item_ar = f"صنف{mark} قياسي ممتاز"
    datasets = {
        "Account": [
            {"account_name": acct_ar, "account_type": "Other"},
            {"account_name": "Petty Cash Account", "account_type": "Other"},
        ],
        "Customer": [{"customer_name": cust_ar, "customer_type": "Company Account"}],
        "Supplier": [{"supplier_name": supp_en, "supplier_type": "Local Supplier"}],
        "Item": [{"item_code": "SKU-1", "item_name": item_ar}],
    }
    assert apply(importer, batch(datasets))["status"] == "applied"
    stored = {(r["entity"], r["key"]): r["row"] for r in backend.records("tenant-a", "Synthetic Trading")}
    assert stored[("Account", '["account_name","الصندوق الرئيسي"]')]["account_name"] == acct_ar
    assert stored[("Account", '["account_name","Petty Cash Account"]')]["account_name"] == "Petty Cash Account"
    assert stored[("Customer", '["customer_name","شركة النور للتجارة"]')]["customer_name"] == cust_ar
    assert stored[("Supplier", '["supplier_name","Gulf Trading Partners"]')]["supplier_name"] == supp_en
    assert stored[("Item", '["item_code","SKU-1"]')]["item_name"] == item_ar
    # Two name-fallback keys differing only by a safe Arabic mark still collide as IMP-DUPLICATE.
    refuses(importer, batch({
        "Account": [
            {"account_name": "النقدية بالصندوق", "account_type": "Other"},
            {"account_name": f"{mark}النقدية بالصندوق", "account_type": "Other"},
        ],
    }, batch_id="dup-mark"), "IMP-DUPLICATE")


def test_apply_mid_call_auth_revocation_logs_imp_auth_without_secrets(backend, monkeypatch):
    importer = OpeningImporter(backend)
    source = batch()
    preview = importer.preview(source)
    assert preview["ok"]
    calls = {"n": 0}
    base_session = backend.identity()

    def revoking_session():
        calls["n"] += 1
        if calls["n"] == 1:
            return dict(base_session, api_secret="super-secret-token", roles=["Accounts Manager"])
        return dict(base_session, capabilities=[], api_secret="super-secret-token", roles=["CallerSuppliedAdmin"])

    monkeypatch.setattr(backend, "_session", revoking_session)
    with pytest.raises(ImportFailure, match="IMP-AUTH"):
        importer.apply(source, confirmed_by="reviewer", plan_hash=preview["plan_hash"])
    assert backend.records("tenant-a", "Synthetic Trading") == []
    failure, = backend.failures("tenant-a")
    assert (failure["code"], failure["user_id"], failure["batch_id"], failure["plan_hash"]) == (
        "IMP-AUTH", "reviewer", "opening-1", preview["plan_hash"],
    )
    serialized = json.dumps(failure)
    assert "super-secret-token" not in serialized
    assert "Accounts Manager" not in serialized
    assert "CallerSuppliedAdmin" not in serialized


def test_apply_backend_imp_auth_rolls_back_and_logs_failure(backend, monkeypatch):
    importer = OpeningImporter(backend)
    source = batch()
    preview = importer.preview(source)
    assert preview["ok"]
    original_write = backend.write
    written = {"n": 0}

    def auth_failing_write(*args):
        original_write(*args)
        written["n"] += 1
        if written["n"] == 2:
            raise ImportFailure("IMP-AUTH")

    monkeypatch.setattr(backend, "write", auth_failing_write)
    with pytest.raises(ImportFailure, match="IMP-AUTH"):
        importer.apply(source, confirmed_by="reviewer", plan_hash=preview["plan_hash"])
    assert backend.records("tenant-a", "Synthetic Trading") == []
    failure, = backend.failures("tenant-a")
    assert (failure["code"], failure["user_id"], failure["batch_id"], failure["plan_hash"]) == (
        "IMP-AUTH", "reviewer", "opening-1", preview["plan_hash"],
    )


def test_confirm_mid_call_auth_revocation_and_backend_imp_auth_are_logged(backend, monkeypatch):
    importer = OpeningImporter(backend)
    source = _near_duplicate_source()
    pending = importer.preview(source)
    assert pending["ok"] is False
    groups = [g["id"] for g in pending["name_groups"]]
    base_session = backend.identity()

    # 1. Mid-call revocation between initial _authorize and post-deepcopy _authorize in confirm().
    calls = {"n": 0}

    def revoking_session():
        calls["n"] += 1
        if calls["n"] == 1:
            return dict(base_session, api_secret="confirm-secret", roles=["Accounts Manager"])
        return dict(base_session, capabilities=["opening_import"], api_secret="confirm-secret", roles=["Guest"])

    monkeypatch.setattr(backend, "_session", revoking_session)
    with pytest.raises(ImportFailure, match="IMP-AUTH"):
        importer.confirm(
            source, confirmed_by="reviewer", owner_confirmed_distinct=groups, plan_hash=pending["plan_hash"],
        )

    # 2. Backend raises IMP-AUTH during record_distinct_confirmation inside transaction.
    monkeypatch.setattr(backend, "_session", lambda: dict(base_session))

    def auth_failing_record(*args, **kwargs):
        raise ImportFailure("IMP-AUTH")

    monkeypatch.setattr(backend, "record_distinct_confirmation", auth_failing_record)
    with pytest.raises(ImportFailure, match="IMP-AUTH"):
        importer.confirm(
            source, confirmed_by="reviewer", owner_confirmed_distinct=groups, plan_hash=pending["plan_hash"],
        )

    failures = backend.failures("tenant-a")
    assert [(f["code"], f["user_id"], f["batch_id"], f["plan_hash"]) for f in failures] == [
        ("IMP-AUTH", "reviewer", "opening-1", pending["plan_hash"]),
        ("IMP-AUTH", "reviewer", "opening-1", pending["plan_hash"]),
    ]
    serialized = json.dumps(failures)
    assert "confirm-secret" not in serialized
    assert "Accounts Manager" not in serialized
    assert "Guest" not in serialized


def _spy_backend(store):
    stack = ExitStack()
    names = ("company_currency", "master", "journal", "claim_opening", "write")
    spies = {name: stack.enter_context(patch.object(store, name, wraps=getattr(store, name))) for name in names}
    return stack, spies


def test_apply_mutated_tenant_left_changed_logs_only_to_authenticated_tenant(backend):
    backend.set_company_currency("tenant-b", "Synthetic Trading", "SAR")
    importer, source = OpeningImporter(backend), batch()
    preview = importer.preview(source)
    assert preview["ok"]
    orig_auth, calls = importer._authorize, {"n": 0}

    def mutating_auth(payload, **kw):
        calls["n"] += 1
        ident = orig_auth(payload, **kw)
        if calls["n"] == 1:
            source["tenant_id"] = "tenant-b"
        return ident

    stack, spies = _spy_backend(backend)
    with stack, patch.object(importer, "_authorize", side_effect=mutating_auth), pytest.raises(ImportFailure, match="IMP-AUTH"):
        importer.apply(source, confirmed_by="reviewer", plan_hash=preview["plan_hash"])
    assert all(s.call_count == 0 for s in spies.values())
    assert backend.records("tenant-b", "Synthetic Trading") == [] and backend.failures("tenant-b") == []
    assert backend.records("tenant-a", "Synthetic Trading") == []
    failure, = backend.failures("tenant-a")
    assert (failure["code"], failure["user_id"], failure["batch_id"], failure["plan_hash"]) == (
        "IMP-AUTH", "reviewer", "opening-1", preview["plan_hash"],
    )


def test_apply_mutated_tenant_flipped_back_before_deepcopy_never_touches_tenant_b(backend):
    from change_engine.importer import engine as engine_mod
    backend.set_company_currency("tenant-b", "Synthetic Trading", "SAR")
    importer, source = OpeningImporter(backend), batch()
    preview = importer.preview(source)
    assert preview["ok"]
    orig_bounded = engine_mod.bounded

    def flipping_bounded(payload, **kw):
        payload["tenant_id"] = "tenant-b"
        try:
            return orig_bounded(payload, **kw)
        finally:
            payload["tenant_id"] = "tenant-a"

    stack, spies = _spy_backend(backend)
    with stack, patch.object(engine_mod, "bounded", side_effect=flipping_bounded):
        res = importer.apply(source, confirmed_by="reviewer", plan_hash=preview["plan_hash"])
    assert res["status"] == "applied"
    for spy in spies.values():
        assert all("tenant-b" not in c.args and "tenant-b" not in c.kwargs.values() for c in spy.call_args_list)
    assert backend.records("tenant-b", "Synthetic Trading") == [] and backend.failures("tenant-b") == []


def test_apply_mutated_batch_id_or_switched_session_refuses_before_backend_reads(backend, monkeypatch):
    from change_engine.importer import engine as engine_mod
    backend.set_company_currency("tenant-b", "Synthetic Trading", "SAR")
    importer, source = OpeningImporter(backend), batch()
    preview = importer.preview(source)
    assert preview["ok"]
    orig_bounded = engine_mod.bounded

    def mutate_batch(payload, **kw):
        orig_bounded(payload, **kw)
        payload["batch_id"] = "opening-2"

    stack, spies = _spy_backend(backend)
    with stack, patch.object(engine_mod, "bounded", side_effect=mutate_batch), pytest.raises(ImportFailure, match="IMP-AUTH"):
        importer.apply(source, confirmed_by="reviewer", plan_hash=preview["plan_hash"])
    assert all(s.call_count == 0 for s in spies.values())

    source2 = batch(batch_id="opening-switch")
    preview2 = importer.preview(source2)
    assert preview2["ok"]
    base_session, scalls = backend.identity(), {"n": 0}

    def switching_session():
        scalls["n"] += 1
        return dict(base_session) if scalls["n"] == 1 else dict(base_session, tenant_id="tenant-b", user_id="other")

    def switch_tenant(payload, **kw):
        orig_bounded(payload, **kw)
        payload["tenant_id"] = "tenant-b"

    monkeypatch.setattr(backend, "_session", switching_session)
    stack2, spies2 = _spy_backend(backend)
    with stack2, patch.object(engine_mod, "bounded", side_effect=switch_tenant), pytest.raises(ImportFailure, match="IMP-AUTH"):
        importer.apply(source2, confirmed_by="reviewer", plan_hash=preview2["plan_hash"])
    assert all(s.call_count == 0 for s in spies2.values())
    assert backend.records("tenant-b", "Synthetic Trading") == [] and backend.failures("tenant-b") == []
    assert [(f["code"], f["user_id"], f["batch_id"]) for f in backend.failures("tenant-a")] == [
        ("IMP-AUTH", "reviewer", "opening-1"),
        ("IMP-AUTH", "reviewer", "opening-switch"),
    ]


def test_confirm_mutated_tenant_and_batch_id_refuse_and_log_authenticated_tenant_only(backend, monkeypatch):
    backend.set_company_currency("tenant-b", "Synthetic Trading", "SAR")
    importer, source = OpeningImporter(backend), _near_duplicate_source()
    pending = importer.preview(source)
    assert pending["ok"] is False
    groups, base_session = [g["id"] for g in pending["name_groups"]], backend.identity()
    scalls, acalls, orig_auth = {"n": 0}, {"n": 0}, importer._authorize

    def switching_session():
        scalls["n"] += 1
        return dict(base_session) if scalls["n"] == 1 else dict(base_session, tenant_id="tenant-b", user_id="other")

    def mutating_auth(payload, **kw):
        acalls["n"] += 1
        ident = orig_auth(payload, **kw)
        if acalls["n"] == 1:
            source["tenant_id"] = "tenant-b"
        return ident

    monkeypatch.setattr(backend, "_session", switching_session)
    with (
        patch.object(importer, "_authorize", side_effect=mutating_auth),
        patch.object(backend, "record_distinct_confirmation", wraps=backend.record_distinct_confirmation) as spy_rec,
        pytest.raises(ImportFailure, match="IMP-AUTH"),
    ):
        importer.confirm(source, confirmed_by="reviewer", owner_confirmed_distinct=groups, plan_hash=pending["plan_hash"])
    assert spy_rec.call_count == 0 and backend.failures("tenant-b") == []

    monkeypatch.setattr(backend, "_session", lambda: dict(base_session))
    source2 = _near_duplicate_source()
    from change_engine.importer import engine as engine_mod
    orig_bounded = engine_mod.bounded

    def mutating_batch_bounded(payload, **kw):
        orig_bounded(payload, **kw)
        payload["batch_id"] = "opening-mutated"

    with (
        patch.object(engine_mod, "bounded", side_effect=mutating_batch_bounded),
        patch.object(backend, "record_distinct_confirmation", wraps=backend.record_distinct_confirmation) as spy_rec2,
        pytest.raises(ImportFailure, match="IMP-AUTH"),
    ):
        importer.confirm(source2, confirmed_by="reviewer", owner_confirmed_distinct=groups, plan_hash=pending["plan_hash"])
    assert spy_rec2.call_count == 0
    assert [(f["code"], f["user_id"], f["batch_id"]) for f in backend.failures("tenant-a")] == [
        ("IMP-AUTH", "reviewer", "opening-1"),
        ("IMP-AUTH", "reviewer", "opening-1"),
    ]


def test_preview_and_validate_mutated_tenant_refuse_without_cross_tenant_read(backend):
    backend.set_company_currency("tenant-b", "Synthetic Trading", "SAR")
    importer = OpeningImporter(backend)
    for method in ("preview", "validate"):
        source, orig_auth, calls = batch(), importer._authorize, {"n": 0}

        def mutating_auth(payload, **kw):
            calls["n"] += 1
            ident = orig_auth(payload, **kw)
            if calls["n"] == 1:
                source["tenant_id"] = "tenant-b"
            return ident

        with (
            patch.object(importer, "_authorize", side_effect=mutating_auth),
            patch.object(backend, "company_currency", wraps=backend.company_currency) as spy_ccy,
            patch.object(backend, "master", wraps=backend.master) as spy_master,
        ):
            res = getattr(importer, method)(source)
        assert res["ok"] is False and [e["code"] for e in res["errors"]] == ["IMP-AUTH"]
        assert spy_ccy.call_count == 0 and spy_master.call_count == 0


def test_name_fields_refuse_nfc_twins_and_accept_common_arabic(backend):
    importer = OpeningImporter(backend)
    refuses(importer, batch({"Account": [
        {"account_name": "Caf\u00e9", "account_type": "Other"},
        {"account_name": "Cafe\u0301", "account_type": "Other"},
    ]}), "IMP-DUPLICATE")
    assert backend.records("tenant-a", "Synthetic Trading") == []

    arabic_customers = [
        {"customer_code": "C-CAFE", "customer_name": "Caf\u00e9"},
        {"customer_code": "C-AR1", "customer_name": "محمد"},
        {"customer_code": "C-AR2", "customer_name": "شركة الفجر"},
        {"customer_code": "C-AR3", "customer_name": "عبدالله"},
        {"customer_code": "C-AR4", "customer_name": "مؤسسة"},
        {"customer_code": "C-AR5", "customer_name": "إبراهيم"},
        {"customer_code": "C-AR6", "customer_name": "آل"},
        {"customer_code": "C-AR7", "customer_name": "شركـة النور"},
        {"customer_code": "C-AR8", "customer_name": "شركة\u200c\u200d\u200e\u200f\u061c الأمل"},
        {"customer_code": "C-FW", "customer_name": "Ｃａｓｈ"},
    ]
    assert apply(importer, batch({"Customer": arabic_customers}, batch_id="nfc-ok"))["status"] == "applied"
    stored = {r["row"]["customer_code"]: r["row"]["customer_name"] for r in backend.records("tenant-a", "Synthetic Trading")}
    for row in arabic_customers:
        assert stored[row["customer_code"]] == row["customer_name"]


@pytest.mark.parametrize("label,ch", [
    ("braille_blank", "\u2800"),
    ("ideographic_space", "\u3000"),
    ("hangul_choseong_filler", "\u115f"),
    ("hangul_jungseong_filler", "\u1160"),
    ("hangul_filler", "\u3164"),
])
def test_name_fields_refuse_blank_and_filler_twins(backend, label, ch):
    importer = OpeningImporter(backend)
    datasets = {"Account": [
        {"account_name": "Cash", "account_type": "Other"},
        {"account_name": f"Cash{ch}", "account_type": "Other"},
    ]}
    refuses(importer, batch(datasets, batch_id=f"blank-{label}"), "IMP-SCHEMA")
    assert backend.records("tenant-a", "Synthetic Trading") == []


@pytest.mark.parametrize("label,ch", [
    ("zwsp", "\u200b"),
    ("shy", "\u00ad"),
    ("wj", "\u2060"),
    ("bom", "\ufeff"),
    ("mvs", "\u180e"),
    ("tag_space", "\U000e0020"),
])
def test_name_fields_refuse_cf_default_ignorables_with_imp_formula(backend, label, ch):
    importer = OpeningImporter(backend)
    refuses(importer, batch({"Customer": [{"customer_name": f"Alpha{ch}Trading"}]}, batch_id=f"cf-{label}"), "IMP-FORMULA")
    assert backend.records("tenant-a", "Synthetic Trading") == []
