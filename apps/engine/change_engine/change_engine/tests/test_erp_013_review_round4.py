"""Round 4 PR #202 review regressions (ERP-013, Tier 3)."""
import copy
import sqlite3

import pytest

from services.discovery.prevalidate import prevalidate
from change_engine.importer import ImportFailure, OpeningImporter, SQLiteImportBackend
from change_engine.tests.test_erp_013_opening_importer import apply, backend, batch, refuses
from change_engine.tests.test_erp_013_review_fixes import opening_details


def test_offsetting_control_accounts_reject_dummy_zero_detail(backend):
    datasets = {
        "Account": [{"account_number": key, "account_type": "Receivable"} for key in ("1100", "1200")],
        "TrialBalance": [
            {"account": "1100", "account_type": "Receivable", "debit": "100.00", "credit": "0"},
            {"account": "1200", "account_type": "Receivable", "debit": "0", "credit": "100.00"},
        ],
        "Customer": [{"customer_code": "C1"}],
        "AR": [{"customer": "C1", "amount": "0"}],
    }
    importer = OpeningImporter(backend)
    refuses(importer, batch(datasets), "IMP-RECONCILE")
    datasets["AR"][0]["account"] = "1100"
    refuses(importer, batch(datasets), "IMP-RECONCILE")
    assert backend.records("tenant-a", "Synthetic Trading") == []


@pytest.mark.parametrize("entity,control", [("AR", "ar"), ("AP", "ap"), ("Stock", "stock")])
def test_single_control_persists_its_account_on_the_detail(backend, entity, control):
    apply(OpeningImporter(backend), batch(opening_details()))
    detail, = [r["row"] for r in backend.records("tenant-a", "Synthetic Trading") if r["entity"] == entity]
    assert detail["account"] == control


def test_per_account_reconciliation_and_account_link_validation(backend):
    datasets = {
        "Account": [{"account_number": "1100", "account_type": "Receivable"},
                    {"account_number": "1200", "account_type": "Receivable"},
                    {"account_number": "2100", "account_type": "Payable"},
                    {"account_number": "3000", "account_type": "Other"}],
        "TrialBalance": [
            {"account": "1100", "account_type": "Receivable", "debit": "40.00", "credit": "0"},
            {"account": "1200", "account_type": "Receivable", "debit": "60.00", "credit": "0"},
            {"account": "3000", "account_type": "Other", "debit": "0", "credit": "100.00"},
        ],
        "Customer": [{"customer_code": "C1"}, {"customer_code": "C2"}],
        "AR": [{"customer": "C1", "account": "1100", "amount": "40.00"},
               {"customer": "C2", "account": "1200", "amount": "60.00"}],
    }
    importer = OpeningImporter(backend)
    assert importer.preview(batch(datasets))["ok"]
    # Swapping amounts across the two Receivable accounts keeps aggregate total 100.00 but must fail per account.
    swapped = copy.deepcopy(datasets)
    swapped["AR"][0]["amount"], swapped["AR"][1]["amount"] = "60.00", "40.00"
    refuses(importer, batch(swapped), "IMP-RECONCILE")
    # Detail naming a wrong-type account fails IMP-REFERENCE; naming an account absent from TB fails IMP-RECONCILE.
    wrong_type = copy.deepcopy(datasets)
    wrong_type["AR"][0]["account"] = "2100"
    refuses(importer, batch(wrong_type), "IMP-REFERENCE")
    not_in_tb = copy.deepcopy(datasets)
    not_in_tb["Account"].append({"account_number": "1300", "account_type": "Receivable"})
    not_in_tb["Customer"].append({"customer_code": "C3"})
    not_in_tb["AR"].append({"customer": "C3", "account": "1300", "amount": "0"})
    refuses(importer, batch(not_in_tb), "IMP-RECONCILE")


