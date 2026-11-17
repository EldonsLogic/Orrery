# services/gateway

Status: development
Owner: partner
Plan ID: PLT-025

Purpose: AI model gateway. Routes model calls by tier, enforces per-tenant and per-session token/cost budgets, calculates deterministic per-call micro-USD spend, and emits Contract 4 `meter.ai_usage` events. Spec: [05-platform](../../docs/specs/05-platform.md), design: [ai-layer](../../docs/architecture/ai-layer.md).

## Implemented (PLT-025)
- `pricing.py`: Deterministic integer pico-USD / micro-USD pricing (`compute_call_cost`, `PriceBook`, `ModelRate`) rejecting floats, booleans, negative counts, and `cached_tokens > input_tokens`.
  - Default tier rates (`frontier` \$5/\$25, `mid` \$3/\$15, `small` \$0.80/\$4 per 1M tokens, cached input at 10% of uncached input) are **UNVERIFIED** strategy assumptions copied from [06-model-strategy](../../docs/strategy/06-model-strategy.md); replace with verified provider rate cards before billing.
- `ulid.py`: Thread-safe pure-stdlib monotonic ULID generator conforming to `contracts/events.md`.
- `metering.py`: Thread-safe `GatewayMeter`, fail-closed `GatewayContext` tenant validation (rejecting `"platform"` and tenant-spoof metadata keys), per-call / per-tenant / per-session (including `purpose="build"` builder session) counters, fail-closed `BudgetPolicy` caps & threshold alerts, and `build_ai_usage_event` emitting Contract 4 `meter.ai_usage` events.
- `router.py`: `MeteredGatewayRouter` wrapping pluggable provider transports with tier routing, pre-flight `precheck_budget`, latency capture, and guaranteed post-transport metering commits.
- `__main__.py`: CLI report summarising synthetic JSONL call logs (`PYTHONPATH=services python3 -m gateway <jsonl_file|-> [--tenant ID] [--session ID]`).

## Planned for later PLT rows
- Live provider HTTP adapters and fallback chains (`PLT-009`)
- Regional endpoint routing and licence-verified gateway proxy evaluation (`PLT-010`)
- Response/prompt cache and PII redaction filters (`PLT-009`)
- Customer-facing API path rewriting, header/cookie stripping, and engine error mapping (`PLT-024`)

## Running tests
```bash
# Pure stdlib unit tests:
PYTHONPATH=services python3 -m unittest discover -s services/gateway/tests -v

# Including Contract 4 evstream schema conformance (requires jsonschema from services/blueprint/requirements.txt):
PYTHONPATH=services:services/blueprint/events python3 -m unittest discover -s services/gateway/tests -v
```
