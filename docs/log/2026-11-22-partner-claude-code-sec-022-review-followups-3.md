# Session log: sec-022-review-followups-3

Date: 2026-11-22
Author: partner
Tool and model: claude-code (Claude Sonnet 5.5)
Plan IDs: SEC-022,BPL-032

## Summary
Fixed the four Lows of the Opus review of merged PR #258 (comment "Cross-model security review (Claude Opus 5.5) of aa9ecc3"): the protected-entity check is now case-insensitive, and ADR-0051 records the in-memory residual, the passed live tests and the no-table condition.

## Review Lows
- L2 (pre-existing), case-sensitive protected check: `gl_entry` derived `Gl Entry`, which did not match `GL Entry` in the locked set, though the engine folds case. `mapping.is_protected_entity` now compares case-insensitively against `ZONE_2_LOCKED_DOCTYPES` and `PROTECTED_ENTITY_IDS`. Tests first: `gl_entry`, `GL_ENTRY`, `Gl Entry` protected; every locked doctype under its derived spellings (the acronym names `GL Entry`, `DocPerm`, `DocShare`, `Custom DocPerm` included); `entity.add` and a grant on `gl_entry`, `payment_ledger_entry` and `docperm` blocked at plan time on the in-memory adapter and the offline engine fake. Before the fix: 47 failing subtests in the new module; after: 16 tests pass.
- L1, in-memory residual: recorded in ADR-0051 (grant targets). The L2 fix blocks none of `server_script`, `has_role`, `payment_entry` (not in the locked set); they still plan `gated` in memory and are refused on the engine path.
- L3: ADR-0051 lists the BPL-027 live tests that passed (`test_01`, `01b`, `03b`, `04`, `04b`, `06`, `07`, `08`) and states `test_05` is still the expected failure.
- L4: ADR-0051 states that "allowed" for an own document type also requires that no table exists yet (`frappe_backend.py:1206`).

## Files touched
- apps/engine/change_engine/change_engine/adapter/mapping.py: case-insensitive `is_protected_entity`.
- apps/engine/change_engine/change_engine/tests/test_sec_022_review_followups_2.py: L2 tests.
- docs/decisions/ADR-0051-adapter-role-and-state-namespacing.md: L1, L3, L4 wording.
- docs/log/2026-11-22-partner-claude-code-sec-022-review-followups-3.md: this log.

## Decisions
- None; edits to Proposed ADR-0051. #258 was merged before this work finished, so the fixes go on a new branch and PR.

## Tokens or cost
Unknown.

## Next step
Eldon's line-by-line review (Tier 3); then the open ADR-0051 item 4 follow-ups and BPL-034.

## Review fix (Gemini Hydrogen review of e792eb9)
- Medium, whitespace bypass: `is_protected_entity` now compares a normalised key (stripped, whitespace and underscore runs collapsed, case folded). The plan stage also refuses any entity id outside the Blueprint id grammar `^[a-z][a-z0-9_]{1,63}$` (`contracts/blueprint.schema.json` `$defs/id`) with `unsupported_value_type` (no `invalid_subject` code exists in the plan reason codes, so the existing code for an id outside the grammar is used, as ADR-0051 item 1 does): pointer segment and `entity.add` subject id in `engine.py` `_judge`, role grant targets in `grant_plan_reason`. Inputs `gl_entry `, ` gl_entry`, `gl _entry`, `GL Entry ` and `general_ledger ` are blocked on the in-memory and offline engine-backed adapters; the offline fake is not written.
- Low: the broken sentence in ADR-0051 item 3 is rewritten.
- Tests: `test_sec_022_review_followups_2.py` has a new class for the above (32 subtests failed before the fix, all pass after).
