# Session log: plt-024-review-fixes

Date: 2026-11-18
Author: partner
Tool and model: claude-code / sonnet-5.5
Plan IDs: PLT-024

## Summary
Fixed the cross-model security review of PR #123 (2 High, 4 Medium, 5 Low): engine bodies are now projected through route-declared allow-list schemas instead of scanned, the session cookie fails closed until ADR-0007, audit is required and written for success and failure. PLT-024 stays `doing` (no HTTP binding or real handlers yet).

## Files touched
- services/gateway/edge/projection.py: new, schema allow-list projection, strict UTF-8 JSON only.
- services/gateway/edge/{markers,headers,errors,paths,gateway,__init__}.py: two detectors (bare words only on engine-controlled channels, strict structure patterns on values and paths), cookie fail-closed, required audit with intent and outcome, ours-wins headers, status mapping, `%2f` and escape fixes.
- services/gateway/tests/test_edge_gateway.py: 46 tests across the gateway suite, escape cases, tenant false positives, sessions, audit.
- services/gateway/README.md: PLT-024 section rewritten.

## Decisions
- `Route(handler, schema | own_content_type)` replaces bare handlers; a non-JSON route's own-renderer declaration is a trust statement needing security review at registration.
- Conditional GET is answered from our own ETag at the gateway (conditional headers are not forwarded), instead of passing an engine 304 through.
- Outcome-audit failure after a committed mutating effect returns the real result and queues the record (`drain_unlogged`); the intent record is the durable trail. Everything else fails closed.
- Not fixed: I2 (HEAD/OPTIONS/CORS policy) and I3 (CSRF) need a policy decision and ADR-0007; section 8 audit fields need identity.

## Not done or not verified
- Marker, route, module and exception tables and the 417 status are UNVERIFIED until QA-016 runs against a live engine.
- No HTTP binding, no real handlers; cross-model re-review of this fix still needed.

## Tokens or cost
Unknown.

## Next step
Re-review of the fixes by a different model; then HTTP binding and handlers after ADR-0007, ERP-020, QA-016.
