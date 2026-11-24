"""Exercise the registered hooks and the outbox using separate transaction connections."""

import importlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from change_engine import hooks
from change_engine.adapter.record_events import (
    RECORD_ENTITIES,
    RECORD_HOOKS,
    _import_evstream,
    resolve_subject_id,
)

_evstream = _import_evstream()
MemoryStore = _evstream.MemoryStore
validate_event = _evstream.validate_event


class Database:
    """Use SQLite for real commits and rollbacks with real per-DB threading locks."""

    _locks_guard = threading.Lock()
    _db_locks: dict[str, threading.Lock] = {}

    def __init__(self, path, *, create_tables: bool = True):
        self.path = str(path)
        self.connection = sqlite3.connect(self.path, check_same_thread=False, timeout=10.0)
        if create_tables:
            self.connection.executescript("""
                CREATE TABLE IF NOT EXISTS document (name TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS `tabChange Engine Event Outbox` (
                    position INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    payload TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NULL,
                    dead_lettered_at TEXT NULL
                );
                CREATE TABLE IF NOT EXISTS `tabChange Engine Event Subject` (
                    subject_id TEXT PRIMARY KEY,
                    entity TEXT NOT NULL,
                    record_name TEXT NOT NULL,
                    live INTEGER NULL DEFAULT 1,
                    UNIQUE(entity, record_name, live)
                );
            """)
        with self._locks_guard:
            self._lock = self._db_locks.setdefault(self.path, threading.Lock())
        self.held_locks: set[str] = set()
        self.fail_commit = False

    def sql(self, query, params=()):
        if "GET_LOCK" in query:
            key = params[0]
            if self._lock.acquire(blocking=False):
                self.held_locks.add(key)
                return [(1,)]
            return [(0,)]
        if "RELEASE_LOCK" in query:
            key = params[0]
            if key in self.held_locks:
                self.held_locks.remove(key)
                self._lock.release()
            return [(1,)]
        return self.connection.execute(query.replace("%s", "?"), params).fetchall()

    def commit(self):
        if self.fail_commit:
            raise ConnectionError("database acknowledgment lost")
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()


class Document(dict):
    doctype = "Sales Order"
    name = "ERPNext-customer-private-key"

    def __init__(self, *args, prior=None, **fields):
        super().__init__(*args, **fields)
        self._prior = prior

    def get_doc_before_save(self):
        return self._prior


class FrappeLikeDocument:
    """A real engine document is not a dict: it offers get() and as_dict() only."""

    doctype = "Sales Order"

    def __init__(self, name, prior=None, **fields):
        self.name = name
        self._prior = prior
        self._fields = fields

    def get(self, key, default=None):
        return self._fields.get(key, default)

    def as_dict(self):
        return json.loads(json.dumps(self._fields))

    def get_doc_before_save(self):
        return self._prior


def invoke_hook(doc, method, *args):
    path = hooks.doc_events[doc.doctype][method]
    module, name = path.rsplit(".", 1)
    getattr(importlib.import_module(module), name)(doc, method, *args)


@pytest.fixture
def sites(tmp_path, monkeypatch):
    connections = []
    engine = SimpleNamespace(
        conf={},
        local=SimpleNamespace(),
        flags=SimpleNamespace(in_install=False, in_migrate=False, in_patch=False),
        session=SimpleNamespace(user="frappe-private@example.invalid"),
    )
    monkeypatch.setitem(sys.modules, "frappe", engine)

    def select(tenant, *, worker=False, create_tables=True):
        # Each worker owns a separate connection to its site's database.
        database = Database(tmp_path / tenant, create_tables=create_tables)
        connections.append(database.connection)
        engine.conf = {"tenant_id": tenant, "db_name": tenant}
        if worker:
            engine.conf["record_event_sink"] = "test.append"
        engine.db = database
        return database

    yield engine, select
    for connection in connections:
        connection.close()


