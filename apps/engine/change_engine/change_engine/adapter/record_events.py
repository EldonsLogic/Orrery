"""Capture business record facts in the site transaction and relay committed rows."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
import sys
import threading
import time

from change_engine.adapter.mapping import entity_to_doctype
from change_engine.guarded_apply.schema_reconciler import make_bounded_lock_key

_LOGGER = logging.getLogger(__name__)

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
_VALID_ENTITIES = frozenset(RECORD_ENTITIES.values())
_VALID_VERBS = frozenset(RECORD_HOOKS.values())
_TENANT_ID = re.compile(r"[A-Za-z0-9_]{1,64}")
_ENGINE_NAME = re.compile(r"frappe|erpnext", re.IGNORECASE)
_IGNORED_DIFF_FIELDS = frozenset({"modified", "modified_by", "creation", "owner", "idx", "docstatus"})
_BATCH_SIZE = 100
_MAX_ROWS_PER_TICK = 10_000
_MAX_DELIVERY_ATTEMPTS = 5

# Self-contained Contract 4 ULID & envelope validation constants (mirrors services/blueprint/events).
_ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_ULID_RE = re.compile(r"[0-7][0-9A-HJKMNP-TV-Z]{25}")
_ULID_MAX_MS = (1 << 48) - 1
_ULID_RAND_BITS = 80
_MAX_DATA_BYTES = 64 * 1024
_MAX_DATA_DEPTH = 6
_MAX_DATA_NODES = 5000
_MAX_DATA_KEYS = 40
_WHOLE_RECORD_KEYS = frozenset({"record", "whole_record", "full_record", "document", "doc", "row", "snapshot"})
_WHOLE_RECORD_MARKER = "__whole_record__"
_TENANT_KEYS = frozenset({"tenantid", "tenantids", "tenant"})
_TENANT_VALUE_RE = re.compile(r"t_[A-Za-z0-9_]{3,62}")
_ISO_Z_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z")


class RecordEventError(Exception):
    """Contract validation or rejection error raised by the self-contained engine emitter."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}" if message else code)


