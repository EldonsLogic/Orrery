"""PR #245 review round-2 regressions: apply() binding order & NFC name keys (ERP-013, Tier 3)."""
import unicodedata
from unittest.mock import patch

import pytest

from change_engine.importer import ImportFailure, OpeningImporter
from change_engine.importer import engine as engine_mod
from change_engine.tests.test_erp_013_opening_importer import apply, backend, batch, refuses
from change_engine.tests.test_erp_013_review_round4 import _near_duplicate_source
from services.discovery.prevalidate import prevalidate

# Vocalised Arabic "محمد" typed with shadda before fatha (non-NFC) vs NFC (fatha before shadda).
MUHAMMAD_NON_NFC = "\u0645\u062d\u0645\u0651\u064e\u062f"
MUHAMMAD_NFC = unicodedata.normalize("NFC", MUHAMMAD_NON_NFC)
assert MUHAMMAD_NON_NFC != MUHAMMAD_NFC

CAFE_NFC = "Caf\u00e9"
CAFE_NFD = "Cafe\u0301"
assert CAFE_NFC != CAFE_NFD and unicodedata.normalize("NFC", CAFE_NFD) == CAFE_NFC


def test_apply_missing_currency_oracle_returns_imp_auth_with_zero_backend_reads(backend):
    # tenant-b has NO configured company currency; mutated tenant must raise IMP-AUTH, not IMP-CURRENCY.
    assert backend.company_currency("tenant-b", "Synthetic Trading") is None
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

    with (
        patch.object(importer, "_authorize", side_effect=mutating_auth),
        patch.object(backend, "company_currency", wraps=backend.company_currency) as spy_ccy,
        patch.object(backend, "master", wraps=backend.master) as spy_master,
        patch.object(backend, "journal", wraps=backend.journal) as spy_journal,
        patch.object(backend, "claim_opening", wraps=backend.claim_opening) as spy_claim,
        patch.object(backend, "write", wraps=backend.write) as spy_write,
        pytest.raises(ImportFailure, match="IMP-AUTH"),
    ):
        importer.apply(source, confirmed_by="reviewer", plan_hash=preview["plan_hash"])

    assert (spy_ccy.call_count, spy_master.call_count, spy_journal.call_count,
            spy_claim.call_count, spy_write.call_count) == (0, 0, 0, 0, 0)
    assert backend.records("tenant-b", "Synthetic Trading") == []
    assert backend.failures("tenant-b") == []
    failure, = backend.failures("tenant-a")
    assert (failure["code"], failure["user_id"], failure["batch_id"], failure["plan_hash"]) == (
        "IMP-AUTH", "reviewer", "opening-1", preview["plan_hash"],
    )


def test_apply_mutated_tenant_during_bounded_with_missing_currency_returns_imp_auth(backend):
    assert backend.company_currency("tenant-b", "Synthetic Trading") is None
    importer, source = OpeningImporter(backend), batch()
    preview = importer.preview(source)
    assert preview["ok"]
    orig_bounded = engine_mod.bounded

    def mutating_bounded(payload, **kw):
        orig_bounded(payload, **kw)
        payload["tenant_id"] = "tenant-b"

    with (
        patch.object(engine_mod, "bounded", side_effect=mutating_bounded),
        patch.object(backend, "company_currency", wraps=backend.company_currency) as spy_ccy,
        patch.object(backend, "master", wraps=backend.master) as spy_master,
        patch.object(backend, "journal", wraps=backend.journal) as spy_journal,
        patch.object(backend, "claim_opening", wraps=backend.claim_opening) as spy_claim,
        patch.object(backend, "write", wraps=backend.write) as spy_write,
        pytest.raises(ImportFailure, match="IMP-AUTH"),
    ):
        importer.apply(source, confirmed_by="reviewer", plan_hash=preview["plan_hash"])

    assert (spy_ccy.call_count, spy_master.call_count, spy_journal.call_count,
            spy_claim.call_count, spy_write.call_count) == (0, 0, 0, 0, 0)
    assert backend.failures("tenant-b") == []
    failure, = backend.failures("tenant-a")
    assert (failure["code"], failure["user_id"], failure["batch_id"], failure["plan_hash"]) == (
        "IMP-AUTH", "reviewer", "opening-1", preview["plan_hash"],
    )


