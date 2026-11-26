# Session log: opr-006-slice-3-host-wiring

Date: 2026-11-26
Author: eldon
Tool and model: claude-code
Plan IDs: OPR-006

## Summary
OPR-006 slice 3 (stacked on #361): the metric registry uses the Blueprint's real role ids, and a host helper wires `metric.query` end to end (generate with the registry, wrap the ToolPort), tested through a chat turn with a fake model.

## Files touched
- services/operate/metrics/registry.py: roles `finance` -> `accountant`, `sales_manager` -> `sales_rep`
- services/operate/runtime/host.py: `wire_metrics` returns the tool defs function and the `MetricToolPort`
- services/operate/tests/chat/test_metric_host.py: end-to-end chat turn, permitted and non-permitted role
- services/operate/tests/runtime/test_metric_tool.py: role expectations updated

## Decisions
- Role ids are open per Blueprint; the ids come from `contracts/examples/blueprint-trading-minimal.json` (owner, accountant, sales_rep). The trading template also has `general_manager`, `branch_sales_manager`, `auditor`; not added, no invented roles. Whether `sales_rep` should read company revenue is a product call (sales_rep is scoped to own records in the template); flagged for the reviewer.

## Tokens or cost
Unknown or approximate, if known.

## Next step
OPR-006: a real operate host entrypoint should call `wire_metrics` (none exists yet); vitest key-parity run.
