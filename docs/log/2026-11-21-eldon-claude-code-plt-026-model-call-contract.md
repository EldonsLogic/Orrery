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