def run_publisher(engine, append, **kwargs):
    engine.get_attr = lambda path: {"test.append": append}[path]
    path, = hooks.scheduler_events["all"]
    module, name = path.rsplit(".", 1)
    return getattr(importlib.import_module(module), name)(**kwargs)


def test_hooks_module_imports_no_adapter_at_load_and_matches_registry():
    assert set(hooks._RECORD_DOCTYPES) == set(RECORD_ENTITIES)
    assert set(hooks._RECORD_HOOK_METHODS) == set(RECORD_HOOKS)
    change_engine_root = str(Path(__file__).resolve().parents[2])
    env = {**os.environ, "PYTHONPATH": change_engine_root}
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, change_engine.hooks; "
            "assert not any(m.startswith('change_engine.adapter') for m in sys.modules)",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


@pytest.mark.parametrize("method", RECORD_HOOKS)
def test_unbound_bench_hooks_without_evstream(sites, monkeypatch, method):
    """Bench installs have no tenant binding or event package; unrelated writes still work."""
    engine, select = sites
    db = select("t_alpha")
    engine.conf.pop("tenant_id")
    monkeypatch.setitem(sys.modules, "evstream", None)
    importlib.reload(hooks)
    before = Document(docstatus=0)
    invoke_hook(Document(prior=before, docstatus=0), method)
    assert db.sql("SELECT COUNT(*) FROM `tabChange Engine Event Outbox`") == [(0,)]


def test_bound_site_without_evstream_fails_closed(sites, monkeypatch):
    """A provisioned tenant must never silently lose an event when its dependency is absent."""
    _, select = sites
    db = select("t_alpha")
    monkeypatch.setitem(sys.modules, "evstream", None)
    with pytest.raises(RuntimeError, match="Event stream package is required"):
        invoke_hook(Document(), "after_insert")
    assert db.sql("SELECT COUNT(*) FROM `tabChange Engine Event Subject`") == [(0,)]


def test_sink_without_tenant_is_a_configuration_error(sites, monkeypatch):
    """A sink opts into publication and must not silently run without a tenant binding."""
    engine, select = sites
    select("t_alpha", worker=True)
    engine.conf.pop("tenant_id")
    monkeypatch.setitem(sys.modules, "evstream", None)
    with pytest.raises(RuntimeError, match="Site tenant is missing"):
        invoke_hook(Document(), "after_insert")


def test_lifecycle_hooks_deliver_contract_events_with_delete_and_rename(sites):
    engine, select = sites
    db = select("t_alpha")
    draft = Document(docstatus=0, tenant_id="t_foreign", customer="t_foreign")
    invoke_hook(draft, "after_insert")
    invoke_hook(draft, "on_update")  # The insert also runs on_update.
    invoke_hook(Document({**draft, "grand_total": 150}, prior=draft), "on_update")
    submitted = Document(prior=draft, docstatus=1)
    invoke_hook(submitted, "on_update")  # The submit also runs on_update.
    invoke_hook(submitted, "on_submit")
    invoke_hook(Document(prior=submitted, docstatus=1, notes="updated"), "on_update_after_submit")

    # Rename keeps the exact same surrogate subject.id and updates the reverse map.
    renamed = Document(docstatus=1)
    renamed.name = "ERPNext-renamed-key"
    invoke_hook(renamed, "after_rename", draft.name, renamed.name, False)

    invoke_hook(Document(prior=submitted, docstatus=2), "on_cancel")
    amended = Document(amended_from=renamed.name, docstatus=0)
    amended.name = "new-document-1"
    invoke_hook(amended, "after_insert")
    invoke_hook(amended, "on_trash")
    db.commit()

    select("t_alpha", worker=True)
    store = MemoryStore()
    assert run_publisher(engine, store.append) == 8
    events = store.read("t_alpha")
    assert [event["type"] for event in events] == [
        "sales_order.created",
        "sales_order.updated",
        "sales_order.submitted",
        "sales_order.updated",
        "sales_order.updated",
        "sales_order.cancelled",
        "sales_order.created",
        "sales_order.deleted",
    ]
    assert [event["sequence"] for event in events] == list(range(1, 9))
    assert all(validate_event(event).ok for event in events)
    assert all(event["actor"]["kind"] == "user" for event in events)

    orig_subject_id = events[0]["subject"]["id"]
    assert orig_subject_id.startswith("rec_")
    # Same surrogate ID across update, submit, rename, and amendment link.
    assert events[4]["subject"]["id"] == orig_subject_id
    assert events[4]["data"]["changed_fields"] == ["name"]
    assert events[1]["data"]["changed_fields"] == ["grand_total"]
    assert events[2]["data"]["changes"] == {"status": "submitted"}
    assert events[6]["data"]["amended_from_id"] == orig_subject_id
    assert events[6]["subject"]["id"] != orig_subject_id
    assert events[7]["subject"]["id"] == events[6]["subject"]["id"]
    assert events[7]["data"]["deleted"] is True
    # Bidirectional mapping resolves renamed and deleted records cleanly.
    assert resolve_subject_id(db, orig_subject_id) == ("sales_order", "ERPNext-renamed-key")
    assert resolve_subject_id(db, events[6]["subject"]["id"]) == ("sales_order", "new-document-1")

    visible = json.dumps(events).lower()
    for marker in ("frappe", "erpnext", "t_foreign", "private", "renamed"):
        assert marker not in visible