def test_functional_currency_is_checked_and_preview_echoes_context(backend):
    importer = OpeningImporter(backend)
    refuses(importer, batch(currency="USD"), "IMP-CURRENCY")
    source = batch()
    preview = importer.preview(source)
    assert {key: preview[key] for key in ("company", "posting_date", "currency")} == {
        key: source[key] for key in ("company", "posting_date", "currency")}


def test_near_duplicate_names_require_a_bound_owner_confirmation(backend, monkeypatch):
    importer = OpeningImporter(backend)
    datasets = {
        "Item": [{"item_code": f"SKU-RED-{size}", "item_name": f"Blue Shirt {size}"} for size in ("M", "L")],
        "Customer": [{"customer_code": code, "customer_name": name}
                     for code, name in (("CUST-A", "محمد أحمد"), ("CUST-B", "أحمد محمد"))],
    }
    source = batch(datasets)
    # A genuine upstream report with a flagged name group must also be resolvable.
    source["prevalidation"] = prevalidate(datasets["Customer"] + datasets["Item"], {
        "required": {"*": []}, "fields": {"party": "customer_name", "item": "item_name"}}).to_dict()
    pending = importer.preview(source)
    assert pending["ok"] is False
    assert {group["entity"] for group in pending["name_groups"]} == {"Item", "Customer"}
    groups = [group["id"] for group in pending["name_groups"]]
    assert importer.preview(dict(source, owner_confirmed_distinct=groups))["errors"][0]["code"] == "IMP-SCHEMA"
    with pytest.raises(ImportFailure, match="IMP-REPORT"):
        importer.apply(source, confirmed_by="reviewer", plan_hash="0" * 64)
    identity = backend.identity()
    monkeypatch.setattr(backend, "_session", lambda: dict(identity, capabilities=["opening_import"]))
    with pytest.raises(ImportFailure, match="IMP-AUTH"):
        importer.confirm(source, confirmed_by="reviewer", owner_confirmed_distinct=groups,
                         plan_hash=pending["plan_hash"])
    monkeypatch.setattr(backend, "_session", lambda: identity)
    changes = copy.deepcopy(datasets)
    changes["Item"][0]["item_name"] = "Blue Shirts M"
    edited = batch(changes)
    for candidate, ids in ((source, groups[:1]), (source, [groups[0], "0" * 64]), (edited, groups)):
        with pytest.raises(ImportFailure, match="IMP-CONFIRM"):
            importer.confirm(candidate, confirmed_by="reviewer", owner_confirmed_distinct=ids,
                             plan_hash=pending["plan_hash"])
    confirmed = importer.confirm(source, confirmed_by="reviewer", owner_confirmed_distinct=groups,
                                 plan_hash=pending["plan_hash"])
    assert confirmed["ok"]
    assert confirmed["owner_confirmed_distinct"] == sorted(groups)
    assert confirmed["plan_hash"] != pending["plan_hash"]
    assert backend.records("tenant-a", "Synthetic Trading") == []
    assert not importer.preview(dict(source, batch_id="different-batch"))["ok"]
    assert apply(OpeningImporter(backend), source)["status"] == "applied"
    assert apply(importer, source)["status"] == "already_applied"


def test_similar_codes_are_not_name_findings_in_opening_details(backend):
    datasets = opening_details("50")
    datasets["Customer"] = [{"customer_code": f"CUST-{suffix}"} for suffix in ("A", "B")]
    datasets["Item"] = [{"item_code": f"SKU-RED-{size}"} for size in ("S", "M")]
    datasets["AR"] = [{"customer": row["customer_code"], "amount": "25"} for row in datasets["Customer"]]
    datasets["Stock"] = [{"item_code": row["item_code"], "warehouse": "W1", "qty": "1", "valuation_rate": "50"}
                         for row in datasets["Item"]]
    assert OpeningImporter(backend).preview(batch(datasets))["ok"]


