# ADR-0054: Model-call interface contract

Status: Proposed
Owner: eldon
Approved by: pending (partner review as gateway owner; security review by a different model, RULES 42)

## Context
Q-127 option A (GOV-058) moved the gateway rows (PLT-009, PLT-010, PLT-011, PLT-021) to the partner and made Eldon rows (SEC-009, BPL-017, OPR-013) depend on a model-call contract instead (PLT-026). The gateway design for PLT-009 (ADR-0053, Proposed) sketches the caller interface in its section 9 and says freezing it is a contract change with its own ADR. SEC-003 section 2.2 says the contract that carries trust envelopes needs an ADR. ADR-0038 keeps provider keys in the gateway only. The founder answers of 2026-11-26 (Q-671 PD status, Q-672 identity and cache hits, Q-679 late replies and overruns) on PR 355 and the partner reviews of PR 368 led to 0.3.0.

## Decision
1. Add [contracts/model-call.md](../../contracts/model-call.md) 0.3.0 with [model-call.schema.json](../../contracts/model-call.schema.json) and examples. Callers name a tier and purpose, never a model; caller identity comes from the verified principal and the signed run token (the body `caller` is only compared); prompt blocks carry SEC-003 trust envelopes in a fixed order (platform, tenant config, then conversation turns); no keys in requests.
2. Budgets are reserve then commit across nested layers, fail closed; the gateway may lower the output limit to what the budget affords, never below the caller's `min_output_tokens`. Once dispatch began the actual cost is committed and metered even when output is withheld; the input bound counts everything sent in UTF-8 bytes.
3. The refusal set is closed: `budget_refused`, `kill_switch_engaged`, `region_policy_refused`, `model_unavailable`, `invalid_request`, `injection_tainted`, `filter_blocked`, each with a closed set of reasons. Only `model_unavailable` is retryable. A secret-filter hit has one generic reason (`flagged`, ADR-0038).
4. Metering stays the existing `meter.ai_usage` event: one per committed reservation (a reply, withheld output, a timed-out attempt, a late reply), plus one zero-cost event with `data.cache_hit: true` per response-cache hit, which has no reservation; none for refusals before dispatch or idempotent replays.
5. A block without a trust label is refused (SEC-003 2.3), not silently treated as untrusted.
6. Platform (L0) and tenant-config (L1) content and tool specs travel by reference only (`content_id` in the release manifest of `prompt_version`, or in the applied revision), with an optional `content_hash` the gateway verifies; platform blocks are C0 or C1. No caller can place its own text at L0 or L1.
7. Idempotency keys are scoped to (service, tenant) from the principal; a replay re-checks the kill switch and the output filter; an in-flight key is refused; stored replies are kept 24 h, classed and encrypted per tenant.
8. Conversation items carry `role` and `turn` with their own trust; the request carries `thread_tainted`, which the gateway only raises.
9. 0.2.1 (re-review Lows): references resolve only for a release active for the calling service and tools within the run-token grant; taint is recorded per thread, session and run; a `user` block needs a user principal and the caller is accountable for conversation labels; a charged fallback that ends in refusal reports `reservation_released: false`; the 1 MiB cap is on the unescaped UTF-8 form; malformed input, duplicate `content_id` and duplicate tools are `invalid_request`; idempotency is also scoped to the actor.
10. Eldon-lane callers test against the deterministic fake `services/operate/runtime/model_call_fake.py`. The partner's gateway implements the contract; this ADR does not change `services/gateway/`.

## Alternatives rejected
- Callers keep importing `gateway` internals (today's `gateway_port.py`): couples Eldon rows to partner-lane code and leaves no frozen surface while PLT-009 is built.
- Missing trust label treated as untrusted and allowed: silent; refusing finds the caller bug.
- Open-ended error strings: callers cannot map them fail closed.

## Consequences
- Eldon rows can build and test without the live gateway. The partner's PLT-009 must conform, or propose a contract change by ADR.
- `gateway_port.py` keeps working unchanged; moving it onto this contract is a follow-up once the gateway implements it.
- Needed: the partner's Tier 3 acceptance of 0.3.0 (PR 368), and alignment of the model gateway design and ADR-0053 with 0.3.0 (PLT-033, partner).
- 0.2.0 (security review of PR 244) is breaking against 0.1.0; no caller shipped 0.1.0. 0.3.0 is source-breaking against 0.2.1 (`contract_version` value, required reply `cache_hit`), allowed while the major is 0; no caller shipped 0.2.1.
- 0.3.0 adds: the `pd` and `pd_none` flags with unreadable counted as PD, `pd_not_allowed`, `data_class_above_grant`, `output_schema` by reference, the human memberRef plus `token_id`, metered cache hits keyed at least on prompt, tier, prompt version, locale, output limit, model id and routing-table version, a reservation TTL floor, late replies as overruns, and overrun recorded per tenant so one tenant's overrun never blocks the platform layer for others.
- The gateway's `build_ai_usage_event` cannot yet emit `data.cache_hit`; the partner adds a row for it (partner lane). The `redact` transform is not in 0.3.0; PLT-033 designs it.
- Open: the byte input bound is conservative only for byte-level tokenizers (UNVERIFIED per provider; checked at eval admission). The timeout-after-send charge assumes the provider may bill (UNVERIFIED per provider).

## Supersedes
none