def test_rollback_and_uncommitted_changes_never_reach_the_stream(sites):
    engine, select = sites
    db = select("t_alpha")
    db.sql("INSERT INTO document VALUES (%s)", ("rolled_back",))
    invoke_hook(Document(), "after_insert")

    select("t_alpha", worker=True)
    store = MemoryStore()
    assert run_publisher(engine, store.append) == 0
    db.rollback()
    assert run_publisher(engine, store.append) == 0
    assert store.read("t_alpha") == []
    assert db.sql("SELECT * FROM document") == []


def test_duplicate_delivery_reuses_the_id_when_the_outbox_ack_fails(sites):
    engine, select = sites
    db = select("t_alpha")
    invoke_hook(Document(), "after_insert")
    invoke_hook(Document(prior=Document(docstatus=0), docstatus=0), "on_update")
    db.commit()

    worker = select("t_alpha", worker=True)
    store = MemoryStore()
    worker.fail_commit = True
    with pytest.raises(ConnectionError):
        run_publisher(engine, store.append)
    delivered = store.read("t_alpha")
    assert len(delivered) == 1
    assert delivered[0]["type"] == "sales_order.created"
    worker.fail_commit = False
    assert run_publisher(engine, store.append) == 2
    first, second = store.read("t_alpha")
    assert first == delivered[0]
    assert second["type"] == "sales_order.updated"
    assert run_publisher(engine, store.append) == 0


def test_events_stay_with_the_site_database_and_its_trusted_tenant(sites):
    engine, select = sites
    alpha = select("t_alpha")
    invoke_hook(Document(tenant_id="t_bravo"), "after_insert")
    alpha.commit()
    bravo = select("t_bravo")
    invoke_hook(Document(tenant_id="t_alpha"), "after_insert")
    bravo.commit()

    store = MemoryStore()
    select("t_alpha", worker=True)
    engine.conf["tenant_id"] = "t_bravo"
    with pytest.raises(RuntimeError, match="tenant mismatch"):
        run_publisher(engine, store.append)
    assert store.read("t_alpha") == store.read("t_bravo") == []
    select("t_alpha", worker=True)
    assert run_publisher(engine, store.append) == 1
    assert store.read("t_bravo") == []
    select("t_bravo", worker=True)
    assert run_publisher(engine, store.append) == 1
    first, second = store.read("t_alpha")[0], store.read("t_bravo")[0]
    assert first["tenant_id"] == "t_alpha" and second["tenant_id"] == "t_bravo"
    assert first["event_id"] != second["event_id"]
    assert first["subject"]["id"] != second["subject"]["id"]