class _UlidGenerator:
    """Monotonic Crockford base32 ULID generator using the Python standard library only."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_ms = -1
        self._last_rand = 0

    @staticmethod
    def _encode(value: int) -> str:
        out = []
        for _ in range(26):
            out.append(_ULID_ALPHABET[value & 31])
            value >>= 5
        return "".join(reversed(out))

    @staticmethod
    def _fresh() -> int:
        return int.from_bytes(os.urandom(10), "big")

    def generate(self) -> str:
        with self._lock:
            ms = max(time.time_ns() // 1_000_000, self._last_ms)
            if ms == self._last_ms:
                rand = self._last_rand + 1
                if rand >> _ULID_RAND_BITS:
                    ms += 1
                    rand = self._fresh()
            else:
                rand = self._fresh()
            if ms > _ULID_MAX_MS:
                raise RecordEventError("EVS-ENV-001", "ULID timestamp out of range")
            self._last_ms, self._last_rand = ms, rand
            return self._encode((ms << _ULID_RAND_BITS) | rand)


_ULID_GENERATOR = _UlidGenerator()


def _new_ulid() -> str:
    return _ULID_GENERATOR.generate()


def _is_valid_ulid(value: object) -> bool:
    return isinstance(value, str) and _ULID_RE.fullmatch(value) is not None


def _iso_z_now() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _norm_key(key: str) -> str:
    return re.sub(r"[^a-z]", "", key.lower())


def _validate_record_data(data: object, tenant_id: str) -> None:
    """Validate record event `data` against Contract 4 shape, size, and tenant-isolation rules."""
    if not isinstance(data, dict):
        raise RecordEventError("EVS-DATA-001", "data must be a JSON object")

    nodes = 0
    keys = 0
    stack: list[tuple[object, int, str]] = [(data, 1, "data")]
    while stack:
        val, depth, path = stack.pop()
        nodes += 1
        if nodes > _MAX_DATA_NODES:
            raise RecordEventError("EVS-DATA-002", f"{path}: more than {_MAX_DATA_NODES} values")
        if depth > _MAX_DATA_DEPTH:
            raise RecordEventError("EVS-DATA-003", f"{path}: nesting deeper than {_MAX_DATA_DEPTH}")
        if isinstance(val, dict):
            keys += len(val)
            if keys > _MAX_DATA_KEYS:
                raise RecordEventError("EVS-DATA-004", f"data: more than {_MAX_DATA_KEYS} keys")
            if val.get(_WHOLE_RECORD_MARKER):
                raise RecordEventError("EVS-DATA-004", f"{path}: object marked as a whole record")
            for k, v in val.items():
                if not isinstance(k, str):
                    raise RecordEventError("EVS-DATA-005", f"{path}: non-string key")
                child_path = f"{path}.{k[:60]}"
                if _norm_key(k) in _TENANT_KEYS:
                    raise RecordEventError("EVS-TENANT-001", f"{child_path}: data must not carry a tenant id")
                if k in _WHOLE_RECORD_KEYS and isinstance(v, (dict, list)):
                    raise RecordEventError("EVS-DATA-004", f"{child_path}: whole record embedded")
                stack.append((v, depth + 1, child_path))
        elif isinstance(val, list):
            for idx, item in enumerate(val):
                stack.append((item, depth + 1, f"{path}[{idx}]"))
        elif isinstance(val, str):
            if _TENANT_VALUE_RE.fullmatch(val) and val != tenant_id:
                raise RecordEventError("EVS-TENANT-001", f"{path}: another tenant's id inside data")
        elif isinstance(val, bool) or val is None or isinstance(val, int):
            pass
        elif isinstance(val, float):
            if not math.isfinite(val):
                raise RecordEventError("EVS-DATA-005", f"{path}: NaN or infinity")
        else:
            raise RecordEventError("EVS-DATA-005", f"{path}: value of type {type(val).__name__} is not JSON")

    if "changed_fields" in data:
        cf = data["changed_fields"]
        if not isinstance(cf, list) or len(cf) > 100 or not all(
            isinstance(item, str) and 1 <= len(item) <= 256 for item in cf
        ):
            raise RecordEventError("EVS-DATA-001", "data.changed_fields must be a list of <= 100 non-empty strings")
    if "changes" in data and not isinstance(data["changes"], dict):
        raise RecordEventError("EVS-DATA-001", "data.changes must be an object")

    try:
        encoded = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RecordEventError("EVS-DATA-005", "data is not serialisable as JSON") from exc
    if len(encoded) > _MAX_DATA_BYTES:
        raise RecordEventError("EVS-DATA-002", f"data exceeds {_MAX_DATA_BYTES} bytes")


def _build_record_event(
    *,
    tenant_id: str,
    actor_kind: str,
    actor_id: str,
    entity: str,
    verb: str,
    data: dict,
    event_id: str,
    subject_id: str,
) -> dict:
    """Construct and validate a Contract 4 business record event envelope using stdlib only."""
    if entity not in _VALID_ENTITIES or verb not in _VALID_VERBS:
        raise RecordEventError("EVS-TYPE-001", f"unsupported record event type: {entity}.{verb}")
    if not _is_valid_ulid(event_id):
        raise RecordEventError("EVS-ENV-001", "event_id is not a valid ULID")
    if (not isinstance(tenant_id, str) or not _TENANT_ID.fullmatch(tenant_id)
            or tenant_id == "platform" or _ENGINE_NAME.search(tenant_id)):
        raise RecordEventError("EVS-TENANT-002", "invalid tenant_id for record event")
    if actor_kind not in ("user", "system"):
        raise RecordEventError("EVS-ENV-001", "invalid actor.kind")
    if not isinstance(actor_id, str) or not (1 <= len(actor_id) <= 256):
        raise RecordEventError("EVS-ENV-001", "invalid actor.id")
    if not isinstance(subject_id, str) or not (1 <= len(subject_id) <= 256):
        raise RecordEventError("EVS-SUBJ-001", "invalid subject.id")

    _validate_record_data(data, tenant_id)
    now_iso = _iso_z_now()
    if not _ISO_Z_RE.fullmatch(now_iso):
        raise RecordEventError("EVS-ENV-001", "invalid timestamp format")

    return {
        "event_id": event_id,
        "type": f"{entity}.{verb}",
        "schema_version": 1,
        "occurred_at": now_iso,
        "recorded_at": now_iso,
        "tenant_id": tenant_id,
        "actor": {
            "kind": actor_kind,
            "id": actor_id,
            "role_ids": [],
            "on_behalf_of": None,
        },
        "source": {"service": "engine"},
        "correlation_id": event_id,
        "causation_id": None,
        "subject": {"entity": entity, "id": subject_id},
        "data": copy.deepcopy(data),
        "data_class": "business",
        "trace": None,
    }


def _is_event_rejection_error(exc: BaseException) -> bool:
    """True when the sink rejected the event itself (contract/poison error), False for outages."""
    if isinstance(exc, RecordEventError):
        return True
    evstream_mod = sys.modules.get("evstream")
    ev_err = getattr(evstream_mod, "EventError", None) if evstream_mod is not None else None
    if isinstance(ev_err, type) and issubclass(ev_err, BaseException) and isinstance(exc, ev_err):
        return True
    code = getattr(exc, "code", None)
    return isinstance(code, str) and code.startswith("EVS-") and type(exc).__name__ == "EventError"


def _import_evstream():
    """Optional helper to import evstream in monorepo/test environments (not required at runtime)."""
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
                import evstream  # type: ignore
                return evstream
        raise


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

    tenant_id = _site_tenant(frappe)
    user = frappe.session.user
    actor_kind = "user" if user else "system"
    actor_id = _opaque_id(tenant_id, "actor", user) if user else "runtime"
    event_id = _new_ulid()

    if method == "after_rename":
        old_name = args[0] if len(args) >= 1 and args[0] else doc.name
        new_name = args[1] if len(args) >= 2 and args[1] else doc.name
        merge = bool(args[2]) if len(args) >= 3 else False
        subject_id, merged_from_id = _rename_subject_id(
            frappe.db, entity, old_name, new_name, merge=merge, new_ulid=_new_ulid,
        )
        data: dict = {"id": subject_id, "changed_fields": ["name"]}
        if merged_from_id:
            data["merged_from_id"] = merged_from_id
    else:
        if verb == "created":
            subject_id = _new_subject_id(frappe.db, entity, doc.name, _new_ulid)
        else:
            subject_id = _get_or_create_subject_id(frappe.db, entity, doc.name, _new_ulid)
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
            data["amended_from_id"] = _get_or_create_subject_id(frappe.db, entity, amended_from, _new_ulid)

    event = _build_record_event(
        tenant_id=tenant_id,
        actor_kind=actor_kind,
        actor_id=actor_id,
        entity=entity,
        verb=verb,
        data=data,
        event_id=event_id,
        subject_id=subject_id,
    )
    frappe.db.sql(
        f"INSERT INTO `{OUTBOX_TABLE}` (event_id, payload) VALUES (%s, %s)",
        (event_id, json.dumps(event)),
    )


def outbox_metrics(db=None) -> dict[str, int]:
    """Return pending and dead-lettered row counts for the current site outbox."""
    if db is None:
        import frappe
        db = frappe.db
    if not _tables_exist(db):
        return {"pending": 0, "dead_lettered": 0}
    pending = int(db.sql(f"SELECT COUNT(*) FROM `{OUTBOX_TABLE}` WHERE dead_lettered_at IS NULL")[0][0])
    dead_lettered = int(db.sql(f"SELECT COUNT(*) FROM `{OUTBOX_TABLE}` WHERE dead_lettered_at IS NOT NULL")[0][0])
    return {"pending": pending, "dead_lettered": dead_lettered}


def _dead_letter_row(db, event_id: str, attempts: int, error: str) -> None:
    db.sql(
        f"UPDATE `{OUTBOX_TABLE}` SET attempts = %s, last_error = %s, dead_lettered_at = %s WHERE event_id = %s",
        (attempts, error[:1000], _utc_now(), event_id),
    )
    db.commit()
    dead_total = int(db.sql(f"SELECT COUNT(*) FROM `{OUTBOX_TABLE}` WHERE dead_lettered_at IS NOT NULL")[0][0])
    _LOGGER.warning(
        "Event %s dead-lettered after %d attempt(s) (dead_lettered_total=%d)",
        event_id,
        attempts,
        dead_total,
    )


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
    if not _tables_exist(frappe.db):
        return 0
    sink_path = frappe.conf.get("record_event_sink")
    if not sink_path:
        pending = int(frappe.db.sql(f"SELECT COUNT(*) FROM `{OUTBOX_TABLE}` WHERE dead_lettered_at IS NULL")[0][0])
        frappe.db.rollback()  # End the read snapshot.
        if pending:
            _LOGGER.warning(
                "record_event_sink is unset; %d record event(s) remain pending in outbox",
                pending,
            )
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
                    if _is_event_rejection_error(exc) and next_attempts >= max_attempts:
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
