# Session log: plt-024-rereview-n1

Date: 2026-11-18
Author: partner
Tool and model: claude-code / opus-5.5
Plan IDs: PLT-024

## Summary
Fixed the one remaining finding from the cross-model re-review of PR #123 (N1, what was left of H2) and the cheap Low L1. A projected tenant value that mentions a bare engine route inside a sentence ("See /app for details", Arabic text before "/desk", "site-packages") no longer fails the whole list with 500. Values that are engine links (a value that is a route, or a route followed by a path or query such as "/app/customer", "/printview?doctype=x", including HTML- and percent-encoded forms) and stack-trace fingerprints still fail closed. A route schema can no longer read from engine message or exception keys (`_server_messages`, `exc`, `exc_type`, `__onload`, `_debug_messages`, ...). Inbound path checks are unchanged.

## Files touched
- services/gateway/edge/markers.py: value detector split from the path detector (`contains_engine_trace` with `ENGINE_VALUE_RE`); `FORBIDDEN_SOURCES`.
- services/gateway/edge/projection.py: values use `contains_engine_trace`; schema registration refuses forbidden sources.
- services/gateway/tests/test_edge_gateway.py: three tests (route-like tenant values pass in a list; trace fingerprints still refused; forbidden sources refused).
- docs/log/: this log.

## Verified
`PYTHONPATH=services python3 -W error -m unittest discover -s services/gateway/tests`: 49 tests OK (1 skipped, pre-existing).

## Not done
The other re-review Lows (chunked/gzip headers on decoded bodies, in-memory unlogged audit cap, engine document names as values) and the Infos are left for the PLT-024 follow-up; none blocks merge per the re-review. No live engine (QA-016).

## Decisions
- None.

## Tokens or cost
Unknown.

## Next step
Merge after the other founder's review (Tier 2); remaining Lows in a PLT-024 follow-up once the HTTP binding lands.
