# Session log: plt-026-model-call-contract

Date: 2026-11-21
Author: eldon
Tool and model: claude-code / opus-5.5
Plan IDs: PLT-026

## Summary
Added the model-call interface contract 0.1.0 (tier and purpose, SEC-003 trust-labelled prompt blocks, reserve-then-commit budgets, a closed refusal set, `meter.ai_usage` metering, ADR-0053 fallback rules) and a deterministic fake port with tests, so Eldon rows (SEC-009, BPL-017, OPR-013) build without the live gateway.

## Files touched
- contracts/model-call.md, contracts/model-call.schema.json, contracts/examples/model-call-*.json: new contract, schema, examples.
- contracts/README.md: contract table row.
- scripts/check_contracts.py: validates the model-call examples (shared path, one line).
- docs/decisions/ADR-0054-model-call-contract.md, docs/decisions/INDEX.md: new Proposed ADR (RULES 42).
- services/operate/runtime/model_call_fake.py: fake port; services/operate/tests/runtime/test_model_call_fake.py: 26 tests (every refusal code and reason, reservation lifecycle, fallback, idempotency, meter event validated against Contract 4).
- docs/PLAN.md: PLT-026 done.

## Decisions
- [ADR-0054](../decisions/ADR-0054-model-call-contract.md) (Proposed): contract shape and closed refusal set. A block with no trust label is refused (SEC-003 2.3), where the PLT-009 design check MG-013 says "treated as L3 and alerted"; the partner should align PLT-009 or raise it.

## Tokens or cost
Unknown.

## Next step
- Partner review of ADR-0054 and security review by a different model (RULES 42).
- PLT-009 (partner) implements the contract in `services/gateway/`; then move `services/operate/runtime/gateway_port.py` onto it (unchanged in this session; its tests still pass).
- Callers: SEC-009, BPL-017, OPR-013 build against `model_call_fake.py`.

## Review fixes (security review of PR 244, contract 0.2.0)
All nine findings fixed, tests first in the fake (68 tests in `test_model_call_fake.py`):
1. Platform and tenant-config blocks and tools by reference (`content_id` in `prompt_version` or the applied `revision_id`, optional verified `content_hash`); platform implies C0/C1; inline text is `ref_required`; unknown or mismatched refs refused.
2. Post-dispatch cost committed and metered (withheld output, timeout after send); `reservation_released` is a boolean.
3. Identity from the verified principal and run token; body `caller` only compared; a configured layer with no id is `layer_unbound`.
4. Idempotency scoped to (service, tenant); canonical body includes `caller`; replay re-checks kill switch and filters; in-flight key refused; retention stated.
5. Input bound = UTF-8 bytes of the assembled prompt (blocks, wrappers, tool specs) plus framing; an actual cost above the hold is committed, recorded and blocks later calls.
6. Strict schema: bounds everywhere, closed reasons per code, metadata allow-list, no `(?i)`, non-empty `source`, `limit` defined, 1 MiB request cap.
7. The fake validates against the schema first; the secret filter scans every string, resolved content, the assembled prompt and joined texts.
8. One generic filter reason `flagged`; ids constrained by pattern and `call_id` echoed only when valid; `model_id` removed from the reply.
9. Conversation items carry `role` and `turn` with their own trust; a `thread_tainted` input, sticky per (tenant, session) in the fake.

The meter test imports `evstream` at module level like `test_trace_gateway.py`, so a missing package fails instead of returning. New example `contracts/examples/model-call-refusal-filter-after-dispatch.json`.
Open (UNVERIFIED, recorded in ADR-0054): the byte bound is proven only for byte-level tokenizers; timeout-after-send billing varies by provider.
