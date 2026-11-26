# Session log: opr-006-slice-2-chat-read

Date: 2026-11-26
Author: eldon
Tool and model: claude-code
Plan IDs: OPR-006

## Summary
OPR-006 slice 2 (stacked on #358): `metric.query` is generated from the metric registry and executed with the caller's own roles; MET-* refusals are in the error catalog; metric labels are in the web ar and en messages.

## Files touched
- contracts/tool-api-error-catalog.json: 7 `metric_*` entries, version 0.2.0
- contracts/tool-api.md: version 0.3.2, `metric.query` registry mode
- services/operate/toolapi/generate.py: optional `metrics` registry drives `metric.query` and `requires_by_value`
- services/operate/runtime/metric_tool.py: `MetricToolPort` (caller roles only, result only, catalog errors)
- web/app/messages/{ar,en}.json: `metrics.*` label keys
- services/operate/tests/runtime/test_metric_tool.py, tests/toolapi/test_errors.py: new and updated tests

## Decisions
- Reuse `metric.query`, no new tool; labels in web/app/messages (coordinator, 2026-11-26). Not done: the host does not yet pass the registry to `generate_tool_api` or wrap its ToolPort with `MetricToolPort`; the registry role ids (`finance`, `sales_manager`) do not match the example Blueprint's (`accountant`, `sales_rep`).

## Tokens or cost
Unknown.

## Next step
OPR-006: host wiring (generate with the registry, wrap the ToolPort), role id alignment, vitest key-parity run (no node_modules here).
