# Model-call interface

Version: 0.2.1
Status: draft
Owner: eldon

How a platform service (Operate, Discovery, the Blueprint factory, evals) asks the model gateway for one model call. Callers depend on this contract, not on gateway internals; the gateway (`services/gateway/`, partner lane) implements it. Schema: [model-call.schema.json](model-call.schema.json). Examples: [request](examples/model-call-request-agent.json), [reply](examples/model-call-reply.json), [budget refusal](examples/model-call-refusal-budget.json), [refusal after dispatch](examples/model-call-refusal-filter-after-dispatch.json). Decision: [ADR-0054](../docs/decisions/ADR-0054-model-call-contract.md). Design background: the model gateway design and ADR-0053 (both Proposed, PLT-009), [prompt-injection-defence](../docs/security/prompt-injection-defence.md) (SEC-003), [ADR-0038](../docs/decisions/ADR-0038-secrets-management.md). A deterministic fake for tests: `services/operate/runtime/model_call_fake.py`.

0.2.0 changes (security review of PR 244): trusted content by reference only, post-dispatch cost committed and metered, identity from the verified principal, namespaced idempotency with re-checks on replay, a UTF-8 byte input bound, a strict schema with closed reasons per code, one generic filter reason, `model_id` removed from the reply, conversation turns and a thread-taint input.

0.2.1 changes (re-review Lows): references scoped to the calling service and run grant, thread-keyed taint, `user` trust needs a user principal, charged fallback reports the charge, 1 MiB cap measured on the unescaped form, malformed input is `invalid_request`, unique ids and tools, actor-scoped idempotency.

## 1. Rules
1. **Tier and purpose, never a model.** A request names a `tier` (`frontier`, `mid`, `small`) and a `purpose` (`chat`, `agent`, `build`, `simulation`, as in `meter.ai_usage`). Fields that name a model, provider or endpoint (`model`, `model_id`, `provider`, `endpoint`), also as `metadata` keys, are refused as `invalid_request` (`model_named`). `code` is never a model tier.
2. **Identity from the verified principal.** The gateway takes tenant, actor kind and id, role ids, session and on-behalf-of from the verified principal of the calling service session (mTLS service identity plus the forwarded user or run token, as in the PLT-025 `GatewayContext`), and `agent_id`, `run_id`, `thread_id` and the tool grant from the signed run token (agent-least-privilege section 2 item 3). The body `caller` is only compared with them: any difference, or an id present on one side only, is `invalid_request` (`caller_mismatch`). Budget layers, metering and idempotency use the principal's values, never the body's; `correlation_id` is the only `caller` field taken from the body. A tenant key outside `caller` (in `metadata` or a block) is `tenant_in_payload`.
3. **No keys in requests.** No provider key, token, `Authorization` value or tenant-supplied key travels in a request; provider keys (S01) are read only by the gateway (ADR-0038).
4. **One call, one result.** The result is either a reply (section 4) or a refusal (section 5). Nothing partial. Before dispatch every refusal releases the whole hold. Once dispatch began the actual cost is committed and metered whatever the result (section 6); only the content is withheld.

