# Session log: plt-024-gateway-engine-hiding

Date: 2026-11-18
Author: partner
Tool and model: claude-code / sonnet-5.5
Plan IDs: PLT-024

## Summary
Added the customer-facing API edge core in `services/gateway/edge/` (path policy, header and cookie filtering, engine error mapping, marker scrub) with a test table of hostile engine responses; PLT-024 is `doing`, not `done`, because the core has no HTTP binding or real route handlers yet.

## Files touched
- services/gateway/edge/{__init__,markers,errors,paths,headers,gateway}.py: new, pure stdlib (no new dependency or licence).
- services/gateway/tests/test_edge_gateway.py: 14 tests; picked up by the existing CI step that runs `unittest discover -s services/gateway/tests`.
- services/gateway/README.md: PLT-024 section; removed it from "planned".
- docs/PLAN.md: PLT-024 set to `doing`, owner partner.

## Decisions
- Edge lives inside the existing `services/gateway` package (Python, as the rest of services) so CI discovery needs no change.
- Allow-list everywhere (routes, methods, response headers, request headers, cookies); a body or header with an engine marker becomes `internal_error`, never a scrubbed pass-through.
- Own session cookie name `__Host-session` (no Domain, Path=/, Secure).
- No ADR: this implements ADR-0016; the identity ADR-0007 still decides how sessions are created.

## Not done or not verified
- No HTTP server binding, TLS or real route handlers over the engine adapter; tested only with fake upstreams.
- Not tested against a real engine response; the marker list and the exception-type table come from knowledge of the engine's behaviour and are UNVERIFIED until QA-016 (staging crawl) runs.
- Desk disabling on the engine side (ERP-020) and QA-016 untouched.
- Binary bodies are scanned as bytes; compressed bodies are refused, so the adapter must ask the engine for identity encoding.
- Request for Eldon's lane (contracts/tool-api.md section 7, not edited): add an `unauthenticated` error code; today 401 maps to `permission_denied`. OPR-018 will add domain codes replacing `engine_error`.
- Tests were not mutation-checked beyond the table; no cross-model review yet.

## Tokens or cost
Unknown.

## Next step
Review by a different model. Then HTTP binding and route handlers (needs ADR-0007 session decision), ERP-020 and QA-016 run against staging.
