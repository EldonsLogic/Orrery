# Session log: bpl-017-factory-drafting

Date: 2026-11-23
Author: eldon
Tool and model: claude-code (Opus 5.5, subagent)
Plan IDs: BPL-017

## Summary
First slice of BPL-017 (Eldon approved starting the row on 2026-11-23): a deterministic drafter that turns a schema-checked component request into an AI-drafted candidate component (manifest, code, tests) in the BPL-015 sandbox, through the PLT-026 model-call port (fake port only, no live model). Stacked on PR #244 (PLT-026). Row stays `doing`.

## Files touched
- services/blueprint/factory/drafting.py: request checks (schema, injection, rigid zone, proven plain), one port call (tier mid, purpose build, reserved minimum output), draft checks (closed shape, path check, rigid zone, fixed fields, registry admission), sandbox write outside the repo, BPL-015 check, draft record and one audit record per outcome.
- services/blueprint/factory/request.schema.json: closed request shape (internal input, not a contract).
- services/blueprint/tests/factory/test_drafting.py: 24 tests (injection, ledger, VAT, Arabic tax, payroll, tenant login, unproven need, model refusal, budget exhaustion, writes outside the sandbox, failing draft tests, tests not run without the flag, manifest failing the schema, rigid or malformed drafts, sandbox root in the repo).
- services/blueprint/README.md: short section.
- docs/decisions/ADR-0065 (Proposed) and INDEX; docs/PLAN.md: BPL-017 `doing`.

## Decisions
- [ADR-0065](../decisions/ADR-0065-ai-drafted-components-enter-factory-as-drafts.md) Proposed. ADR-0064 left free for OPR-013, which builds on the same base.

## Checks
- `pytest services/blueprint/tests`: 2105 passed. New file: 24 passed.
- Not checked: a real gateway (none yet); running candidate tests under an OS sandbox (INF-014 does not exist, so the flag stays off for customer-influenced requests).
- CI path filter: the blueprint tests now import `services/operate/runtime/model_call_fake.py`; a change only under services/operate will not re-run them.

## Tokens or cost
Unknown.

## Next step
BPL-017 next slices: the promotion step with a reviewer-not-requester check (ADR-0034), input from an approved BPL-016 record, a real gateway adapter once PLT-009 lands, i18n labels if the codes reach a UI. Real routing of refused requests to a human queue (today only a reason code).