def test_confirm_preview_validate_missing_currency_oracle_zero_backend_reads(backend):
    assert backend.company_currency("tenant-b", "Synthetic Trading") is None
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
            patch.object(backend, "journal", wraps=backend.journal) as spy_journal,
        ):
            res = getattr(importer, method)(source)
        assert res["ok"] is False and [e["code"] for e in res["errors"]] == ["IMP-AUTH"]
        assert (spy_ccy.call_count, spy_master.call_count, spy_journal.call_count) == (0, 0, 0)

    confirm_src = _near_duplicate_source()
    pending = importer.preview(confirm_src)
    assert pending["ok"] is False
    groups = [g["id"] for g in pending["name_groups"]]
    orig_auth, calls = importer._authorize, {"n": 0}

    def mutating_confirm_auth(payload, **kw):
        calls["n"] += 1
        ident = orig_auth(payload, **kw)
        if calls["n"] == 1:
            confirm_src["tenant_id"] = "tenant-b"
        return ident

    with (
        patch.object(importer, "_authorize", side_effect=mutating_confirm_auth),
        patch.object(backend, "company_currency", wraps=backend.company_currency) as spy_ccy,
        patch.object(backend, "master", wraps=backend.master) as spy_master,
        patch.object(backend, "journal", wraps=backend.journal) as spy_journal,
        patch.object(backend, "record_distinct_confirmation", wraps=backend.record_distinct_confirmation) as spy_rec,
        pytest.raises(ImportFailure, match="IMP-AUTH"),
    ):
        importer.confirm(confirm_src, confirmed_by="reviewer", owner_confirmed_distinct=groups, plan_hash=pending["plan_hash"])
    assert (spy_ccy.call_count, spy_master.call_count, spy_journal.call_count, spy_rec.call_count) == (0, 0, 0, 0)
    assert backend.failures("tenant-b") == []
    failure, = backend.failures("tenant-a")
    assert (failure["code"], failure["user_id"], failure["batch_id"], failure["plan_hash"]) == (
        "IMP-AUTH", "reviewer", "opening-1", pending["plan_hash"],
    )


def test_vocalised_arabic_non_nfc_accepted_and_stored_byte_identical(backend):
    importer = OpeningImporter(backend)
    datasets = {
        "Customer": [{"customer_name": MUHAMMAD_NON_NFC}],
        "Account": [{"account_name": MUHAMMAD_NON_NFC, "account_type": "Other"}],
        "Supplier": [{"supplier_name": MUHAMMAD_NON_NFC}],
        "Item": [{"item_code": "I-AR", "item_name": MUHAMMAD_NON_NFC}],
    }
    assert apply(importer, batch(datasets, batch_id="ar-non-nfc"))["status"] == "applied"
    stored = {r["entity"]: r for r in backend.records("tenant-a", "Synthetic Trading")}
    for entity, field in (
        ("Customer", "customer_name"),
        ("Account", "account_name"),
        ("Supplier", "supplier_name"),
        ("Item", "item_name"),
    ):
        saved = stored[entity]["row"][field]
        assert saved == MUHAMMAD_NON_NFC
        assert saved.encode("utf-8") == MUHAMMAD_NON_NFC.encode("utf-8")
        assert saved != MUHAMMAD_NFC


def test_vocalised_arabic_nfc_twin_in_same_batch_refused_as_imp_duplicate(backend):
    importer = OpeningImporter(backend)
    # Default report (Account + Customer).
    refuses(importer, batch({"Account": [
        {"account_name": MUHAMMAD_NON_NFC, "account_type": "Other"},
        {"account_name": MUHAMMAD_NFC, "account_type": "Other"},
    ]}, batch_id="dup-acct"), "IMP-DUPLICATE")
    refuses(importer, batch({"Customer": [
        {"customer_name": MUHAMMAD_NON_NFC},
        {"customer_name": MUHAMMAD_NFC},
    ]}, batch_id="dup-cust"), "IMP-DUPLICATE")
    # Also with a DSC-019 party-mapped report that emits PRE-801.
    rows = [{"customer_name": MUHAMMAD_NON_NFC}, {"customer_name": MUHAMMAD_NFC}]
    mapped_report = prevalidate(rows, {"required": {"*": []}, "fields": {"party": "customer_name"}}).to_dict()
    refuses(importer, batch({"Customer": rows}, batch_id="dup-cust-mapped", prevalidation=mapped_report), "IMP-DUPLICATE")
    assert backend.records("tenant-a", "Synthetic Trading") == []


def test_stored_nfc_arabic_refuses_incoming_non_nfc_twin_as_imp_duplicate(backend):
    importer = OpeningImporter(backend)
    apply(importer, batch({"Customer": [{"customer_name": MUHAMMAD_NFC}]}, batch_id="seed-nfc"))
    before = backend.records("tenant-a", "Synthetic Trading")
    refuses(importer, batch({"Customer": [{"customer_name": MUHAMMAD_NON_NFC}]}, batch_id="twin-non-nfc"), "IMP-DUPLICATE")
    assert backend.records("tenant-a", "Synthetic Trading") == before
    # Exact same NFC spelling still allows updating non-key fields.
    assert apply(importer, batch(
        {"Customer": [{"customer_name": MUHAMMAD_NFC, "tax_id": "300000000000003"}]},
        batch_id="update-exact",
    ))["status"] == "applied"
    saved = backend.records("tenant-a", "Synthetic Trading")[0]["row"]
    assert saved["customer_name"] == MUHAMMAD_NFC and saved["tax_id"] == "300000000000003"