@pytest.mark.parametrize(("doctype", "event_type"), [
    ("Delivery Note", "delivery_note"),
    ("Stock Entry", "stock_entry"),
    ("Stock Reconciliation", "stock_reconciliation"),
    ("Journal Entry", "journal_entry"),
    ("Item Price", "item_price"),
    ("Warehouse", "warehouse"),
])
def test_trading_documents_are_tracked(sites, doctype, event_type):
    engine, select = sites
    db = select("t_alpha")
    doc = Document()
    doc.doctype = doctype
    invoke_hook(doc, "after_insert")
    db.commit()

    select("t_alpha", worker=True)
    store = MemoryStore()
    assert run_publisher(engine, store.append) == 1
    assert store.read("t_alpha")[0]["type"] == f"{event_type}.created"


def test_missing_or_invalid_tenant_rejects_the_write(sites):
    engine, select = sites
    db = select("t_alpha")
    del engine.conf["tenant_id"]
    engine.conf["record_event_sink"] = "test.append"
    with pytest.raises(RuntimeError, match="missing or invalid"):
        invoke_hook(Document(tenant_id="t_alpha"), "after_insert")
    engine.conf["tenant_id"] = "invalid-tenant"
    with pytest.raises(RuntimeError, match="missing or invalid"):
        invoke_hook(Document(), "after_insert")
    assert db.sql("SELECT * FROM `tabChange Engine Event Outbox`") == []


@pytest.mark.parametrize("acknowledge", [
    lambda event: {**event, "sequence": 1, "tenant_id": "t_bravo"},
    lambda event: event,
])
def test_invalid_sink_acknowledgment_keeps_the_event_pending(sites, acknowledge):
    engine, select = sites
    db = select("t_alpha")
    invoke_hook(Document(), "after_insert")
    db.commit()

    select("t_alpha", worker=True)
    with pytest.raises(RuntimeError, match="invalid acknowledgment"):
        run_publisher(engine, acknowledge)
    store = MemoryStore()
    assert run_publisher(engine, store.append) == 1
    assert store.read("t_alpha")[0]["type"] == "sales_order.created"


def test_poison_row_quarantined_and_does_not_block_valid_events(sites):
    engine, select = sites
    db = select("t_alpha")
    db.sql(
        "INSERT INTO `tabChange Engine Event Outbox` (event_id, payload) VALUES (%s, %s)",
        ("01J8ZK30000000000000000000", "{corrupt-json"),
    )
    bad_ack_doc = Document()
    bad_ack_doc.name = "bad-ack-doc"
    invoke_hook(bad_ack_doc, "after_insert")
    good_doc = Document()
    good_doc.name = "good-doc"
    invoke_hook(good_doc, "after_insert")
    db.commit()

    select("t_alpha", worker=True)
    store = MemoryStore()
    # Corrupt JSON row dead-letters automatically, bad-ack fails on attempt 1..1 until max_attempts=2,
    # then dead-letters on attempt 2 so good_doc delivers immediately.
    def flaky_append(ev):
        if "bad" in str(resolve_subject_id(db, ev["subject"]["id"])):
            raise _evstream.EventError("EVS-ENV-002", "sink rejected poison payload")
        return store.append(ev)

    with pytest.raises(_evstream.EventError, match="sink rejected"):
        run_publisher(engine, flaky_append, max_attempts=2)
    assert run_publisher(engine, flaky_append, max_attempts=2) == 1
    assert len(store.read("t_alpha")) == 1
    assert resolve_subject_id(db, store.read("t_alpha")[0]["subject"]["id"]) == ("sales_order", "good-doc")
    dead = db.sql(
        "SELECT event_id, dead_lettered_at FROM `tabChange Engine Event Outbox` WHERE dead_lettered_at IS NOT NULL"
    )
    assert len(dead) == 2


