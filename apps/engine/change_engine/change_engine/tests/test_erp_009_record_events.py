"""Exercise the registered hooks and the outbox using separate transaction connections."""

import importlib
import json
import sqlite3
import sys
from types import SimpleNamespace

import pytest

from change_engine import hooks
from evstream import MemoryStore, validate_event


class Database:
    """Use SQLite for real commits and rollbacks, substituting MariaDB's lock functions."""

    def __init__(self, path):
        self.connection = sqlite3.connect(path)
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS document (name TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS `tabChange Engine Event Outbox` (
                position INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                payload TEXT NOT NULL
            );
        """)
        self.locked = False
        self.fail_commit = False

    def sql(self, query, params=()):
        if "GET_LOCK" in query:
            if self.locked:
                return [(0,)]
            self.locked = True
            return [(1,)]
        if "RELEASE_LOCK" in query:
            self.locked = False
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

    def get_doc_before_save(self):
        return self.get("prior")


def invoke_hook(doc, method):
    path = hooks.doc_events[doc.doctype][method]
    module, name = path.rsplit(".", 1)
    getattr(importlib.import_module(module), name)(doc, method)


@pytest.fixture
def sites(tmp_path, monkeypatch):
    connections = []
    engine = SimpleNamespace(
        conf={}, local=SimpleNamespace(),
        session=SimpleNamespace(user="frappe-private@example.invalid"),
    )
    monkeypatch.setitem(sys.modules, "frappe", engine)

    def select(tenant, *, worker=False):
        # Each worker owns a separate connection to its site's database.
        database = Database(tmp_path / tenant)
        connections.append(database.connection)
        engine.conf = {"tenant_id": tenant, "db_name": tenant}
        if worker:
            engine.conf["record_event_sink"] = "test.append"
        engine.db = database
        return database

    yield engine, select
    for connection in connections:
        connection.close()


def run_publisher(engine, append):
    engine.get_attr = lambda path: {"test.append": append}[path]
    path, = hooks.scheduler_events["all"]
    module, name = path.rsplit(".", 1)
    return getattr(importlib.import_module(module), name)()


def test_lifecycle_hooks_deliver_contract_events_in_order(sites):
    engine, select = sites
    db = select("t_alpha")
    draft = Document(docstatus=0, tenant_id="t_foreign", customer="t_foreign")
    invoke_hook(draft, "after_insert")
    invoke_hook(draft, "on_update")  # The insert also runs on_update.
    invoke_hook(Document(prior=draft, docstatus=0), "on_update")
    submitted = Document(prior=draft, docstatus=1)
    invoke_hook(submitted, "on_update")  # The submit also runs on_update.
    invoke_hook(submitted, "on_submit")
    invoke_hook(Document(prior=submitted, docstatus=1), "on_update_after_submit")
    invoke_hook(Document(prior=submitted, docstatus=2), "on_cancel")
    amended = Document(amended_from=draft.name, docstatus=0)
    amended.name = "new-document-1"
    invoke_hook(amended, "after_insert")
    db.commit()

    select("t_alpha", worker=True)
    store = MemoryStore()
    assert run_publisher(engine, store.append) == 6
    events = store.read("t_alpha")
    assert [event["type"] for event in events] == [
        "sales_order.created", "sales_order.updated", "sales_order.submitted",
        "sales_order.updated", "sales_order.cancelled", "sales_order.created",
    ]
    assert [event["sequence"] for event in events] == list(range(1, 7))
    assert all(validate_event(event).ok for event in events)
    assert all(event["actor"]["kind"] == "user" for event in events)
    assert events[2]["data"]["changes"] == {"status": "submitted"}
    assert events[-1]["data"]["amended_from_id"] == events[0]["subject"]["id"]
    assert events[-1]["subject"]["id"] != events[0]["subject"]["id"]
    visible = json.dumps(events).lower()
    for marker in ("frappe", "erpnext", "t_foreign", "private"):
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
