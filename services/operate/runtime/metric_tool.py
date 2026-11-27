"""ToolPort for `metric.query` (OPR-006 slice 2, docs/product/semantic-layer.md).

The caller's tenant, user and roles come from the verified `ToolRequest`, never from the arguments; an argument
that is not a declared metric parameter is refused (MET-003). The model gets the metric result only, never events.
Refusals become contract errors with a `domain` block from the catalog. Anything else fails closed."""
from __future__ import annotations

from metrics import MetricError, MetricService, Principal
from toolapi.errors import build_error, internal_error, load_catalog

from .models import ToolRequest, ToolResponse

DOMAIN = {
    "MET-001": "metric_unknown",
    "MET-002": "metric_permission_denied",
    "MET-003": "metric_invalid_params",
    "MET-004": "metric_tenant_mismatch",
    "MET-005": "metric_currency_mismatch",
    "MET-006": "metric_bad_event_data",
    "MET-007": "metric_no_principal",
}
_SHOWN = ("metric_id", "label_key", "unit", "value", "currency", "params")


def _err(code: str, message_key: str) -> ToolResponse:
    return ToolResponse(status="error", error={"code": code, "message_key": message_key, "retryable": False, "details": {}})


class MetricToolPort:
    def __init__(self, service: MetricService, inner=None, catalog: dict | None = None):
        self._svc, self._inner, self._catalog = service, inner, catalog or load_catalog()

    def call(self, request: ToolRequest) -> ToolResponse:
        if request.tool != "metric.query":
            if self._inner is not None:
                return self._inner.call(request)
            return _err("unknown_tool", "errors.unknown_tool")
        try:
            args = dict(request.arguments) if isinstance(request.arguments, dict) else {}
            metric = args.pop("metric", None)
            principal = Principal(tenant_id=request.tenant_id, user_id=request.user_id,
                                  role_ids=frozenset(request.role_ids or ()))
            r = self._svc.get(principal, metric, args)
        except MetricError as e:
            return ToolResponse(status="error", error=build_error(DOMAIN[e.code], {}, self._catalog))
        except Exception:  # noqa: BLE001 - fail closed, no detail
            return ToolResponse(status="error", error=internal_error())
        out = {k: r[k] for k in _SHOWN}
        out["metric"] = out.pop("metric_id")
        return ToolResponse(status="ok", result=out)