@pytest.mark.parametrize("explicit_clear", [False, True])
def test_master_update_preserves_omissions_and_reports_explicit_clears(backend, explicit_clear):
    importer = OpeningImporter(backend)
    old = {"customer_code": "C1", "customer_name": "Before", "tax_id": "synthetic-tax"}
    apply(importer, batch({"Customer": [old]}))
    update = {"customer_code": "C1", "customer_name": "After"}
    if explicit_clear:
        update["tax_id"] = ""
    source = batch({"Customer": [update]}, batch_id="update")
    preview = importer.preview(source)
    assert preview["master_update_fields"] == [
        {"entity": "Customer", "row": 1, "changed_fields": ["customer_name"],
         "cleared_fields": ["tax_id"] if explicit_clear else []}]
    apply(importer, source)
    stored, = backend.records("tenant-a", "Synthetic Trading")
    assert stored["row"] == (dict(update, tax_id="synthetic-tax") if not explicit_clear else
                             {"customer_code": "C1", "customer_name": "After"})


@pytest.mark.parametrize("mark", ["\u200e", "\u200f", "\u200c", "\u200d", "\u061c"])
def test_arabic_text_keeps_directional_and_joining_marks(backend, mark):
    importer = OpeningImporter(backend)
    name = mark + "محمد" + mark + " أحمد"
    apply(importer, batch({"Customer": [{"customer_name": name}]}))
    assert backend.records("tenant-a", "Synthetic Trading")[0]["row"]["customer_name"] == name
    refuses(importer, batch({"Customer": [{"customer_name": mark + "＝1+1"}]}), "IMP-FORMULA")


def _two_control_datasets(entity, link_field, master_entity, master_row,
                          acct1, acct2, acct_type, first_val, second_val):
    side, other = ("credit", "debit") if acct_type == "Payable" else ("debit", "credit")
    val_key = "qty" if entity == "Stock" else "amount"
    extra = {"warehouse": "W1", "valuation_rate": "10.00"} if entity == "Stock" else {}
    second_extra = {"warehouse": "W1", "valuation_rate": "25.00"} if entity == "Stock" else {}
    t1 = "50.00" if entity == "Stock" else first_val
    t2 = "25.00" if entity == "Stock" else second_val
    total = "75.00" if entity == "Stock" else "100.00"
    datasets = {
        "Account": [
            {"account_number": acct1, "account_type": acct_type},
            {"account_number": acct2, "account_type": acct_type},
            {"account_number": "3000", "account_type": "Other"},
        ],
        "TrialBalance": [
            {"account": acct1, "account_type": acct_type, side: t1, other: "0"},
            {"account": acct2, "account_type": acct_type, side: t2, other: "0"},
            {"account": "3000", "account_type": "Other", side: "0", other: total},
        ],
        master_entity: [master_row],
        entity: [
            {link_field: list(master_row.values())[0], "account": acct1, val_key: first_val, **extra},
            {link_field: list(master_row.values())[0], "account": acct2, val_key: second_val, **second_extra},
        ],
    }
    if entity == "Stock":
        datasets["Warehouse"] = [{"warehouse_name": "W1"}]
    return datasets


def test_invisible_marks_refused_in_codes_accounts_links_and_batch_id(backend):
    importer = OpeningImporter(backend)
    # Probe 1: customer code with RLM cannot create a second master or pass schema.
    refuses(importer, batch({"Customer": [
        {"customer_code": "C1", "customer_name": "One"},
        {"customer_code": "C1\u200f", "customer_name": "Twin"},
    ]}), "IMP-SCHEMA")
    # Probe 2: account number or TB link with LRM cannot bypass TB duplicate check.
    refuses(importer, batch({
        "Account": [
            {"account_number": "1100", "account_type": "Other"},
            {"account_number": "1100\u200e", "account_type": "Other"},
        ],
    }), "IMP-SCHEMA")
    refuses(importer, batch({
        "Account": [{"account_number": "1100", "account_type": "Other"}],
        "TrialBalance": [
            {"account": "1100", "account_type": "Other", "debit": "0", "credit": "0"},
            {"account": "1100\u200e", "account_type": "Other", "debit": "0", "credit": "0"},
        ],
    }), "IMP-SCHEMA")
    # batch_id and link fields refuse format marks too.
    refuses(importer, batch(batch_id="opening-1\u200f"), "IMP-SCHEMA")
    ar_bad = batch()
    ar_bad["datasets"]["AR"][0]["customer"] = "C1\u200f"
    refuses(importer, ar_bad, "IMP-SCHEMA")
    ar_acct_bad = batch()
    ar_acct_bad["datasets"]["AR"][0]["account"] = "1100\u061c"
    refuses(importer, ar_acct_bad, "IMP-SCHEMA")
    # Name-only masters differing only by an invisible mark collide as duplicates.
    refuses(importer, batch({"Customer": [
        {"customer_name": "Acme"},
        {"customer_name": "Acme\u200f"},
    ]}), "IMP-DUPLICATE")


