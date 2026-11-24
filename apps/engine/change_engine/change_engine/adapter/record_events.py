"""Capture business record facts in the site transaction and relay committed rows."""

from __future__ import annotations

import hashlib
import json
import re

from change_engine.adapter.mapping import entity_to_doctype
from change_engine.guarded_apply.schema_reconciler import make_bounded_lock_key

OUTBOX_TABLE = "tabChange Engine Event Outbox"
# ERP-005 G1 trading aggregates. Child rows and derived ledger rows have no hooks.
RECORD_ENTITIES = {
    entity_to_doctype(entity): entity
    for entity in (
        "customer", "sales_order", "sales_invoice", "delivery_note", "item", "item_price",
        "price_list", "warehouse", "stock_entry", "stock_entry_type", "stock_reconciliation",
        "account", "journal_entry", "fiscal_year", "company", "address", "contact",
    )
}
RECORD_HOOKS = {
    "after_insert": "created",
    "on_update": "updated",
    "on_submit": "submitted",
    "on_cancel": "cancelled",
    "on_update_after_submit": "updated",
}
_TENANT_ID = re.compile(r"[A-Za-z0-9_]{1,64}")
_ENGINE_NAME = re.compile(r"frappe|erpnext", re.IGNORECASE)
_BATCH_SIZE = 100


def _site_tenant(frappe) -> str:
    """Take the tenant from trusted provisioning configuration for this connected site."""
    tenant_id = frappe.conf.get("tenant_id")
    if (not isinstance(tenant_id, str) or not _TENANT_ID.fullmatch(tenant_id)
            or tenant_id == "platform" or _ENGINE_NAME.search(tenant_id)):
        raise RuntimeError("Site tenant is missing or invalid for the event stream")
    return tenant_id


def _opaque_id(tenant_id: str, namespace: str, value: str) -> str:
    """Keep names and logins out of the stream while retaining stable, site-scoped references."""
    identity = json.dumps([tenant_id, namespace, value]).encode()
    return hashlib.sha256(identity).hexdigest()


def record_document_event(doc, method: str) -> None:
    """Run after the engine writes a record, with the same connection and no commit."""
    import frappe

    entity = RECORD_ENTITIES[doc.doctype]
    verb = RECORD_HOOKS[method]
    if method == "on_update":
        previous = doc.get_doc_before_save()
        # The engine also calls on_update at insert and submit. Each has its own hook.
        if previous is None or previous.get("docstatus") != doc.get("docstatus"):
            return

    from evstream import Context, build_event, new_ulid

    tenant_id = _site_tenant(frappe)
    user = frappe.session.user
    actor_kind = "user" if user else "system"
    actor_id = _opaque_id(tenant_id, "actor", user) if user else "runtime"
    event_id = new_ulid()
    data = {"changes": {"status": verb}} if verb in ("submitted", "cancelled") else {}
    amended_from = doc.get("amended_from")
    if verb == "created" and amended_from:
        data["amended_from_id"] = _opaque_id(tenant_id, entity, amended_from)

    event = build_event(
        Context(tenant_id, actor_kind, actor_id, "engine"),
        f"{entity}.{verb}",
        data,
        event_id=event_id,
        correlation_id=event_id,
        subject={"entity": entity, "id": _opaque_id(tenant_id, entity, doc.name)},
    )
    frappe.db.sql(
        f"INSERT INTO `{OUTBOX_TABLE}` (event_id, payload) VALUES (%s, %s)",
        (event_id, json.dumps(event)),
    )


def publish_pending() -> int:
    """Relay a bounded batch from the scheduler's own site connection.

    The operator-configured sink implements EventStore.append and acknowledges durable
    acceptance. Capture continues while the sink is unconfigured or unavailable.
    """
    import frappe

    if getattr(frappe.local, "request", None) is not None:
        raise RuntimeError("Event publishing requires a background job")
    sink_path = frappe.conf.get("record_event_sink")
    if not sink_path:
        return 0

    tenant_id = _site_tenant(frappe)
    append = frappe.get_attr(sink_path)
    db = frappe.db
    # One drainer per site database. A DB lock does not lock the document writes.
    lock_key = make_bounded_lock_key(frappe.conf["db_name"], "record_event_outbox")
    acquired = db.sql("SELECT GET_LOCK(%s, 0)", (lock_key,))[0][0]
    if acquired == 0:
        return 0
    if acquired != 1:
        raise RuntimeError("Unable to lock the event outbox")

    delivered = 0
    try:
        for _ in range(_BATCH_SIZE):
            # Document writes serialize on their record lock. The resulting order of
            # committed outbox rows preserves that order for each aggregate.
            rows = db.sql(f"SELECT event_id, payload FROM `{OUTBOX_TABLE}` ORDER BY position LIMIT 1")
            if not rows:
                db.rollback()  # End the read snapshot.
                break
            event_id, payload = rows[0]
            event = json.loads(payload)
            if event["tenant_id"] != tenant_id or event["event_id"] != event_id:
                raise RuntimeError("Event outbox tenant mismatch or invalid identifier")
            accepted = append(event)
            sequence = accepted.get("sequence") if isinstance(accepted, dict) else None
            if (type(sequence) is not int or sequence < 1 or accepted.get("event_id") != event_id
                    or accepted.get("tenant_id") != tenant_id):
                raise RuntimeError("Event sink returned an invalid acknowledgment")
            db.sql(f"DELETE FROM `{OUTBOX_TABLE}` WHERE event_id = %s", (event_id,))
            db.commit()
            delivered += 1
    except Exception:
        db.rollback()
        raise
    finally:
        db.sql("SELECT RELEASE_LOCK(%s)", (lock_key,))
    return delivered
