# ADR-0054: Model-call interface contract

Status: Proposed
Owner: eldon
Approved by: pending (partner review as gateway owner; security review by a different model, RULES 42)

## Context
Q-127 option A (GOV-058) moved the gateway rows (PLT-009, PLT-010, PLT-011, PLT-021) to the partner and made Eldon rows (SEC-009, BPL-017, OPR-013) depend on a model-call contract instead (PLT-026). The gateway design for PLT-009 (ADR-0053, Proposed, not yet on main) sketches the caller interface in its section 9 and says freezing it is a contract change with its own ADR. SEC-003 section 2.2 says the contract that carries trust envelopes needs an ADR. ADR-0038 keeps provider keys in the gateway only.

## Decision
1. Add [contracts/model-call.md](../../contracts/model-call.md) 0.1.0 with [model-call.schema.json](../../contracts/model-call.schema.json) and examples. Callers name a tier and purpose, never a model; caller identity comes from the verified session; prompt blocks carry SEC-003 trust envelopes in a fixed order (platform, tenant config, user, untrusted); no keys in requests.
2. Budgets are reserve then commit across nested layers, fail closed; the gateway may lower the output limit to what the budget affords, never below the caller's `min_output_tokens`.
3. The refusal set is closed: `budget_refused`, `kill_switch_engaged`, `region_policy_refused`, `model_unavailable`, `invalid_request`, `injection_tainted`, `filter_blocked`. Only `model_unavailable` is retryable.
4. Metering stays the existing `meter.ai_usage` event, one per committed call, none for refusals or idempotent replays.
5. A block without a trust label is refused (SEC-003 2.3), not silently treated as untrusted.
6. Eldon-lane callers test against the deterministic fake `services/operate/runtime/model_call_fake.py`. The partner's gateway implements the contract; this ADR does not change `services/gateway/`.

## Alternatives rejected
- Callers keep importing `gateway` internals (today's `gateway_port.py`): couples Eldon rows to partner-lane code and leaves no frozen surface while PLT-009 is built.
- Missing trust label treated as untrusted and allowed: silent; refusing finds the caller bug.
- Open-ended error strings: callers cannot map them fail closed.

## Consequences
- Eldon rows can build and test without the live gateway. The partner's PLT-009 must conform, or propose a contract change by ADR.
- `gateway_port.py` keeps working unchanged; moving it onto this contract is a follow-up once the gateway implements it.
- Needed: partner review, security review, alignment with ADR-0053 when it is accepted.

## Supersedes
none
