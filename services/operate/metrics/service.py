"""MetricService: permission check from the caller's roles, tenant-scoped event read, formula, per-tenant cache.

`event_loader(tenant_id)` is an injected port returning that tenant's events (Event stream envelopes). The
service never trusts the loader: every event must carry the caller's tenant id or the call is refused.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal

from .errors import MetricError
from .registry import MINOR_UNITS, parse_window, quantize


@dataclass(frozen=True)
class Principal:
    tenant_id: str
    user_id: str
    role_ids: frozenset


class MetricService:
    def __init__(self, registry: dict, event_loader):
        self._reg = registry
        self._load = event_loader
        self._cache: dict = {}  # tenant_id -> {(metric_id, params_json): (watermark, result)}

    def catalog(self, principal) -> list:
        """Metric ids and label keys the caller may read (what the model is shown)."""
        p = self._principal(principal)
        return [{"id": m.id, "label_key": m.label_key, "unit": m.unit, "grain": m.grain}
                for m in self._reg.values() if m.roles & p.role_ids]

    def get(self, principal, metric_id, params=None) -> dict:
        p = self._principal(principal)
        m = self._reg.get(metric_id) if isinstance(metric_id, str) else None
        if m is None:
            raise MetricError("MET-001")
        if not (m.roles & p.role_ids):
            raise MetricError("MET-002")
        params = self._check_params(m, params)
        window = parse_window(m.grain, params)

        events, seen = [], set()
        for e in self._load(p.tenant_id):
            if not isinstance(e, dict) or e.get("tenant_id") != p.tenant_id:
                raise MetricError("MET-004")
            if e.get("event_id") in seen or e.get("type") not in m.sources:
                continue
            seen.add(e.get("event_id"))
            events.append(e)
        try:
            watermark = max((e["sequence"] for e in events), default=0)
        except (KeyError, TypeError):
            raise MetricError("MET-006") from None

        key = (m.id, json.dumps(params, sort_keys=True))
        hit = self._cache.get(p.tenant_id, {}).get(key)
        if hit and hit[0] == watermark:
            return dict(hit[1], cached=True)

        raw = m.formula(events, window, params.get("currency"))
        result = {"metric_id": m.id, "label_key": m.label_key, "unit": m.unit, "grain": m.grain,
                  "params": params, "currency": params.get("currency"),
                  "value": quantize(raw, params["currency"]) if m.unit == "money" else int(raw),
                  "watermark": watermark, "event_count": len(events), "cached": False}
        self._cache.setdefault(p.tenant_id, {})[key] = (watermark, result)
        return result

    @staticmethod
    def _principal(principal) -> Principal:
        if not isinstance(principal, Principal) or not principal.tenant_id or not principal.user_id:
            raise MetricError("MET-007")
        return principal

    @staticmethod
    def _check_params(m, params) -> dict:
        allowed = {"period" if m.grain == "month" else "as_of"}
        if m.unit == "money":
            allowed.add("currency")
        params = {} if params is None else params
        if not isinstance(params, dict) or set(params) != allowed:
            raise MetricError("MET-003")
        if m.unit == "money" and params["currency"] not in MINOR_UNITS:
            raise MetricError("MET-003")
        return dict(params)
