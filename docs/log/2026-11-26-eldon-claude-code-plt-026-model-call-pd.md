# Session log: plt-026-model-call-pd

Date: 2026-11-26
Author: eldon
Tool and model: claude-code
Plan IDs: PLT-026

## Summary
Shipped model-call contract 0.3.0 (founder answers on PR 355: Q-671 PD flag, grant ceiling reason, output_schema, pd_not_allowed; Q-672 identity, audit id, cache hits; Q-679 TTL floor, late replies, layered overruns), tests first.

## Files touched
- contracts/model-call.md, contracts/model-call.schema.json, contracts/README.md, contracts/examples/model-call-request-agent.json, contracts/examples/model-call-reply.json: version 0.3.0
- services/operate/runtime/model_call_fake.py and its test: fake port follows 0.3.0 (13 new tests)

## Decisions
- Founder answers on PR 355 (Eldon, 2026-11-26), Q-671, Q-672, Q-679. Choices left to the contract: PD is the reserved flags `pd` / `pd_none` (neither means unreadable, so PD); `output_schema` is by reference; grant ceiling is `invalid_request` `data_class_above_grant`; mismatching output is `filter_blocked` `output_schema_mismatch`.

## Tokens or cost
Unknown.

## Next step
Partner (gateway lane, PLT-009): implement 0.3.0 in services/gateway (PD checks, grant ceiling, output_schema, cache-hit metering, TTL floor, late-reply overrun, platform layer excludes overruns, memberRef plus token_id actor, reject `0.2.1`). Eldon: `redact` transform for Q-674.
