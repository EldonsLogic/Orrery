"""Host wiring for `metric.query` (OPR-006 slice 3): one call builds the tool definitions generated with the
metric registry and the ToolPort that executes `metric.query` with the caller's own roles; other tools go to
`inner`. The host passes `defs_for` as `tool_defs` and `port` as `tools` to `chat.loop_runtime_factory`."""
from __future__ import annotations

from metrics import MetricService
from toolapi.generate import generate_tool_api

from .metric_tool import MetricToolPort


def wire_metrics(blueprint, *, metrics: dict, event_loader, inner=None, registry=None, manifests=None):
    """Return `(defs_for, port)`. Raises ValueError when the Tool API does not generate for this Blueprint."""
    res = generate_tool_api(blueprint, registry, manifests, metrics=metrics)
    if not res.ok:
        raise ValueError("tool api generation failed: %d errors" % len(res.errors))
    tools = list(res.tools)
    return (lambda tenant_id: tools), MetricToolPort(MetricService(metrics, event_loader), inner)