def test_changed_fields_work_on_real_non_dict_documents(sites):
    engine, select = sites
    db = select("t_alpha")
    row = {"name": "r1", "item_code": "A", "qty": 1, "modified": "2026-01-01 09:00:00", "idx": 1}
    before = FrappeLikeDocument(
        "SO-1", docstatus=0, grand_total=100, modified="2026-01-01 09:00:00", items=[row],
    )
    invoke_hook(FrappeLikeDocument("SO-1", docstatus=0), "after_insert")
    # Saving stamps every child row with a new modified time; that alone is not a change.
    stamped = {**row, "modified": "2026-01-02 09:00:00"}
    invoke_hook(FrappeLikeDocument(
        "SO-1", prior=before, docstatus=0, grand_total=150, notes="x",
        modified="2026-01-02 09:00:00", items=[stamped],
    ), "on_update")
    invoke_hook(FrappeLikeDocument(
        "SO-1", prior=before, docstatus=0, grand_total=100, modified="2026-01-02 09:00:00",
        items=[{**stamped, "qty": 2}],
    ), "on_update")
    db.commit()

    select("t_alpha", worker=True)
    store = MemoryStore()
    assert run_publisher(engine, store.append) == 3
    events = store.read("t_alpha")
    assert events[1]["data"]["changed_fields"] == ["grand_total", "notes"]
    assert events[2]["data"]["changed_fields"] == ["items"]


def test_recreating_a_deleted_name_gets_a_new_subject_id(sites):
    engine, select = sites
    db = select("t_alpha")
    doc = Document()
    doc.name = "CUST-1"
    invoke_hook(doc, "after_insert")
    invoke_hook(doc, "on_trash")
    invoke_hook(doc, "after_insert")  # The same name is created again later.
    edited = Document(prior=Document(docstatus=0), docstatus=0, notes="x")
    edited.name = "CUST-1"
    invoke_hook(edited, "on_update")
    db.commit()

    select("t_alpha", worker=True)
    store = MemoryStore()
    assert run_publisher(engine, store.append) == 4
    created, deleted, recreated, updated = store.read("t_alpha")
    assert created["subject"]["id"] == deleted["subject"]["id"]
    assert recreated["subject"]["id"] != deleted["subject"]["id"]
    assert updated["subject"]["id"] == recreated["subject"]["id"]
    assert resolve_subject_id(db, deleted["subject"]["id"]) == ("sales_order", "CUST-1")
    assert resolve_subject_id(db, recreated["subject"]["id"]) == ("sales_order", "CUST-1")
    live = db.sql("SELECT subject_id FROM `tabChange Engine Event Subject` WHERE live = 1")
    assert live == [(recreated["subject"]["id"],)]


def test_transient_sink_failures_never_dead_letter_an_event(sites):
    engine, select = sites
    db = select("t_alpha")
    for name in ("first", "second"):
        doc = Document()
        doc.name = name
        invoke_hook(doc, "after_insert")
    db.commit()

    select("t_alpha", worker=True)

    def down(_event):
        raise ConnectionError("sink unavailable")

    for _ in range(4):  # Far past max_attempts: an outage must not lose events.
        with pytest.raises(ConnectionError):
            run_publisher(engine, down, max_attempts=2)
    assert db.sql("SELECT COUNT(*) FROM `tabChange Engine Event Outbox` WHERE dead_lettered_at IS NOT NULL") == [(0,)]
    assert db.sql("SELECT attempts, last_error FROM `tabChange Engine Event Outbox` ORDER BY position")[0] == (
        4, "sink unavailable",
    )

    store = MemoryStore()
    assert run_publisher(engine, store.append, max_attempts=2) == 2
    names = [resolve_subject_id(db, e["subject"]["id"])[1] for e in store.read("t_alpha")]
    assert names == ["first", "second"]


