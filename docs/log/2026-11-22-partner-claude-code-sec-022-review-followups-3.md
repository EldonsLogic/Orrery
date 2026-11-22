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

## Fix round 2 (Eldon)
- Author / tool: partner, antigravity (fix for Eldon's Fable 5.2 re-review of `2767110` on PR #261).
- Finding 1 (Medium, unchecked parent on `field.*` and `relation.*` steps): `_judge` in `adapter/engine.py` now extracts `subject.parents[0].id` for every `field.*` and `relation.*` step, checks `is_valid_entity_id` (`unsupported_value_type`), checks `is_protected_entity` (`protected_subject`), and requires `parents[0].id == pointer segment` (`definition_conflict`). Missing/empty parents or non-`/entities/<id>` pointers fail closed (`unsupported_value_type`).
- Finding 2 (Medium, unchecked `definition.entity` on `workflow.upsert` and `report.upsert`): `_judge` now validates `definition.entity` against `is_valid_entity_id` (`unsupported_value_type`) and `is_protected_entity` (`protected_subject`) for both step kinds (required on `workflow.upsert`, optional when omitted on `report.upsert` per the Blueprint schema).
- Finding 3 (Medium, grammar-check test pinning): `test_sec_022_review_followups_2.py` adds non-protected invalid ids (`widget `, `widget\n`, `Widget`, `wid-get`) asserting `reasonCode == "unsupported_value_type"`, asserts exact `reasonCode` on all existing `blocked` tests, and adds pointer/subject mismatch cases. Mutation checks against the fixed module: `fullmatch` -> `match` (16 failures), grant-target -> `isinstance(str)` (28 failures), `entity.add` subject id unchecked (8 removed / 14 skipped grammar), pointer segment unchecked (12 removed / 6 skipped grammar).
- Finding 4 (Low, pointer/subject disagreement on `entity.add`): `_judge` now runs `is_protected_entity` on `subject.id` as well as `segs[1]` and requires `subject.id == segs[1]` (`definition_conflict`).
- Wording: corrected `adapter/mapping.py` lines 128-130 and `docs/decisions/ADR-0051-adapter-role-and-state-namespacing.md` to scope the plan-time grammar claim to the checked paths (noting Link field `target` options are not yet grammar-checked at plan time).
- Tests: `test_sec_022_review_followups_2.py` 64 failures before fix -> 28 tests pass (0 failures) after; SEC-022, BPL-027 offline, BPL-012, BPL-008, ERP-012, ERP-020, ERP-021, ERP-023, ERP-027, CE-SEC mocks: 423 passed, 11 skipped; conformance `make_harness` 208 passed, `make_frappe_harness` (`CHANGE_ENGINE_ENV=test`) 208 passed; `check_docs`, `check_repo_hygiene`, `scan_secrets`, `check_lanes`: clean.