## 2. Request
| Field | Req | Meaning |
|---|---|---|
| `kind` | yes | `"request"` |
| `contract_version` | yes | `"0.2.1"` |
| `call_id` | yes | Caller-unique id (`^[A-Za-z0-9_.:-]{1,128}$`) for trace and meter correlation |
| `idempotency_key` | yes | `^[A-Za-z0-9_.:-]{8,128}$`. Section 2.1 |
| `caller` | yes | Compared only (section 1 rule 2): `tenant_id`, `actor_kind` (`user`, `agent`, `system`, `support`), `actor_id`, `correlation_id`, `role_ids`, optional `session_id`, `on_behalf_of`, `agent_id`, `run_id`, `thread_id` |
| `tier`, `purpose` | yes | Section 1 rule 1 |
| `prompt_version` | yes | Release manifest of the platform prompt set; platform blocks and tools resolve in it |
| `blocks` | yes | 1 to 256 ordered blocks (section 3) |
| `tools` | no | Up to 64 tool references: `name`, optional `content_hash`. Specs resolve in the release manifest of `prompt_version` (L0); inline specs are `ref_required` |
| `max_output_tokens` | yes | 1 to 32000. Provider output limit and the output part of the reservation |
| `min_output_tokens` | no | Default = `max_output_tokens`. The gateway may lower the provider limit to what the remaining budget affords, never below this. Above `max_output_tokens` is `invalid_request` (`limit`) |
| `accepts_untrusted` | yes | `false` for a step that must run on a clean context (SEC-003 3.2 item 4, privileged planner) |
| `thread_tainted` | yes | The runtime's thread taint (SEC-003 2.4 rule 4, PI-009). The gateway only ever raises it: it also keeps its own record per (tenant, thread), (tenant, session) and (tenant, run) from the principal and run token, and marks all of them after any tainted reply; a call matching any marked key is tainted, so a new session or a sessionless run on the same thread stays tainted |
| `locale` | no | `ar` or `en` |
| `metadata` | no | Allow-listed trace keys only: `feature`, `step`, `eval_case_id` (ids) and `trace_parent` (W3C). Any other key is `schema` |

The request is at most 1 MiB, measured on its canonical unescaped UTF-8 form (sorted keys, non-ASCII written as UTF-8, not as `\uXXXX` escapes); larger is `schema`. A string with a lone surrogate, nesting too deep to serialize, a duplicate block `content_id` or a duplicate tool name is also `invalid_request` (`schema`); the gateway never errors out on malformed input.

### 2.1 Idempotency
1. The key is scoped to (calling service, tenant, actor kind and id), all from the principal. The same key from another service, tenant or actor is a different key: no conflict, no shared reply.
2. Same scoped key and same canonical body (the whole request, `caller` included, serialized with sorted keys) within 24 h returns the stored reply with `replayed: true` and no second dispatch, charge or meter event. A different body is `idempotency_conflict`.
3. A replay re-checks the kill switch, the secret filter feed and the output filter on the stored reply (fingerprints may have changed). Any of these failing refuses the replay as for a new call; nothing is charged.
4. A key whose first call is still in flight is refused (`idempotency_in_flight`); the caller retries after the first call ends. The gateway holds the key under a lock for the life of the call.
5. Refusals are not stored, so a retry may succeed (and, after dispatch, is charged again).
6. Stored replies are held 24 h, then deleted; they are classed as the highest `data_class` in the request, encrypted under the tenant's key (data-classification), never read across the (service, tenant) scope, and deleted at tenant offboarding with other tenant data.

## 3. Prompt blocks and untrusted content (SEC-003)
Each block is a context item with its trust envelope as metadata, never as a marker inside text. Three shapes:
- **Platform (L0), by reference:** `content_id`, `trust: "platform"`, `data_class` (`C0` or `C1` only), optional `content_hash`. Resolved in the release manifest of `prompt_version` (set by the build pipeline, SEC-003 2.1); that release must be active for the calling service identity, else `ref_mismatch`.
- **Tenant configuration (L1), by reference:** `content_id`, `trust: "tenant_config"`, `data_class`, `revision_id`, optional `content_hash`. Resolved in the tenant's applied Blueprint revision (control plane); `revision_id` must be the applied one.
- **Conversation item (L2 or L3):** `content_id`, `trust` (`user` or `untrusted`), `role` (`user`, `assistant`, `tool`), `turn` (0 to 1023), `text` (at most 262144 characters), `data_class` (`C0`..`C3`), for `untrusted` also `source` (non-empty: connector, tool and audit id, or `model_output`), plus optional `parents` (at most 32), `transform`, `flags` (at most 16), `content_hash`.

