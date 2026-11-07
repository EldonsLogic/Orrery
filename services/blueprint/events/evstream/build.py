"""build_event: the only supported way for a producer to make an event.

tenant_id, actor and source come from the authenticated Context, never from the payload.
sequence is assigned by the store; recorded_at is stamped again by the store on append.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable

from .errors import EventError
from .registry import Registry, default_registry
from .ulid import UlidGenerator, is_valid_ulid, new_ulid
from .validate import validate_event

ALLOWED_FIELDS = frozenset({"subject", "correlation_id", "causation_id", "occurred_at", "data_class",
                            "trace", "event_id"})
PLATFORM_STAMPED = frozenset({"sequence", "actor", "source", "recorded_at", "schema_version", "type", "data"})


@dataclass(frozen=True)
class Context:
    """Authenticated caller context, produced by the gateway after verifying the session."""
    tenant_id: str
    actor_kind: str  # user | agent | system | support
    actor_id: str
    service: str
    role_ids: tuple = ()
    on_behalf_of: str | None = None
    component: str | None = None
    blueprint_revision: int | None = None
    correlation_id: str | None = None


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def build_event(ctx: Context, type: str, data: dict, *, registry: Registry | None = None,
                clock: Callable[[], datetime] = utc_now, ids: UlidGenerator | None = None,
                known_tenant_ids: Iterable[str] = (), **fields) -> dict:
    reg = registry or default_registry()
    if "tenant_id" in fields:
        raise EventError("EVS-TENANT-001", "tenant_id comes from the context only")
    for k in fields:
        if k not in ALLOWED_FIELDS:
            why = "set by the platform" if k in PLATFORM_STAMPED else "unknown"
            raise EventError("EVS-FIELD-001", f"field {k!r} not allowed ({why})")
    info = reg.lookup(type)
    if info is None:
        raise EventError("EVS-TYPE-001", f"producers may only emit registry types: {str(type)[:80]!r}")
    event_id = fields.get("event_id") or (ids.generate() if ids else new_ulid())
    if not is_valid_ulid(event_id):
        raise EventError("EVS-ENV-001", "event_id is not a ULID")
    occurred = fields.get("occurred_at") or iso_z(clock())
    if isinstance(occurred, datetime):
        occurred = iso_z(occurred)
    actor = {"kind": ctx.actor_kind, "id": ctx.actor_id, "role_ids": list(ctx.role_ids),
             "on_behalf_of": ctx.on_behalf_of}
    source = {"service": ctx.service}
    if ctx.component is not None:
        source["component"] = ctx.component
    if ctx.blueprint_revision is not None:
        source["blueprint_revision"] = ctx.blueprint_revision
    ev = {
        "event_id": event_id, "type": type, "schema_version": info.schema_version,
        "occurred_at": occurred, "recorded_at": iso_z(clock()), "tenant_id": ctx.tenant_id,
        "actor": actor, "source": source,
        "correlation_id": fields.get("correlation_id") or ctx.correlation_id,
        "causation_id": fields.get("causation_id"),
        "subject": fields.get("subject"),
        "data": data,
        "data_class": fields.get("data_class") or info.data_class,
        "trace": fields.get("trace"),
    }
    res = validate_event(ev, reg, stamped=False, known_tenant_ids=known_tenant_ids)
    if not res.ok:
        first = res.errors[0]
        raise EventError(first.code, f"{first.path}: {first.message}")
    ev["data"] = copy.deepcopy(data)  # safe: depth and size were bounded by the validator
    for k in ("subject", "trace"):
        ev[k] = copy.deepcopy(ev[k])
    return ev