def test_alm_allowed_in_names_and_embedded_tab_is_schema_error(backend):
    importer = OpeningImporter(backend)
    name = "\u061cمحمد\u061c أحمد"
    apply(importer, batch({"Customer": [{"customer_name": name, "territory": "الرياض\u200f"}]}))
    stored, = backend.records("tenant-a", "Synthetic Trading")
    assert stored["row"]["customer_name"] == name
    refuses(importer, batch({"Customer": [{"customer_name": "\u061c＝1+1"}]}), "IMP-FORMULA")
    refuses(importer, batch({"Customer": [{"customer_name": "Buyer\tName"}]}), "IMP-SCHEMA")
    refuses(importer, batch({"Customer": [{"customer_name": "\tBuyer"}]}), "IMP-FORMULA")


def test_stock_ignores_control_account_while_ar_ap_key_on_party_and_account(backend):
    importer = OpeningImporter(backend)
    stock_ds = _two_control_datasets(
        "Stock", "item_code", "Item", {"item_code": "I1"},
        "1400", "1410", "Stock", "5", "1",
    )
    refuses(importer, batch(stock_ds), "IMP-DUPLICATE")
    ar_ds = _two_control_datasets(
        "AR", "customer", "Customer", {"customer_code": "C1"},
        "1100", "1110", "Receivable", "60.00", "40.00",
    )
    ar_preview = importer.preview(batch(ar_ds))
    assert ar_preview["ok"] and ar_preview["reconciliations"]["ar"] is True
    ar_swapped = copy.deepcopy(ar_ds)
    ar_swapped["AR"][0]["amount"], ar_swapped["AR"][1]["amount"] = "40.00", "60.00"
    refuses(importer, batch(ar_swapped), "IMP-RECONCILE")
    ar_dup = copy.deepcopy(ar_ds)
    ar_dup["AR"] = [
        {"customer": "C1", "account": "1100", "amount": "30.00"},
        {"customer": "C1", "account": "1100", "amount": "30.00"},
        {"customer": "C1", "account": "1110", "amount": "40.00"},
    ]
    refuses(importer, batch(ar_dup), "IMP-DUPLICATE")
    ap_ds = _two_control_datasets(
        "AP", "supplier", "Supplier", {"supplier_code": "S1"},
        "2100", "2200", "Payable", "40.00", "60.00",
    )
    ap_preview = importer.preview(batch(ap_ds))
    assert ap_preview["ok"] and ap_preview["reconciliations"]["ap"] is True
    ap_dup = copy.deepcopy(ap_ds)
    ap_dup["AP"] = [
        {"supplier": "S1", "account": "2100", "amount": "20.00"},
        {"supplier": "S1", "account": "2100", "amount": "20.00"},
        {"supplier": "S1", "account": "2200", "amount": "60.00"},
    ]
    refuses(importer, batch(ap_dup), "IMP-DUPLICATE")
    assert apply(importer, batch(ar_ds))["status"] == "applied"


