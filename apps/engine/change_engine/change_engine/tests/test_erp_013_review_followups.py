"""PR #202 review follow-up regressions: name-key twins and IMP-AUTH failure logging (ERP-013, Tier 3)."""
import json

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