def test_stored_non_nfc_arabic_refuses_incoming_nfc_twin_as_imp_duplicate(backend):
    importer = OpeningImporter(backend)
    apply(importer, batch({"Account": [{"account_name": MUHAMMAD_NON_NFC, "account_type": "Other"}]}, batch_id="seed-non-nfc"))
    before = backend.records("tenant-a", "Synthetic Trading")
    refuses(
        importer,
        batch({"Account": [{"account_name": MUHAMMAD_NFC, "account_type": "Other"}]}, batch_id="twin-nfc"),
        "IMP-DUPLICATE",
    )
    assert backend.records("tenant-a", "Synthetic Trading") == before


def test_cafe_nfd_lone_accepted_verbatim_and_nfd_vs_nfc_refused_as_imp_duplicate(backend):
    importer = OpeningImporter(backend)
    # Within one batch: NFD next to NFC gives IMP-DUPLICATE.
    refuses(importer, batch({"Customer": [
        {"customer_name": CAFE_NFD},
        {"customer_name": CAFE_NFC},
    ]}, batch_id="cafe-batch-dup"), "IMP-DUPLICATE")
    # Lone NFD Café is accepted and stored byte-identical as typed.
    assert apply(importer, batch({"Customer": [{"customer_name": CAFE_NFD}]}, batch_id="cafe-nfd-lone"))["status"] == "applied"
    before = backend.records("tenant-a", "Synthetic Trading")
    assert len(before) == 1
    saved = before[0]["row"]["customer_name"]
    assert saved == CAFE_NFD and saved.encode("utf-8") == CAFE_NFD.encode("utf-8")
    # Incoming NFC twin against stored NFD master gives IMP-DUPLICATE.
    refuses(importer, batch({"Customer": [{"customer_name": CAFE_NFC}]}, batch_id="cafe-stored-dup"), "IMP-DUPLICATE")
    assert backend.records("tenant-a", "Synthetic Trading") == before
    # Non-NFC + safe mark twin also collides as IMP-DUPLICATE.
    refuses(importer, batch({"Account": [
        {"account_name": CAFE_NFC, "account_type": "Other"},
        {"account_name": f"{CAFE_NFD}\u200f", "account_type": "Other"},
    ]}, batch_id="cafe-mark-dup"), "IMP-DUPLICATE")


def test_combining_hamza_madda_and_vocalised_tanween_kasra_accepted_verbatim(backend):
    importer = OpeningImporter(backend)
    hamza_above = "\u0627\u0654\u062d\u0645\u062f"       # ا + combining hamza above + حمد
    hamza_below = "\u0627\u0655\u0628\u0631\u0627\u0647\u064a\u0645"  # ا + combining hamza below + براهيم
    madda = "\u0627\u0653\u0645\u0646\u0629"              # ا + combining madda above + منة
    tanween_kasra = "\u0645\u064f\u062d\u064e\u0645\u0651\u064e\u062f\u064d \u0643\u064e\u0631\u0650\u064a\u0645\u064b\u0627"
    vocalised_shadda_kasra = "\u0634\u064e\u0631\u0650\u0643\u064e\u0629\u064f \u0627\u0644\u0646\u0651\u0650\u064a\u0644\u0650"
    rows = [
        {"customer_code": "C-H1", "customer_name": hamza_above},
        {"customer_code": "C-H2", "customer_name": hamza_below},
        {"customer_code": "C-M1", "customer_name": madda},
        {"customer_code": "C-TK", "customer_name": tanween_kasra},
        {"customer_code": "C-SK", "customer_name": vocalised_shadda_kasra},
    ]
    assert apply(importer, batch({"Customer": rows}, batch_id="ar-vocalised"))["status"] == "applied"
    stored = {r["row"]["customer_code"]: r["row"]["customer_name"] for r in backend.records("tenant-a", "Synthetic Trading")}
    for row in rows:
        saved = stored[row["customer_code"]]
        assert saved == row["customer_name"]
        assert saved.encode("utf-8") == row["customer_name"].encode("utf-8")
    # Combining hamza / madda next to precomposed NFC twin gives IMP-DUPLICATE on name-keyed records.
    refuses(importer, batch({"Account": [
        {"account_name": hamza_above, "account_type": "Other"},
        {"account_name": unicodedata.normalize("NFC", hamza_above), "account_type": "Other"},
    ]}, batch_id="hamza-dup"), "IMP-DUPLICATE")
    refuses(importer, batch({"Account": [
        {"account_name": madda, "account_type": "Other"},
        {"account_name": unicodedata.normalize("NFC", madda), "account_type": "Other"},
    ]}, batch_id="madda-dup"), "IMP-DUPLICATE")


def test_nfkc_not_applied_to_names(backend):
    importer = OpeningImporter(backend)
    datasets = {"Account": [
        {"account_name": "Cash", "account_type": "Other"},
        {"account_name": "\uff23\uff41\uff53\uff48", "account_type": "Other"},
    ]}
    assert apply(importer, batch(datasets, batch_id="nfkc-names"))["status"] == "applied"
    names = {r["row"]["account_name"] for r in backend.records("tenant-a", "Synthetic Trading")}
    assert names == {"Cash", "\uff23\uff41\uff53\uff48"}