def _near_duplicate_source():
    datasets = {
        "Customer": [
            {"customer_code": "CUST-A", "customer_name": "محمد أحمد"},
            {"customer_code": "CUST-B", "customer_name": "أحمد محمد"},
        ],
    }
    source = batch(datasets)
    source["prevalidation"] = prevalidate(
        datasets["Customer"], {"required": {"*": []}, "fields": {"party": "customer_name"}},
    ).to_dict()
    return source


def test_confirm_requires_pending_hash_append_only_and_journals_confirmer(backend, monkeypatch):
    importer = OpeningImporter(backend)
    source = _near_duplicate_source()
    pending = importer.preview(source)
    assert pending["ok"] is False
    groups = [g["id"] for g in pending["name_groups"]]

    # Missing, wrong, or stale pending hash is rejected.
    with pytest.raises(ImportFailure, match="IMP-CONFIRM"):
        importer.confirm(source, confirmed_by="reviewer", owner_confirmed_distinct=groups)
    with pytest.raises(ImportFailure, match="IMP-CONFIRM"):
        importer.confirm(source, confirmed_by="reviewer", owner_confirmed_distinct=groups, plan_hash="0" * 64)
    assert backend.conn.execute("SELECT count(*) FROM import_distinct_confirmations").fetchone()[0] == 0

    # Two distinct confirmers append rows without overwriting the earlier confirmer.
    monkeypatch.setattr(backend, "_session", lambda: {
        "user_id": "owner-1", "human": True, "tenant_id": "tenant-a",
        "companies": ["Synthetic Trading"], "capabilities": ["opening_import", "opening_import_confirm"],
    })
    confirmed = importer.confirm(
        source, confirmed_by="owner-1", owner_confirmed_distinct=groups, plan_hash=pending["plan_hash"],
    )
    assert confirmed["ok"]
    monkeypatch.setattr(backend, "_session", lambda: {
        "user_id": "owner-2", "human": True, "tenant_id": "tenant-a",
        "companies": ["Synthetic Trading"], "capabilities": ["opening_import", "opening_import_confirm"],
    })
    importer.confirm(
        source, confirmed_by="owner-2", owner_confirmed_distinct=groups, plan_hash=pending["plan_hash"],
    )
    confirmers = [
        r[0] for r in backend.conn.execute(
            "SELECT confirmed_by FROM import_distinct_confirmations ORDER BY seq ASC"
        ).fetchall()
    ]
    assert confirmers == ["owner-1", "owner-2"]

    # Applier records both applier and the first distinct confirmer in the batch journal.
    monkeypatch.setattr(backend, "_session", lambda: {
        "user_id": "reviewer", "human": True, "tenant_id": "tenant-a",
        "companies": ["Synthetic Trading"], "capabilities": ["opening_import"],
    })
    assert importer.apply(source, confirmed_by="reviewer", plan_hash=confirmed["plan_hash"])["status"] == "applied"
    journal = backend.journal("tenant-a", "opening-1")
    assert journal["confirmed_by"] == "reviewer"
    assert journal["distinct_confirmed_by"] == "owner-1"


def test_unconfigured_company_currency_fails_closed(monkeypatch):
    monkeypatch.setenv("CHANGE_ENGINE_ENV", "test")
    session = lambda: {
        "user_id": "reviewer", "human": True, "tenant_id": "tenant-a",
        "companies": ["Unconfigured Co"], "roles": ["Accounts Manager"],
    }
    with SQLiteImportBackend(session=session) as store:
        assert store.company_currency("tenant-a", "Unconfigured Co") is None
        refuses(OpeningImporter(store), batch(company="Unconfigured Co"), "IMP-CURRENCY")


