# services/gateway

Status: draft
Owner: unassigned

Purpose: AI model gateway. Routing by tier, per-tenant budgets, caching, regional routing, logging, provider fallback, redaction. Spec: [05-platform](../../docs/specs/05-platform.md), design: [ai-layer](../../docs/architecture/ai-layer.md). Adopt-or-build decision pending a licence check (e.g. LiteLLM; not checked).

Planned contents: router, budget enforcer, cache, redaction filters, provider adapters, model registry loader (`agents/model-registry.md`).

**Empty until gate G1.**
