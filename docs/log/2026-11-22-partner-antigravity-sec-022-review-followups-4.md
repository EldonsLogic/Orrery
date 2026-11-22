# Session log: sec-022-review-followups-4

Date: 2026-11-22
Author: partner
Tool and model: antigravity (Gemini)
Plan IDs: SEC-022,BPL-032

## Summary
Closed Eldon's Medium and three Low follow-up findings from the #261 reviews: added shared case- and whitespace-insensitive fail-closed `is_locked_doctype` across the direct apply engines and adapter mapping, enforced plan-time `definition.target` validation on link `field.add` and `relation.*` steps, refused `field.*`/`relation.*` steps with more than one parent, pinned the non-`/entities/<id>` pointer fail-closed branch, and updated ADR-0051.

## Files touched
- `apps/engine/change_engine/change_engine/guarded_apply/safety_guardrails.py`: added `_normalize_doctype_name` and shared fail-closed `is_locked_doctype(name, extra_locked=None)`; switched Tier 0 lock and restricted Link target checks to use it.
- `apps/engine/change_engine/change_engine/guarded_apply/workflow_engine.py`: replaced exact-match `TIER_0_PROHIBITED_WORKFLOW_DOCTYPES` check with `is_locked_doctype(target_dt, TIER_0_PROHIBITED_WORKFLOW_DOCTYPES)`.
- `apps/engine/change_engine/change_engine/guarded_apply/report_engine.py`: replaced ad-hoc lowercase loop with `is_locked_doctype(rd.ref_doctype, PROHIBITED_REPORT_DOCTYPES)`.
- `apps/engine/change_engine/change_engine/adapter/mapping.py`: reused `is_locked_doctype` in `is_protected_entity` and updated the lines 128-130 plan-time grammar coverage comment.
- `apps/engine/change_engine/change_engine/adapter/engine.py`: in `_judge`, required `len(parents) == 1` on `field.*`/`relation.*` steps and validated `definition.target` on link `field.add` and `relation.*` steps (and `/target` property updates) with `is_valid_entity_id` (`unsupported_value_type`) and `is_protected_entity` (`protected_subject`).
- `apps/engine/change_engine/change_engine/tests/test_sec_022_review_followups_4.py`: added 14 tests (201 subtests) covering all 4 findings, controls, non-strings, both adapters, and zero engine writes on refusal.
- `.github/workflows/tests.yml`: listed `test_sec_022_review_followups_4.py` literally in the SEC-022 offline test step.
- `docs/decisions/ADR-0051-adapter-role-and-state-namespacing.md`: updated Proposed ADR item 3 to record the shared `is_locked_doctype` coverage, single-parent enforcement, non-`/entities/<id>` refusal, and link/relation `definition.target` checks.

## Verification
- Tests-first RED run on `test_sec_022_review_followups_4.py` before edits: `121 failed, 12 passed, 57 subtests passed`.
- After edits, `test_sec_022_review_followups_4.py`: `14 passed, 201 subtests passed`.
- Full engine + security suite (21 test modules: new module, SEC-022, BPL-027 offline, BPL-008, BPL-012, ERP-012, ERP-020, ERP-021, ERP-023, ERP-027, phase2/phase3, CE-SEC mocks): before `460 passed, 11 skipped, 1032 subtests passed`; after `474 passed, 11 skipped, 1233 subtests passed`.
- Standalone `test_phase4_report.py`: `10 passed, 1 failed` (unchanged pre-existing policy-store fixture failure in `test_9_cross_doc_policy_passes_submitted_linked_doc`, noted in `.github/workflows/tests.yml`).
- Conformance harnesses: in-memory `208 passed`, Frappe (`CHANGE_ENGINE_ENV=test`) `208 passed` (both unchanged from baseline).
- Mutation check (replacing `is_locked_doctype` with exact-match comparison across `safety_guardrails`, `workflow_engine`, `report_engine`, `mapping`): `66 failures` in `TestSharedLockedDoctypeHelper`.

## Decisions
- Updated Proposed [ADR-0051](../decisions/ADR-0051-adapter-role-and-state-namespacing.md) in place to state the follow-up 4 coverage.

## Tokens or cost
Unknown.

## Next step
Cross-model security review and Eldon's Tier 3 line-by-line review of this PR (`SEC-022`, `BPL-032`).