Rules:
- **References are scoped to the caller.** Only a `prompt_version` active for the calling service identity resolves (a retired or other service's release is `ref_mismatch`). Offered tools are the intersection of the manifest's tools and the run-token tool grant; a tool outside the grant is `ref_mismatch`, so a caller cannot be offered `payroll.run` because the manifest has it.
- **No inline trusted text.** A platform or tenant-config block with `text`, or an inline tool spec, is `ref_required`. An unknown reference is `unknown_ref`. A `content_hash` (`sha256:` + hex of the UTF-8 content; for a tool, of its canonical JSON) or `data_class` that differs from the resolved entry, or a stale `revision_id`, is `ref_mismatch`. So no caller can place its own text at L0 or L1, or in the cross-tenant L0 cache prefix.
- **Order is fixed:** all platform, then all tenant-config, then conversation items with non-decreasing `turn`. Otherwise `block_order`. This is also the prompt-cache prefix order (ADR-0053 item 5): L0 is shared across tenants, L1 starts with a per-tenant marker the gateway adds.
- **Turns keep their own trust.** User and untrusted items interleave by turn, so history is never pushed into `user` items. `assistant` and `tool` items are always `untrusted` (model output and tool results are L3); a `user` item may be `untrusted` (pasted payload, SEC-003 2.1 rule 4). A `user` item needs a principal that is a user (`actor_kind: user`) or acts `on_behalf_of` one; otherwise `caller_mismatch`. The `trust` and `data_class` labels of conversation items stay caller-asserted: the caller is accountable for them (a tool result labelled `user`, or C3 text labelled C0, is the caller's defect, caught by its own review and the SEC-003 tests, not by the gateway).
- A block with a missing or unknown `trust` is refused (`missing_trust_label`), per SEC-003 2.3. The gateway never guesses a level and never raises one.
- The gateway, not the caller, wraps each `untrusted` item in a quoted data section with a per-call random delimiter and escapes the delimiter inside the data (SEC-003 3.2). A caller that pre-formats prompts by string concatenation is a defect.
- `accepts_untrusted: false` with any `untrusted` block is `injection_tainted`. The reply is `tainted: true` when any block is untrusted or the thread is tainted (input or the gateway's own record).
- **Secret filter.** The gateway scans every string in the request, the resolved platform, tenant-config and tool content, the assembled prompt as sent, and the conversation texts joined without separators (secrets split across items), then the output (text and tool-call arguments). Any hit is `filter_blocked` with the one generic reason `flagged`, whether the hit was in prompt or output, pattern or fingerprint (ADR-0038, SEC2-T37).

## 4. Reply
`kind: "reply"`, `call_id`, `idempotency_key`, `tier` (the tier served, never weaker than requested), `text` (at most 262144 characters), `tool_calls` (at most 64: `id`, `name`, `arguments`, arguments at most 64 KiB serialized), `stop_reason` (`end`, `max_output`, `tool_use`), `trust: "untrusted"` (model output is always L3), `tainted`, `usage` (`input_tokens`, `output_tokens`, `cached_tokens`, `cost_micro_usd`, bounded integers), `attempts`, `fallback_used`, `meter_event_id`, `replayed`. The model id is not in the reply; it stays in the trace and the meter event (ADR-0010, ADR-0016).

## 5. Refusals
`kind: "refusal"`, `call_id`, `code`, `reason`, `retryable`, `reservation_released`. `call_id` is the request's when it matched the id pattern, otherwise `null`; a refusal carries no other caller text. `reservation_released: true` means nothing was charged; `false` means dispatch began (also on an earlier fallback attempt) and the actual cost was committed and metered. Any code can follow a charged attempt, so `false` is valid for `budget_refused` after a charged fallback. The codes and the reasons per code are closed (the schema enforces each pair); callers map every code, and an unknown code is handled as non-retryable.

| Code | Reasons | Retryable | When |
|---|---|---|---|
| `budget_refused` | `exceeded`, `policy_missing`, `meter_unavailable`, `layer_unbound` | no | Reservation would cross any budget layer; a layer has no policy; the meter store is unreachable (ALP-032); a configured layer has no id in the principal or run token |
| `kill_switch_engaged` | `engaged`, `unreachable` | no | AI kill switch on for the platform or tenant, or the flag cannot be read (ALP-036); also checked on replay |
| `region_policy_refused` | `policy_missing`, `data_class_not_allowed`, `no_allowed_endpoint` | no | The tenant's market policy is missing, or forbids a block's data class leaving the country, or leaves no admitted endpoint for the tier |
| `model_unavailable` | `chain_exhausted` | yes | Every same-or-stronger admitted entry failed on transport (charged only if an attempt timed out after send) |
| `invalid_request` | `schema`, `model_named`, `caller_mismatch`, `tenant_in_payload`, `missing_trust_label`, `block_order`, `ref_required`, `unknown_ref`, `ref_mismatch`, `idempotency_conflict`, `idempotency_in_flight`, `limit` | no | The request breaks sections 1 to 3; `limit` is `min_output_tokens` above `max_output_tokens` |
| `injection_tainted` | `untrusted_not_accepted` | no | Untrusted content in a call that declared `accepts_untrusted: false` |
| `filter_blocked` | `flagged`, `filter_unavailable` | no | Secret filter hit on prompt or output (released `false` after dispatch), or its feed is stale |

Refusal text and codes never contain provider text, model ids or prompt content. Customer-facing surfaces map them through i18n.

## 6. Budget reservation (reserve, then commit; fail closed)
1. Before dispatch the gateway bounds input tokens by everything sent: the UTF-8 bytes of the assembled prompt (resolved blocks, data wrappers and delimiters, tool specs) plus a fixed framing allowance per block and per tool, or the provider's own token count when it has one. A byte bound holds for byte-level tokenizers (no token is shorter than one byte; UNVERIFIED for every admitted provider, checked per entry at admission). It reserves `cost(input_bound, output_limit)` at the selected entry's price against every configured layer: platform >= tenant >= session >= agent grant >= run. A lower layer only tightens. All layers are reserved atomically or none.
2. `output_limit` starts at `max_output_tokens`; if that does not fit, it drops to the largest affordable value. Below `min_output_tokens` the call is refused (`budget_refused`, `exceeded`) with nothing reserved.
3. Dispatch begins when the request is sent to a provider. From then on the actual cost is committed and metered: on a reply, on withheld output (`filter_blocked`, `flagged`) and on a timeout after send (charged at the hold, since the provider may bill). A transport failure where the provider received nothing (connection refused, 429 or overload before acceptance) releases the hold. Each reservation ends exactly once, `committed` or `released`; a hold not ended within its TTL is released by the gateway.
4. If the provider-reported actual cost exceeds the hold, the gateway still commits the actual cost (the spend is real), records an overrun alert, and the layers may sit above their caps by that overrun; every later reservation on those layers is then refused until the window resets.
5. A fallback attempt ends the previous hold as in item 3 and reserves again at the new entry's price. If an earlier attempt was charged (timeout after send) and the next reservation fails, the refusal (`budget_refused`, or `model_unavailable`) reports `reservation_released: false`: something was committed and metered.
6. Concurrent calls count each other's holds, so they cannot jointly cross a cap except by overruns under item 4.

## 7. Fallback (ADR-0053 item 3)
Only on transport failure (timeout, connection error, provider 5xx, 429 or overload); never on a provider refusal, filter block or schema failure. The next entry must be the same tier or stronger, eval-admitted and allowed by the tenant's region policy; never a weaker tier, shorter context or skipped filter (ALP-034). At most 3 attempts per call. Each fallback is logged with its reason class and sets `fallback_used`. Chain exhausted: `model_unavailable`, no partial answer.

## 8. Metering
One Contract 4 `meter.ai_usage` event per committed reservation ([events.md](events.md) section 3; built by PLT-025 `build_ai_usage_event`): a reply, withheld output or a timed-out attempt. `data_class: operational`, `tenant_id` and `actor` from the verified principal, `correlation_id` from `caller.correlation_id`, `trace.model_id` and `trace.prompt_version`. `data` = `model_id`, `tier`, `input_tokens`, `output_tokens`, `cached_tokens`, `cost_micro_usd`, `purpose`, `agent_id` (from the run token). No event for a refusal before dispatch or an idempotent replay. No new usage event type. No prompt or output text in the event.

## 9. Versioning
Rules of [contracts/README.md](README.md). Callers send `contract_version`; the gateway refuses a version it does not support (`invalid_request`, `schema`). 0.2.0 is a breaking change from 0.1.0 (draft; no caller ships 0.1.0).
