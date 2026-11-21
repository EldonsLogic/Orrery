# Model-call interface

Version: 0.1.0
Status: draft
Owner: eldon

How a platform service (Operate, Discovery, the Blueprint factory, evals) asks the model gateway for one model call. Callers depend on this contract, not on gateway internals; the gateway (`services/gateway/`, partner lane) implements it. Schema: [model-call.schema.json](model-call.schema.json). Examples: [request](examples/model-call-request-agent.json), [reply](examples/model-call-reply.json), [refusal](examples/model-call-refusal-budget.json). Decision: [ADR-0054](../docs/decisions/ADR-0054-model-call-contract.md). Design background: the model gateway design and ADR-0053 (both Proposed, PLT-009), [prompt-injection-defence](../docs/security/prompt-injection-defence.md) (SEC-003), [ADR-0038](../docs/decisions/ADR-0038-secrets-management.md). A deterministic fake for tests: `services/operate/runtime/model_call_fake.py`.

## 1. Rules
1. **Tier and purpose, never a model.** A request names a `tier` (`frontier`, `mid`, `small`) and a `purpose` (`chat`, `agent`, `build`, `simulation`, as in `meter.ai_usage`). Fields that name a model, provider or endpoint (`model`, `model_id`, `provider`, `endpoint`) are refused as `invalid_request`. `code` is never a model tier.
2. **Identity from the session.** `caller` is stamped by the calling service from the verified principal (the PLT-025 `GatewayContext`), never from user, model or document content. The gateway refuses a `caller` that does not match the authenticated service session, and any tenant key outside `caller` (for example in `metadata`).
3. **No keys in requests.** No provider key, token, `Authorization` value or tenant-supplied key travels in a request; provider keys (S01) are read only by the gateway (ADR-0038). Secret-looking content in any block is refused as `filter_blocked`.
4. **One call, one result.** The result is either a reply (section 4) or a refusal (section 5). Nothing partial. Every refusal is fail closed: nothing is dispatched or, if dispatch began, nothing is returned and the reservation is released.

## 2. Request
| Field | Req | Meaning |
|---|---|---|
| `kind` | yes | `"request"` |
| `contract_version` | yes | `"0.1.0"` |
| `call_id` | yes | Caller-unique id of this call (trace and meter correlation) |
| `idempotency_key` | yes | 8 to 128 chars. Same key and same canonical body inside 24 h returns the first reply with no second dispatch, charge or meter event; same key with a different body is `invalid_request` (`idempotency_conflict`). Refusals are not stored, so a retry may succeed |
| `caller` | yes | `tenant_id`, `actor_kind` (`user`, `agent`, `system`, `support`), `actor_id`, `correlation_id`, `role_ids`, optional `session_id`, `on_behalf_of`, `agent_id`, `run_id` |
| `tier`, `purpose` | yes | Section 1 rule 1 |
| `prompt_version` | yes | Version of the platform prompt set (traces and evals) |
| `blocks` | yes | Ordered prompt blocks (section 3) |
| `tools` | no | Tool specs from L0 or L1 only: `name`, `description`, `input_schema` |
| `max_output_tokens` | yes | 1 to 32000. Provider output limit and the output part of the reservation |
| `min_output_tokens` | no | Default = `max_output_tokens`. The gateway may lower the provider limit to what the remaining budget affords, never below this |
| `accepts_untrusted` | yes | `false` for a step that must run on a clean context (SEC-003 3.2 item 4, privileged planner) |
| `locale` | no | `ar` or `en` |
| `metadata` | no | Flat string map for tracing; no tenant keys, no content |

## 3. Prompt blocks and untrusted content (SEC-003)
Each block is a context item with its trust envelope as metadata, never as a marker inside `text`.
- Fields: `content_id`, `trust` (`platform` L0, `tenant_config` L1, `user` L2, `untrusted` L3), `text`, `data_class` (`C0`..`C3`), and for `untrusted` also `source` (connector, tool and audit id, or `model_output`), plus optional `parents`, `transform`, `flags`, `content_hash`.
- **Order is fixed:** all `platform`, then `tenant_config`, then `user`, then `untrusted` blocks. Out-of-order blocks are `invalid_request`. This order is also the prompt-cache prefix order (ADR-0053 item 5): L0 is shared across tenants, L1 starts with a per-tenant marker the gateway adds.
- A block with a missing or unknown `trust` is refused (`invalid_request`, `missing_trust_label`), per SEC-003 2.3. The gateway never guesses a level and never raises one.
- The gateway, not the caller, wraps each `untrusted` block in a quoted data section with a per-call random delimiter and escapes the delimiter inside the data (SEC-003 3.2). A caller that pre-formats prompts by string concatenation is a defect.
- `accepts_untrusted: false` with any `untrusted` block is `injection_tainted`. Any `untrusted` block makes the reply `tainted: true`.