def test_outbox_patch_does_not_swallow_ddl_errors():
    patch = importlib.import_module("change_engine.patches.erp_009_create_event_outbox")
    statements = []

    class Db:
        def sql_ddl(self, statement):
            statements.append(statement)
            if "ADD COLUMN" in statement:
                raise RuntimeError("ddl failed")

    sys.modules["frappe"] = SimpleNamespace(db=Db())
    try:
        with pytest.raises(RuntimeError, match="ddl failed"):
            patch.execute()
    finally:
        del sys.modules["frappe"]

    statements.clear()
    Db.sql_ddl = lambda self, statement: statements.append(statement)
    sys.modules["frappe"] = SimpleNamespace(db=Db())
    try:
        patch.execute()
    finally:
        del sys.modules["frappe"]
    assert any("live TINYINT" in statement for statement in statements)


def test_drains_more_than_100_rows_in_single_tick(sites):
    engine, select = sites
    db = select("t_alpha")
    for idx in range(150):
        doc = Document()
        doc.name = f"SO-{idx:04d}"
        invoke_hook(doc, "after_insert")
    db.commit()

    select("t_alpha", worker=True)
    store = MemoryStore()
    assert run_publisher(engine, store.append) == 150
    assert len(store.read("t_alpha", limit=200)) == 150


def test_pre_migrate_skips_during_migration_and_fails_closed_otherwise(sites):
    engine, select = sites
    select("t_unmigrated", worker=True, create_tables=False)
    assert run_publisher(engine, MemoryStore().append) == 0

    engine.flags.in_migrate = True
    invoke_hook(Document(), "after_insert")
    engine.flags.in_migrate = False

    with pytest.raises(RuntimeError, match="missing; run bench migrate"):
        invoke_hook(Document(), "after_insert")


def test_concurrent_publishers_serialize_with_advisory_lock_without_duplicates(sites, monkeypatch):
    engine, select = sites
    db = select("t_alpha")
    for idx in range(40):
        doc = Document()
        doc.name = f"CONC-{idx:03d}"
        invoke_hook(doc, "after_insert")
    db.commit()

    store = MemoryStore()
    store_lock = threading.Lock()
    entered = threading.Event()
    proceed = threading.Event()
    results: list[int] = []
    errors: list[BaseException] = []

    def synchronized_append(event):
        entered.set()
        proceed.wait(timeout=5.0)
        with store_lock:
            return store.append(event)

    def make_worker_frappe():
        wdb = Database(db.path)
        return SimpleNamespace(
            conf={"tenant_id": "t_alpha", "db_name": "t_alpha", "record_event_sink": "test.append"},
            local=SimpleNamespace(),
            flags=SimpleNamespace(in_install=False, in_migrate=False, in_patch=False),
            session=SimpleNamespace(user="frappe-private@example.invalid"),
            db=wdb,
            get_attr=lambda p: synchronized_append,
        )

    from change_engine.adapter import record_events

    worker_one = make_worker_frappe()
    worker_two = make_worker_frappe()

    # Start worker 1, wait until it holds GET_LOCK inside append, then launch worker 2.
    def run_w1():
        sys.modules["frappe"] = worker_one
        try:
            results.append(record_events.publish_pending())
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)
        finally:
            worker_one.db.connection.close()

    t1 = threading.Thread(target=run_w1)
    t1.start()
    assert entered.wait(timeout=5.0)
    # While worker 1 holds the DB advisory lock, worker 2 skips immediately with 0.
    sys.modules["frappe"] = worker_two
    try:
        second_count = record_events.publish_pending()
    finally:
        worker_two.db.connection.close()
        proceed.set()
        t1.join(timeout=10.0)

    assert not errors
    assert second_count == 0
    assert results == [40]
    assert len(store.read("t_alpha")) == 40
    assert [e["sequence"] for e in store.read("t_alpha")] == list(range(1, 41))
