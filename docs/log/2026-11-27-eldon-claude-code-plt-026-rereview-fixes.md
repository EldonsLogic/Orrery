# Session log: plt-026-rereview-fixes

Date: 2026-11-27
Author: eldon
Tool and model: claude-code (Opus worker)
Plan IDs: PLT-026

## Summary
Fixed the partner's cross-model review of PR 368 at 22a671f7 (1 High, 2 Medium, 2 Low), tests first, after merging main into the branch.

## Files touched
- services/operate/runtime/model_call_fake.py: `cache_hit` moved from `trace` to `data` of `meter.ai_usage`; `token_id` required for a user caller, forbidden otherwise; platform layer counts all spend while under its cap and alerts only on the overrunning call; cache key adds `prompt_version` and `locale`, only `stop_reason: end` replies are cached, a flagged cached text is evicted and refused; no verified principal raises before parsing.
- services/operate/tests/runtime/test_model_call_fake.py: 6 new tests, every emitted event validated with `evstream.validate_event` (cache hit included).
- services/blueprint/events/schemas/data.meter.schema.json: optional boolean `cache_hit` on `ai_usage` (additive, no schema_version bump, events.md section 2).
- contracts/model-call.md: text for the above, Q-672(d), `output_schema_mismatch` in section 6.3, redact pointer to PLT-033.

## Decisions
- `cache_hit` is an additive `data` field, not a `trace` field: Contract 4 `trace` is closed, and an additive data field needs no envelope version.

## Tokens or cost
Unknown.

- Follow-up commit: contracts/model-call.schema.json `caller` if/then (token_id required for a user, forbidden otherwise) and x-validator-rule reworded, reported as `caller_mismatch` by the fake; ADR-0054 (Proposed) names 0.3.0; contracts/events.md `meter.ai_usage` row lists `cache_hit`.

## Next step
Partner: re-review PR 368, then PLT-033.

## Round 2 fixes (partner re-review at 84713c10)
Merged main first; tests written first for each item (7 new, 102 fake tests pass).
- N1 (Medium): overrun is recorded per tenant in the platform ledger; tenant X's platform reservation is decided on total spend minus the overrun of all other tenants, so X pays for its own overrun and never blocks others (tests: A overrun to 99,498 and 99,999 under a 100,000 cap, 20 late replies from A; B gets a reply, A is refused). model-call.md 6.4 rewritten to match Q-679.
- N2 (Low): `platform_over_cap` is raised once, by the commit that crosses the cap; code and 6.4 agree (test).
- N3 (Low): cache key is "at least" and adds the serving model id and the routing-table version; lookups use the head of the current chain (test).
- Q-672(d) nit: the fake records a `no_verified_principal` security event (test).
- `redact`: not in 0.3.0 (schema refuses it as `invalid_request`, `schema`); PLT-033 designs it (test pins it).
- ADR-0054 (Proposed): decision 4 counts one zero-cost metered event per cache hit; Context and Consequences updated to 0.3.0.