## 4. Reply
`kind: "reply"`, `call_id`, `idempotency_key`, `tier` (the tier served, never weaker than requested), `text`, `tool_calls` (`id`, `name`, `arguments`), `stop_reason` (`end`, `max_output`, `tool_use`), `trust: "untrusted"` (model output is always L3), `tainted`, `usage` (`input_tokens`, `output_tokens`, `cached_tokens`, `cost_micro_usd`, integers), `attempts`, `fallback_used`, `meter_event_id`, `model_id` (internal only: traces and meter; never shown to customers, ADR-0010, ADR-0016), `replayed` (true for an idempotent replay).

## 5. Refusals
`kind: "refusal"`, `call_id`, `code`, `reason`, `retryable`, `reservation_released: true`. The set is closed; callers map every code, and an unknown code is handled as non-retryable.

| Code | Reasons | Retryable | When |
|---|---|---|---|
| `budget_refused` | `exceeded`, `policy_missing`, `meter_unavailable` | no | Reservation would cross any budget layer; a layer has no policy; the meter store is unreachable (ALP-032) |
| `kill_switch_engaged` | `engaged`, `unreachable` | no | AI kill switch on for the platform or tenant, or the flag cannot be read (ALP-036) |
| `region_policy_refused` | `policy_missing`, `data_class_not_allowed`, `no_allowed_endpoint` | no | The tenant's market policy is missing, or forbids a block's data class leaving the country, or leaves no admitted endpoint for the tier |
| `model_unavailable` | `chain_exhausted` | yes | Every same-or-stronger admitted entry failed on transport |
| `invalid_request` | `schema`, `model_named`, `caller_mismatch`, `tenant_in_payload`, `missing_trust_label`, `block_order`, `idempotency_conflict`, `limit` | no | The request breaks sections 1 to 3 |
| `injection_tainted` | `untrusted_not_accepted` | no | Untrusted content in a call that declared `accepts_untrusted: false` |
| `filter_blocked` | `secret_in_prompt`, `secret_in_output`, `filter_unavailable` | no | Secret filter (S23 fingerprints) hit on prompt or output, or its feed is stale |

Refusal text and codes never contain provider text, model ids or prompt content. Customer-facing surfaces map them through i18n.

## 6. Budget reservation (reserve, then commit; fail closed)
1. Before dispatch the gateway estimates input tokens (conservative, 3 characters per token) and reserves `cost(estimated_input, output_limit)` at the selected entry's price against every configured layer: platform >= tenant >= session >= agent grant >= run. A lower layer only tightens. All layers are reserved atomically or none.
2. `output_limit` starts at `max_output_tokens`; if that does not fit, it drops to the largest affordable value. Below `min_output_tokens` the call is refused (`budget_refused`, `exceeded`) with nothing reserved.
3. On a reply the gateway commits the actual cost and releases the rest of the hold. On a refusal, transport failure or any error the whole hold is released. Each reservation ends exactly once, `committed` or `released`; a hold not ended within its TTL is released by the gateway.
4. A fallback attempt releases the previous hold and reserves again at the new entry's price.
5. Concurrent calls count each other's holds, so they cannot jointly cross a cap. Overshoot is bounded by the input estimate error only.

## 7. Fallback (ADR-0053 item 3)
Only on transport failure (timeout, connection error, provider 5xx, 429 or overload); never on a provider refusal, filter block or schema failure. The next entry must be the same tier or stronger, eval-admitted and allowed by the tenant's region policy; never a weaker tier, shorter context or skipped filter (ALP-034). At most 3 attempts per call. Each fallback is logged with its reason class and sets `fallback_used`. Chain exhausted: `model_unavailable`, no partial answer.

## 8. Metering
One Contract 4 `meter.ai_usage` event per committed call ([events.md](events.md) section 3; built by PLT-025 `build_ai_usage_event`), `data_class: operational`, `tenant_id` and `actor` from `caller`, `correlation_id` from `caller.correlation_id`, `trace.model_id` and `trace.prompt_version`. `data` = `model_id`, `tier`, `input_tokens`, `output_tokens`, `cached_tokens`, `cost_micro_usd`, `purpose`, `agent_id`. No event for a refusal or an idempotent replay. No new usage event type. No prompt or output text in the event.

## 9. Versioning
Rules of [contracts/README.md](README.md). Callers send `contract_version`; the gateway refuses a major version it does not support (`invalid_request`, `schema`).
