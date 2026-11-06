# Event stream

Version: 0.1.0
Status: draft
Owner: eldon

Contract 4. What happened in a tenant, in a form that agents, the audit trail and metering can all consume. Events are facts, append-only, ordered per tenant. Business records live in the engine; events describe changes to them and everything the platform did.

## 1. Envelope
Every event is one JSON object:

```json
{
  "event_id": "01J8ZK3...ULID",
  "type": "sales_order.transitioned",
  "schema_version": 1,
  "occurred_at": "2026-01-01T09:30:00Z",
  "recorded_at": "2026-01-01T09:30:00Z",
  "tenant_id": "t_abc",
  "sequence": 10234,
  "actor": {"kind": "user|agent|system|support", "id": "u_123", "role_ids": ["sales_rep"], "on_behalf_of": null},
  "source": {"service": "operate", "component": "core.sales_order@0.1.3", "blueprint_revision": 12},
  "correlation_id": "chat_turn_8841",
  "causation_id": "01J8ZK2...",
  "subject": {"entity": "sales_order", "id": "SO-00017"},
  "data": {},
  "data_class": "business|personal|financial|operational",
  "trace": {"model_id": null, "prompt_version": null, "tool": "sales_order.transition", "audit_id": "aud_..."}
}
```

### Required fields
`event_id`, `type`, `schema_version`, `occurred_at`, `tenant_id`, `sequence`, `actor`, `source.service`, `correlation_id`, `data`, `data_class`. `subject` is required for record events. `trace` is required when an AI model took part.

### Rules
- `event_id` is a ULID, globally unique; consumers de-duplicate on it (delivery is at-least-once).
- `sequence` is monotonic per tenant. Gaps are an alert.
- `tenant_id` is set by the platform from the authenticated context, never by the producer's payload. No event may mention more than one tenant.
- `data` carries ids and changed values, not whole records, and respects redaction: personal data classes are minimised and, for model-bound consumers, redacted ([ai-layer](../docs/architecture/ai-layer.md)).
- Events are immutable. A correction is a new event with `causation_id` pointing at the original.
- Retention: audit-class events kept for the legal minimum (UNVERIFIED, to be set by [docs/legal](../docs/legal/)); operational events shorter. Tenant export includes the tenant's events.

## 2. Versioning
- `type` names are stable. `schema_version` is an integer per type.
- Additive fields do not bump it. Removing or re-typing a field bumps it and producers emit both versions for one overlap period.
- Consumers ignore unknown fields. Unknown types are stored and skipped, never fatal.
- The registry of types and their JSON Schemas lives under `contracts/events/` (created when the first consumer needs it; empty until gate G1).

## 3. Event types
Naming `<domain>.<past_tense_verb>`.

### Record events (engine facts, emitted by the engine adapter)
`<entity>.created`, `<entity>.updated`, `<entity>.submitted`, `<entity>.cancelled`, `<entity>.transitioned` (data: from, to, transition_id), `<entity>.deleted`, `approval.requested`, `approval.decided` (data: decision, approver, comment), `document.issued` (invoice, with e-invoicing status), `document.rejected_by_authority`.

### Audit events (security and governance)
| Type | When |
|---|---|
| `auth.signed_in`, `auth.sign_in_failed`, `auth.mfa_challenged` | Identity |
| `permission.denied` | Tool or UI check failed |
| `role.assigned`, `role.revoked` | Role changes |
| `tool.called` | Every tool call; data per [tool-api.md](tool-api.md) section 8 |
| `blueprint.change_proposed`, `blueprint.change_approved`, `blueprint.applied`, `blueprint.apply_failed`, `blueprint.rolled_back` | Change path |
| `branding.changed`, `branding.asset_uploaded`, `branding.asset_rejected` | Theming |
| `build.state_changed` (+ `build.review_passed`, `build.review_rejected`, `build.live`, see [build-states.md](build-states.md)) | Build lifecycle |
| `support.access_requested`, `support.access_granted`, `support.access_ended`, `support.action_taken` | Just-in-time support access, always with reason and expiry |
| `data.exported`, `data.deleted`, `tenant.state_changed` | Tenant lifecycle |

### Agent events
`agent.run_started`, `agent.tool_proposed`, `agent.run_completed`, `agent.run_failed`, `agent.budget_exceeded`, `agent.output_flagged` (injection or policy filter hit), `chat.turn_completed` (data: mode discover/ask/act/change, latency, token counts, no content), `memory.written`, `memory.expired`, `eval.regression_detected` (platform-level, not tenant).

### Metering events
Cheap, high-volume, aggregated by Part 5 into usage records.
| Type | Data |
|---|---|
| `meter.ai_usage` | model_id, tier, input_tokens, output_tokens, cached_tokens, cost_micro_usd, purpose (chat/agent/build/simulation), agent_id |
| `meter.active_user` | user_id, day |
| `meter.storage` | bytes by class (records, files, backups) |
| `meter.documents_issued` | doc type, count (for e-invoicing volumes) |
| `meter.connector_run` | connector id, rows, bytes, tier |
| `meter.simulation_run` | records replayed, duration |

### Platform events (no tenant data)
`component.published`, `component.deprecated`, `component.request_created`, `component.request_reviewed`, `engine.upgrade_canary_started`, `engine.upgrade_promoted`, `engine.upgrade_rolled_back`. These carry `tenant_id: "platform"`.

## 4. Consumers
| Consumer | Needs |
|---|---|
| Audit store (Part 5) | All audit and record events, immutable, searchable by tenant, actor, subject |
| Agents (Part 4) | Subscribed record events per tenant for triggers (for example `document.issued` for reminders) |
| Metering (Part 5) | `meter.*` events |
| Reuse metrics (Part 2) | `blueprint.*`, `build.*`, provenance counts, component usage |
| Observability | Operational events, error rates |
| Support console | Read-only view with just-in-time access, every read of tenant events is itself an event |

## 5. Security notes
- Events are tenant data: storage is per-tenant partitioned and encrypted with the tenant's key ([data.md](../docs/architecture/data.md)).
- The AI never reads raw events directly; it gets summaries through a tool, with scope applied.
- Anonymised pattern promotion (library learning) uses aggregates computed from `blueprint.*` and `build.*` events, never record events.
