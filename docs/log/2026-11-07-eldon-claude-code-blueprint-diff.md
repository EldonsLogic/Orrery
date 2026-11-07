# Session log: blueprint-diff

Date: 2026-11-07
Author: eldon
Tool and model: claude-code; built by a Sonnet-tier sub-agent from an Opus-written brief, verified by the orchestrator (366 tests, hygiene, no unsafe calls)
Plan IDs: BPL-006

## Summary
Built the Blueprint diff: id-matched structural diff, apply and invert (the undo point), base-hash check, code-computed impact classes and risk summary, explanation data for blueprint.explain_diff, schema and CLI. The code was merged inside PR 29 (Redis licence correction) by mistake of the staging step; this entry records it under its own plan row. Content was verified before merge.

## Files touched
- services/blueprint/diff/ (bpdiff package, README, diff.schema.json), services/blueprint/tests/diff/ (merged in PR 29); services/blueprint/README.md section; docs/PLAN.md: BPL-006 done.

## Decisions
- Diff schema stays in the service; promoting it to contracts/ needs a decision.
- Impact classes are conservative: any added field counts as data_shape; currency and fiscal year count as compliance; order-significant arrays are a judgement (listed in the README).

## Tokens or cost
Unknown or approximate, if known.

## Next step
BPL-011 event stream, BRD-004 tokens after WEB-018 is accepted, BPL-007 (partner) uses the diff.
