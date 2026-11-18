# services/gateway

Status: development
Owner: partner
Plan ID: PLT-025, PLT-024

Purpose: AI model gateway. Routes model calls by tier, enforces per-tenant and per-session token/cost budgets, calculates deterministic per-call micro-USD spend, and emits Contract 4 `meter.ai_usage` events. Spec: [05-platform](../../docs/specs/05-platform.md), design: [ai-layer](../../docs/architecture/ai-layer.md).

## Implemented (PLT-025)
- `pricing.py`: Deterministic integer pico-USD / micro-USD pricing (`compute_call_cost`, `PriceBook`, `ModelRate`) rejecting floats, booleans, negative counts, and `cached_tokens > input_tokens`.
  - Default tier rates (`frontier` \$5/\$25, `mid` \$3/\$15, `small` \$0.80/\$4 per 1M tokens, cached input at 10% of uncached input) are **UNVERIFIED** strategy assumptions copied from [06-model-strategy](../../docs/strategy/06-model-strategy.md); replace with verified provider rate cards before billing.
- `ulid.py`: Thread-safe pure-stdlib monotonic ULID generator conforming to `contracts/events.md`.
- `metering.py`: Thread-safe `GatewayMeter`, fail-closed `GatewayContext` tenant validation (rejecting `"platform"` and tenant-spoof metadata keys), per-call / per-tenant / per-session (including `purpose="build"` builder session) counters, fail-closed `BudgetPolicy` caps & threshold alerts, and `build_ai_usage_event` emitting Contract 4 `meter.ai_usage` events.
- `router.py`: `MeteredGatewayRouter` wrapping pluggable provider transports with tier routing, pre-flight `precheck_budget`, latency capture, and guaranteed post-transport metering commits.
- `__main__.py`: CLI report summarising synthetic JSONL call logs (`PYTHONPATH=services python3 -m gateway <jsonl_file|-> [--tenant ID] [--session ID]`).

## Implemented (PLT-024): customer-facing API edge, `edge/`
Pure stdlib, no new dependency. `Gateway(routes)` takes our own `/v1/...` routes (handlers that call the engine adapter) and filters every response (ADR-0016).
- `paths.py`: deny by default. Only registered routes under `/v1/` are routable; engine paths, unrouted paths, dot segments, encoded or double-encoded traversal, `;`, backslashes and odd methods all return the same our-404 with no engine body.
- `headers.py`: allow-list for response headers (drops Server, X-Frappe-*, X-Page-Name, Location and the rest); the engine `sid` cookie becomes `__Host-session` (Secure, HttpOnly, SameSite=Lax, no Domain) and every other engine cookie (system_user, full_name, user_id, user_image) is dropped; inbound requests forward only an allow-list (no Authorization, role or X-Forwarded headers) and map our cookie back to the engine's.
- `errors.py`: engine failures become the Tool API error model (`code`, `message_key`, `retryable`, `details`, `audit_id`) from HTTP status and a fixed exception-type table only; no engine text, stack trace or SQL is copied. 3xx redirects are never followed or exposed.
- `markers.py` and `gateway.py`: a success body or allowed header containing an engine marker is replaced by `internal_error` (fail closed); compressed engine bodies are refused (the adapter must request identity encoding); handler exceptions and audit-sink failures also fail closed with no exception text.
- Not here: engine-side Desk disabling (ERP-020), the staging crawl (QA-016), the HTTP server binding and session login (ADR-0007), the real route handlers over the engine adapter, and domain error codes (OPR-018, which will replace `engine_error`). Requests for Eldon's lane: contract section 7 has no `unauthenticated` code, so 401 maps to `permission_denied`.

## Planned for later PLT rows
- Live provider HTTP adapters and fallback chains (`PLT-009`)
- Regional endpoint routing and licence-verified gateway proxy evaluation (`PLT-010`)
- Response/prompt cache and PII redaction filters (`PLT-009`)

## Running tests
```bash
# Pure stdlib unit tests:
PYTHONPATH=services python3 -m unittest discover -s services/gateway/tests -v

# Including Contract 4 evstream schema conformance (requires jsonschema from services/blueprint/requirements.txt):
PYTHONPATH=services:services/blueprint/events python3 -m unittest discover -s services/gateway/tests -v
```
