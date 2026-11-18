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
Pure stdlib, no new dependency. `Gateway(routes, audit_sink=...)` takes our own `/v1/...` `Route`s (a handler that calls the engine adapter, plus a declared response shape) and filters every response (ADR-0016).
- Engine output is never passed through raw. A `Route` declares an allow-listed `schema` (our field names, optionally `Field(spec, source=engine_key)`); `projection.py` parses the engine JSON and builds a new body from the declared fields only, so `doctype`, `docstatus`, `naming_series`, `__onload`, owner and audit columns never appear. Schema keys that are engine field names are refused at registration. A non-JSON route (for example a PDF) must declare `own_content_type`, a security-reviewed statement that its handler's bytes come from our own renderer; the gateway passes them only if the upstream media type matches and uses our own `filename` for Content-Disposition. Anything else (UTF-16/32, gzip with or without a header, HTML, undeclared or non-UTF-8 charset, `Transfer-Encoding`) is refused as `internal_error`.
- `markers.py`: two detectors. Bare words (`frappe`, `desk`...) are checked only on channels the engine controls or that are ours (header values, schema keys); tenant values such as "Caramel Frappe" or "Front desk" are never refused for containing a word. The last-resort check on projected values and on inbound paths matches engine routes (`/app/`, `/printview`, `/api/method`...), module paths (`frappe.client`, `werkzeug.`, `pymysql.`...) and trace fingerprints, also behind HTML or percent encoding. Lists are UNVERIFIED until QA-016.
- `paths.py`: deny by default. Only registered routes under `/v1/` are routable: exact match plus at most `max_params` identifier segments (no dots, so an engine method name is not a parameter). Dot segments, encoded or double-encoded traversal, `%2f`/`%5c`, `;`, backslashes and odd methods return the same our-404.
- `headers.py`: response allow-list is only `Content-Language` and `Vary` (marker-checked). We build Content-Type, ETag (hash of our own body), Content-Disposition and Retry-After ourselves; `Cache-Control: no-store` is always ours. Conditional GETs are answered by the gateway from our ETag (304), not forwarded. Requests forward only `Accept`, `Accept-Language`, `Content-Type`, `Idempotency-Key`; never a cookie, Authorization, role or X-Forwarded header.
- Sessions: **there is no gateway session yet (ADR-0007).** The engine `sid` is never exposed as our session. A live engine `sid` in a response is refused (`internal_error`); a Guest or empty `sid` is ignored; an expired one (the engine logout) becomes `__Host-session=; Max-Age=0`. Any inbound `__Host-session` cookie (valid, empty or duplicated) is rejected with 403 `permission_denied` and cleared. Real issuance, tenant and user binding, and revocation come with ADR-0007; do not read this as the design.
- Audit: the sink is required. A mutating request writes an `intent` record before the handler runs (sink down: the handler never runs, `internal_error`) and an `outcome` record after; reads and denials write the outcome only, and a failed write is an error. If the outcome write fails after a committed mutating effect the real result is returned (a 500 would invite a duplicate) and the record is queued for `drain_unlogged()`. Tenant, user and session fields (tool-api section 8) are added when identity exists.
- `errors.py`: engine failures become the Tool API error model from HTTP status and a fixed exception-type table only (UNVERIFIED, QA-016); no engine text is copied. 405, 413, 417, 422 and ValidationError-style exceptions map to `invalid_arguments`. Error mapping triggers on status >= 400 or `exc`/`exc_type` in a 2xx; `_server_messages` on a successful write is dropped, not an error. 3xx is never followed or exposed. `Retry-After` is our own bounded number in both header and body.
- Not here: engine-side Desk disabling (ERP-020), the staging crawl (QA-016), the HTTP server binding, CORS/preflight and CSRF policy (needed before cookie-authenticated POSTs exist), session login (ADR-0007), the real route handlers over the engine adapter, and domain error codes (OPR-018, which will replace `engine_error`). Requests for Eldon's lane: contract section 7 has no `unauthenticated` code, so 401 maps to `permission_denied`.

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
