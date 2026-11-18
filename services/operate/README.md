# services/operate

Status: draft
Owner: unassigned

Purpose: Part 4. Chat runtime, intent router, per-tenant tool API gateway and generator, semantic layer, approval inbox, report builder, scheduled agents, per-tenant memory. Spec: [04-operate](../../docs/specs/04-operate.md). Contracts: [tool API](../../contracts/tool-api.md), [events](../../contracts/events.md).

Planned contents: tool generator, authorisation gateway (fail closed), semantic layer, agent runner, memory store.

**Empty until gate G1.**

## Tool API generator (OPR-003)
`toolapi/` turns a validated Blueprint into the per-tenant typed tool definitions of [contracts/tool-api.md](../../contracts/tool-api.md): `generate_tool_api(blueprint, registry=None, manifests=None)` (pure, deterministic, refusals coded `TAPI-`), `check_tool_api(defs, registry=None, manifests=None)` (re-checks the hard rules on any set) and a CLI (`--registry`, `--manifest`). Resolved component manifests may declare an entity's `riskClass`, which only raises the reviewed class (ADR-0037).
Risk classes, effects and labels are data in `toolapi/policy.py`. Run: `PYTHONPATH=services/operate python3 -m toolapi services/blueprint/fixtures/trading-distribution.blueprint.json`. Tests: `python3 -m pytest services/operate/tests -q`.

## Agent stream endpoint (OPR-020, ADR-0044)
`agui/` serves `POST /v1/agent/stream` (RunAgentInput in, AG-UI events out as Server-Sent Events). Transport only: tenant and roles come from the verified session, never the body; client `state`, `context`, `forwardedProps` and resume `status`/`payload` are ignored; client tools are refused; only allow-listed events and `Custom` names leave (`events.py`); a resume never approves (the interrupt only displays Tool API pending approvals); every failure goes through the bilingual catalog before `RunError` (`errors.py`); run and `meter.ai_usage` events are written to the Event stream (`audit.py`). `handle_request` is framework-free; `create_app(deps)` imports FastAPI lazily. The agent runtime, token verifier and approval reader are injected ports (`ports.py`); no model calls here. Needs `services/operate` and `services/blueprint/events` on the path. Tests: `python3 -m pytest services/operate/tests/agui -q`.
