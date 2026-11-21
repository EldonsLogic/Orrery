"""Capture business record facts in the site transaction and relay committed rows."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from change_engine.adapter.mapping import entity_to_doctype
from change_engine.guarded_apply.schema_reconciler import make_bounded_lock_key

OUTBOX_TABLE = "tabChange Engine Event Outbox"
SUBJECT_TABLE = "tabChange Engine Event Subject"
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
    "on_trash": "deleted",
    "after_rename": "updated",
}
_TENANT_ID = re.compile(r"[A-Za-z0-9_]{1,64}")
_ENGINE_NAME = re.compile(r"frappe|erpnext", re.IGNORECASE)
_IGNORED_DIFF_FIELDS = frozenset({"modified", "modified_by", "creation", "owner", "idx", "docstatus"})
_BATCH_SIZE = 100
_MAX_ROWS_PER_TICK = 10_000
_MAX_DELIVERY_ATTEMPTS = 5


def _import_evstream():
    """Import evstream via environment, installed package, or monorepo discovery."""
    try:
        import evstream  # type: ignore
        return evstream
    except ModuleNotFoundError:
        candidates: list[Path] = []
        env_dir = os.environ.get("ORRERY_EVSTREAM_DIR")
        if env_dir:
            candidates.append(Path(env_dir))
        for parent in Path(__file__).resolve().parents:
            candidates.append(parent / "services" / "blueprint" / "events")
        for cand in candidates:
            if (cand / "evstream" / "__init__.py").is_file():
                cand_str = str(cand)
                if cand_str not in sys.path:
                    sys.path.insert(0, cand_str)
                try:
                    import evstream  # type: ignore
                    return evstream
                except ModuleNotFoundError as exc:
                    raise RuntimeError("Event stream package is required on tenant-bound sites") from exc
        raise RuntimeError("Event stream package is required on tenant-bound sites")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_missing_table_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "doesn't exist" in msg or "no such table" in msg or "1146" in msg


def _in_migration(frappe) -> bool:
    flags = getattr(frappe, "flags", None)
    return bool(
        flags and (
            getattr(flags, "in_install", False)
            or getattr(flags, "in_migrate", False)
            or getattr(flags, "in_patch", False)
        )
    )


def _tables_exist(db) -> bool:
    for table in (OUTBOX_TABLE, SUBJECT_TABLE):
        try:
            db.sql(f"SELECT 1 FROM `{table}` LIMIT 1")
        except Exception as exc:
            if _is_missing_table_error(exc):
                return False
            raise
    return True


def _site_tenant(frappe) -> str:
    """Take the tenant from trusted provisioning configuration for this connected site."""
    tenant_id = frappe.conf.get("tenant_id")
    if (not isinstance(tenant_id, str) or not _TENANT_ID.fullmatch(tenant_id)
            or tenant_id == "platform" or _ENGINE_NAME.search(tenant_id)):
        raise RuntimeError("Site tenant is missing or invalid for the event stream")
    return tenant_id


def _opaque_id(tenant_id: str, namespace: str, value: str) -> str:
    """Keep actor logins out of the stream while retaining stable, site-scoped references."""
    identity = json.dumps([tenant_id, namespace, value]).encode()
    return hashlib.sha256(identity).hexdigest()


def _live_subject_id(db, entity: str, record_name: str) -> str | None:
    rows = db.sql(
        f"SELECT subject_id FROM `{SUBJECT_TABLE}` WHERE entity = %s AND record_name = %s AND live = 1",
        (entity, record_name),
    )
    return rows[0][0] if rows else None


def _retire_subject(db, subject_id: str) -> None:
    """Keep the reverse mapping of a gone record but free its name for a later record."""
    db.sql(f"UPDATE `{SUBJECT_TABLE}` SET live = NULL WHERE subject_id = %s", (subject_id,))


def _mint_subject_id(db, entity: str, record_name: str, new_ulid) -> str:
    subject_id = f"rec_{new_ulid()}"
    db.sql(
        f"INSERT INTO `{SUBJECT_TABLE}` (subject_id, entity, record_name, live) VALUES (%s, %s, %s, 1)",
        (subject_id, entity, record_name),
    )
    return subject_id


def _get_or_create_subject_id(db, entity: str, record_name: str, new_ulid) -> str:
    """Return the stable, reversible surrogate ID (`rec_<ulid>`) of the live record with this name."""
    return _live_subject_id(db, entity, record_name) or _mint_subject_id(db, entity, record_name, new_ulid)


def _new_subject_id(db, entity: str, record_name: str, new_ulid) -> str:
    """A newly inserted record never inherits the ID of an earlier record that had its name."""
    stale = _live_subject_id(db, entity, record_name)
    if stale:
        _retire_subject(db, stale)
    return _mint_subject_id(db, entity, record_name, new_ulid)


def _rename_subject_id(db, entity: str, old_name: str, new_name: str, *, merge: bool, new_ulid) -> tuple[str, str | None]:
    """Preserve subject_id across renames; return (subject_id, merged_from_id)."""
    old_id = _live_subject_id(db, entity, old_name)
    new_id = _live_subject_id(db, entity, new_name)
    if old_id and new_id and old_id != new_id:
        if merge:
            _retire_subject(db, old_id)
            return new_id, old_id
        _retire_subject(db, new_id)  # A stale entry must not block the rename.
        new_id = None
    if old_id:
        db.sql(f"UPDATE `{SUBJECT_TABLE}` SET record_name = %s WHERE subject_id = %s", (new_name, old_id))
        return old_id, None
    if new_id:
        return new_id, None
    return _mint_subject_id(db, entity, new_name, new_ulid), None


def resolve_subject_id(db, subject_id: str) -> tuple[str, str] | None:
    """Reverse-map a surrogate subject_id back to (entity, record_name) on its site DB."""
    rows = db.sql(
        f"SELECT entity, record_name FROM `{SUBJECT_TABLE}` WHERE subject_id = %s",
        (subject_id,),
    )
    if not rows:
        return None
    return rows[0][0], rows[0][1]


def _snapshot(doc) -> dict | None:
    """Plain field mapping of a dict or an engine document (which is not a dict)."""
    if isinstance(doc, dict):
        return doc
    as_dict = getattr(doc, "as_dict", None)
    if callable(as_dict):
        snapshot = as_dict()
        return snapshot if isinstance(snapshot, dict) else None
    return None


def _comparable(value):
    """Drop save-time bookkeeping, also inside child rows, before comparing."""
    if isinstance(value, dict):
        return {k: _comparable(v) for k, v in value.items() if k not in _IGNORED_DIFF_FIELDS}
    if isinstance(value, (list, tuple)):
        return [_comparable(v) for v in value]
    return value


def _changed_fields(previous, doc) -> list[str]:
    """Return safe, sorted field names whose values changed between saves (no values/PII)."""
    before, after = _snapshot(previous), _snapshot(doc)
    if before is None or after is None:
        return []
    keys = (set(before) | set(after)) - _IGNORED_DIFF_FIELDS
    return [key for key in sorted(keys) if _comparable(before.get(key)) != _comparable(after.get(key))]


def record_document_event(doc, method: str, *args) -> None:
    """Run after the engine writes a record, with the same connection and no commit."""
    import frappe

    # A bare bench/install site is not an event producer until trusted provisioning
    # binds it to a tenant. A sink or even an invalid explicit binding must fail
    # closed below; absence of a sink never disables capture for a bound tenant.
    if "tenant_id" not in frappe.conf and not frappe.conf.get("record_event_sink"):
        return
    tenant_id = _site_tenant(frappe)

    entity = RECORD_ENTITIES[doc.doctype]
    verb = RECORD_HOOKS[method]
    previous = None
    if method == "on_update":
        previous = doc.get_doc_before_save()
        # The engine also calls on_update at insert and submit. Each has its own hook.
        if previous is None or previous.get("docstatus") != doc.get("docstatus"):
            return
    elif method == "on_update_after_submit":
        previous = doc.get_doc_before_save()

    if not _tables_exist(frappe.db):
        if _in_migration(frappe):
            return
        raise RuntimeError("Event outbox tables are missing; run bench migrate")

    evstream = _import_evstream()
    Context, build_event, new_ulid = evstream.Context, evstream.build_event, evstream.new_ulid

    user = frappe.session.user
    actor_kind = "user" if user else "system"
    actor_id = _opaque_id(tenant_id, "actor", user) if user else "runtime"
    event_id = new_ulid()

    if method == "after_rename":
        old_name = args[0] if len(args) >= 1 and args[0] else doc.name
        new_name = args[1] if len(args) >= 2 and args[1] else doc.name
        merge = bool(args[2]) if len(args) >= 3 else False
        subject_id, merged_from_id = _rename_subject_id(
            frappe.db, entity, old_name, new_name, merge=merge, new_ulid=new_ulid,
        )
        data: dict = {"id": subject_id, "changed_fields": ["name"]}
        if merged_from_id:
            data["merged_from_id"] = merged_from_id
    else:
        if verb == "created":
            subject_id = _new_subject_id(frappe.db, entity, doc.name, new_ulid)
        else:
            subject_id = _get_or_create_subject_id(frappe.db, entity, doc.name, new_ulid)
        data = {"id": subject_id}
        if verb in ("submitted", "cancelled"):
            data["changes"] = {"status": verb}
        elif verb == "deleted":
            data["deleted"] = True
            _retire_subject(frappe.db, subject_id)
        elif verb == "updated":
            changed = _changed_fields(previous, doc)
            if changed:
                data["changed_fields"] = changed
        amended_from = doc.get("amended_from")
        if verb == "created" and amended_from:
            data["amended_from_id"] = _get_or_create_subject_id(frappe.db, entity, amended_from, new_ulid)

    event = build_event(
        Context(tenant_id, actor_kind, actor_id, "engine"),
        f"{entity}.{verb}",
        data,
        event_id=event_id,
        correlation_id=event_id,
        subject={"entity": entity, "id": subject_id},
    )
    frappe.db.sql(
        f"INSERT INTO `{OUTBOX_TABLE}` (event_id, payload) VALUES (%s, %s)",
        (event_id, json.dumps(event)),
    )


def _dead_letter_row(db, event_id: str, attempts: int, error: str) -> None:
    db.sql(
        f"UPDATE `{OUTBOX_TABLE}` SET attempts = %s, last_error = %s, dead_lettered_at = %s WHERE event_id = %s",
        (attempts, error[:1000], _utc_now(), event_id),
    )
    db.commit()


def publish_pending(*, max_rows: int = _MAX_ROWS_PER_TICK, max_attempts: int = _MAX_DELIVERY_ATTEMPTS) -> int:
    """Relay committed outbox rows in bounded batches from the scheduler's site connection.

    The operator-configured sink implements EventStore.append and acknowledges durable
    acceptance. Poison rows are quarantined with dead_lettered_at so subsequent valid events
    keep draining: a corrupt payload, or a sink that rejects the event itself (EventError)
    max_attempts times. Any other failure (sink down, bad acknowledgment) is an outage, not a
    property of the event: the row stays pending and is retried, never quarantined.
    """
    import frappe

    if getattr(frappe.local, "request", None) is not None:
        raise RuntimeError("Event publishing requires a background job")
    sink_path = frappe.conf.get("record_event_sink")
    if not sink_path:
        return 0
    if not _tables_exist(frappe.db):
        return 0

    tenant_id = _site_tenant(frappe)
    event_error = _import_evstream().EventError
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
    processed = 0
    try:
        while processed < max_rows:
            batch_limit = min(_BATCH_SIZE, max_rows - processed)
            # Document writes serialize on their record lock. The resulting order of
            # committed outbox rows preserves that order for each aggregate.
            rows = db.sql(
                f"SELECT event_id, payload, attempts FROM `{OUTBOX_TABLE}` "
                "WHERE dead_lettered_at IS NULL ORDER BY position LIMIT %s",
                (batch_limit,),
            )
            if not rows:
                db.rollback()  # End the read snapshot.
                break
            for event_id, payload, attempts in rows:
                processed += 1
                try:
                    event = json.loads(payload)
                except Exception as exc:
                    _dead_letter_row(db, event_id, attempts + 1, f"invalid JSON payload: {exc}")
                    continue
                if not isinstance(event, dict) or event.get("event_id") != event_id:
                    _dead_letter_row(db, event_id, attempts + 1, "invalid envelope or event_id mismatch")
                    continue
                if event.get("tenant_id") != tenant_id:
                    raise RuntimeError("Event outbox tenant mismatch or invalid identifier")

                try:
                    accepted = append(event)
                    sequence = accepted.get("sequence") if isinstance(accepted, dict) else None
                    if (type(sequence) is not int or sequence < 1 or accepted.get("event_id") != event_id
                            or accepted.get("tenant_id") != tenant_id):
                        raise RuntimeError("Event sink returned an invalid acknowledgment")
                except Exception as exc:
                    next_attempts = attempts + 1
                    if isinstance(exc, event_error) and next_attempts >= max_attempts:
                        _dead_letter_row(db, event_id, next_attempts, str(exc))
                        continue
                    db.rollback()
                    db.sql(
                        f"UPDATE `{OUTBOX_TABLE}` SET attempts = %s, last_error = %s WHERE event_id = %s",
                        (next_attempts, str(exc)[:1000], event_id),
                    )
                    db.commit()
                    raise

                db.sql(f"DELETE FROM `{OUTBOX_TABLE}` WHERE event_id = %s", (event_id,))
                db.commit()
                delivered += 1
    except Exception:
        db.rollback()
        raise
    finally:
        db.sql("SELECT RELEASE_LOCK(%s)", (lock_key,))
    return delivered
