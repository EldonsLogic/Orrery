# Session log: web-020-studio-plugged-engine

Date: 2026-11-17
Author: eldon
Tool and model: claude
Plan IDs: WEB-020,BPL-012

## Summary
Ran the Studio against the partner's BPL-012 adapter (PR #77, checked out in a throwaway worktree, not merged by me): the conformance suite passes (208 tests) and the Studio compiled and applied the trading Blueprint through it: 85 of 85 steps applied, export hash matched the preview, three approvals granted. One real gap found: the adapter rejects the `attachment` field type (the fake does too), so the Studio's plugged-engine apply now retries once without attachment fields when the preview is rejected and reports `droppedFields` (1 here). The Blueprint fixture and the real engine disagree on `attachment`; that is a BPL-027 integration item, and the capabilities call cannot list unsupported value types (contract 0.1.2; Q-82).

Finding to state plainly: #77's adapter stores state in SQLite and does not import or drive a real Frappe bench. It passes the contract tests, but it is not yet connected to the real engine. Nothing in this repo applies a Blueprint to a real ERPNext site yet.

Model and prompt: Claude (this session); small patch to `services/studio/session.py` plus a test. 70 Studio tests pass.

## Files touched
- services/studio/session.py: plugged-engine retry without attachment fields
- services/studio/tests/test_studio_plugged_engine.py: new

## Decisions
- None.

## Tokens or cost
Unknown or approximate, if known.

## Next step
BPL-027: compile and apply through the adapter on a real bench; decide `attachment` support (engine or Blueprint); expose unsupported value types in capabilities.