def test_wrong_confirmed_by_is_logged_with_authenticated_user(backend):
    importer = OpeningImporter(backend)
    source = batch()
    preview = importer.preview(source)
    with pytest.raises(ImportFailure, match="IMP-CONFIRM"):
        importer.apply(source, confirmed_by="another-user", plan_hash=preview["plan_hash"])
    with pytest.raises(ImportFailure, match="IMP-CONFIRM"):
        importer.apply(source, confirmed_by="another-user", plan_hash=None)
    failures = backend.failures("tenant-a")
    assert [(f["code"], f["user_id"], f["plan_hash"]) for f in failures] == [
        ("IMP-CONFIRM", "reviewer", preview["plan_hash"]),
        ("IMP-CONFIRM", "reviewer", ""),
    ]


def test_legacy_distinct_confirmations_and_batches_migrate(tmp_path):
    path = tmp_path / "legacy_confirm.db"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE import_batches (
                tenant_id TEXT NOT NULL, batch_id TEXT NOT NULL, company TEXT NOT NULL,
                plan_hash TEXT NOT NULL, confirmed_by TEXT NOT NULL, status TEXT NOT NULL,
                PRIMARY KEY (tenant_id, batch_id));
            CREATE TABLE import_distinct_confirmations (
                tenant_id TEXT NOT NULL, company TEXT NOT NULL, batch_id TEXT NOT NULL,
                source_digest TEXT NOT NULL, group_ids_json TEXT NOT NULL, confirmed_by TEXT NOT NULL,
                PRIMARY KEY (tenant_id, company, batch_id, source_digest));
            INSERT INTO import_distinct_confirmations VALUES ('tenant-a', 'Co', 'b1', 'd1', '["g1"]', 'owner-1');
        """)
    conn.close()
    with SQLiteImportBackend(path) as store:
        with store.transaction():
            store.record_distinct_confirmation("tenant-a", "Co", "b1", "d1", "0" * 64, ["g1"], "owner-2")
        rows = [
            r[0] for r in store.conn.execute(
                "SELECT confirmed_by FROM import_distinct_confirmations ORDER BY seq ASC"
            ).fetchall()
        ]
        assert rows == ["owner-1", "owner-2"]


def test_interrupted_legacy_migration_recovers_and_failure_rolls_back(tmp_path, monkeypatch):
    legacy_sql = """
        CREATE TABLE import_distinct_confirmations (
            tenant_id TEXT NOT NULL, company TEXT NOT NULL, batch_id TEXT NOT NULL,
            source_digest TEXT NOT NULL, group_ids_json TEXT NOT NULL, confirmed_by TEXT NOT NULL,
            PRIMARY KEY (tenant_id, company, batch_id, source_digest));
        INSERT INTO import_distinct_confirmations VALUES ('tenant-a', 'Co', 'b1', 'd1', '["g1"]', 'owner-1');
    """
    # 1. Leftover _v2 table from an interrupted migration is dropped and recovery succeeds.
    leftover = tmp_path / "leftover_v2.db"
    with sqlite3.connect(leftover) as conn:
        conn.executescript(legacy_sql + "CREATE TABLE import_distinct_confirmations_v2 (stale TEXT);")
    conn.close()
    with SQLiteImportBackend(leftover) as store:
        tables = {r[0] for r in store.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "import_distinct_confirmations_v2" not in tables
        rows = store.conn.execute(
            "SELECT confirmed_by, pending_plan_hash FROM import_distinct_confirmations ORDER BY seq ASC"
        ).fetchall()
        assert [(r[0], r[1]) for r in rows] == [("owner-1", None)]

    # 2. Failure mid-migration (at RENAME after DROP TABLE) rolls back atomically, leaving old table intact.
    atomic = tmp_path / "atomic_fail.db"
    with sqlite3.connect(atomic) as conn:
        conn.executescript(legacy_sql)
    conn.close()
    real_connect = sqlite3.connect

    def failing_connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        conn.set_authorizer(
            lambda action, a1, a2, db, trig: sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_ALTER_TABLE and a2 == "import_distinct_confirmations_v2"
            else sqlite3.SQLITE_OK
        )
        return conn

    monkeypatch.setattr(sqlite3, "connect", failing_connect)
    with pytest.raises(sqlite3.DatabaseError):
        SQLiteImportBackend(atomic)
    monkeypatch.setattr(sqlite3, "connect", real_connect)
    with sqlite3.connect(atomic) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "import_distinct_confirmations" in tables
        assert "import_distinct_confirmations_v2" not in tables
        rows = conn.execute("SELECT confirmed_by FROM import_distinct_confirmations").fetchall()
        assert [r[0] for r in rows] == ["owner-1"]
    conn.close()


def test_master_change_after_confirm_invalidates_distinct_confirmation(backend, monkeypatch):
    importer = OpeningImporter(backend)
    source = _near_duplicate_source()
    pending = importer.preview(source)
    assert pending["ok"] is False
    groups = [g["id"] for g in pending["name_groups"]]

    def set_user(uid, caps):
        monkeypatch.setattr(backend, "_session", lambda: {
            "user_id": uid, "human": True, "tenant_id": "tenant-a",
            "companies": ["Synthetic Trading"], "capabilities": caps,
        })

    set_user("owner-1", ["opening_import", "opening_import_confirm"])
    confirmed = importer.confirm(
        source, confirmed_by="owner-1", owner_confirmed_distinct=groups, plan_hash=pending["plan_hash"],
    )
    assert confirmed["ok"] and importer.preview(source)["ok"]

    # Master-only change mutates the prior state covered by the plan -> old confirmation is invalid.
    set_user("reviewer", ["opening_import"])
    apply(importer, batch({"Customer": [{"customer_code": "CUST-A", "territory": "Riyadh"}]}, batch_id="master-edit"))
    after = importer.preview(source)
    assert after["ok"] is False and after["errors"][0]["code"] == "IMP-REPORT"
    assert after["plan_hash"] != pending["plan_hash"]
    with pytest.raises(ImportFailure, match="IMP-REPORT"):
        importer.apply(source, confirmed_by="reviewer", plan_hash=confirmed["plan_hash"])

    # Fresh confirmation against the new pending hash succeeds and journals the new confirmer.
    set_user("owner-2", ["opening_import", "opening_import_confirm"])
    reconfirmed = importer.confirm(
        source, confirmed_by="owner-2", owner_confirmed_distinct=groups, plan_hash=after["plan_hash"],
    )
    assert reconfirmed["ok"]
    set_user("reviewer", ["opening_import"])
    assert importer.apply(source, confirmed_by="reviewer", plan_hash=reconfirmed["plan_hash"])["status"] == "applied"
    assert backend.journal("tenant-a", "opening-1")["distinct_confirmed_by"] == "owner-2"
    assert apply(importer, source)["status"] == "already_applied"


def test_refused_confirm_logs_failure_with_authenticated_user(backend):
    importer = OpeningImporter(backend)
    source = _near_duplicate_source()
    pending = importer.preview(source)
    groups = [g["id"] for g in pending["name_groups"]]
    stale_hash = "0" * 64
    with pytest.raises(ImportFailure, match="IMP-CONFIRM"):
        importer.confirm(source, confirmed_by="reviewer", owner_confirmed_distinct=groups, plan_hash=stale_hash)
    with pytest.raises(ImportFailure, match="IMP-CONFIRM"):
        importer.confirm(source, confirmed_by="reviewer", owner_confirmed_distinct=["0" * 64], plan_hash=pending["plan_hash"])
    with pytest.raises(ImportFailure, match="IMP-CONFIRM"):
        importer.confirm(source, confirmed_by="other", owner_confirmed_distinct=groups, plan_hash=None)
    failures = backend.failures("tenant-a")
    assert [(f["code"], f["user_id"], f["plan_hash"]) for f in failures] == [
        ("IMP-CONFIRM", "reviewer", stale_hash),
        ("IMP-CONFIRM", "reviewer", pending["plan_hash"]),
        ("IMP-CONFIRM", "reviewer", ""),
    ]
