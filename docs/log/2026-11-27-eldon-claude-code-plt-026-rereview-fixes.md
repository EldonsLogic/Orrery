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

## Next step
Open: `contracts/model-call.schema.json` should encode the token_id rule (if/then) and its x-validator-rule wording; ADR-0054 still says 0.2.1; contracts/events.md table should list `cache_hit`. Partner: re-review PR 368, then PLT-033.
