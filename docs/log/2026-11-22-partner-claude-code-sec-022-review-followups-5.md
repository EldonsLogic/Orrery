# Session log: sec-022-review-followups-5

Date: 2026-11-22
Author: partner
Tool and model: claude-code (Claude Sonnet 5.5)
Plan IDs: SEC-022,BPL-032

## Summary
Fixes the Low from Eldon's review of merged #262: the adapter now refuses at plan time any step whose pointer is empty, has an empty segment, or whose first segment is not a known section or setting root, so the internal `_typeChangedPointers` record can no longer be a step target (Tier 3).

## Files touched
- apps/engine/change_engine/change_engine/adapter/engine.py: `ALLOWED_POINTER_ROOTS` (components, locations, entities, roles, workflows, approvals, reports, company, compliance, i18n) and the plan-time check in `_judge` (`unsupported_value_type`).
- apps/engine/change_engine/change_engine/tests/test_sec_022_review_followups_5.py: new tests on both adapters, including a site with a recorded `/type` change.
- .github/workflows/tests.yml: the new module is listed in the SEC-022 step.
- docs/decisions/ADR-0051-adapter-role-and-state-namespacing.md: item 7 records the rule (still Proposed).

## Evidence
- New module: 7 tests, 98 subtests pass. With the check disabled: 62 failed, 7 passed. Mutations of the check (drop the whole check, the allowlist clause, the empty-segments clause, the empty-segment clause, add `_typeChangedPointers` or `settings` as a root, drop a valid root) each fail the tests.
- SEC-022 modules 116 passed; BPL-027 offline 9 passed (11 skipped, no bench); BPL-008, BPL-012, ERP-012, ERP-020, ERP-021, ERP-023, ERP-027 276 passed; property setter and phase3 24 passed; phase4 10 passed, 1 failed (`test_9_cross_doc_policy_passes_submitted_linked_doc`, pre-existing); CE-SEC mocks 40 passed (separate run); both conformance harnesses 208 passed, no vector changed; bpdiff 146 passed.
- Not run: a live bench. Real-engine behaviour is UNVERIFIED; the refusal runs before any engine call.

## Decisions
- ADR-0051 item 7 (Proposed).

## Tokens or cost
Unknown.

## Next step
Eldon's cross-model security review of this PR. Eldon's Low items 2 and 3 on #262 (dead reorder branch, `order` permutation check at plan) remain open follow-ups, not part of this change.

## Review fix round
Cross-model review (Gemini 4 Neon) of 6e4e53a: APPROVE, 0 High, 0 Medium, 2 Low. All fixed here (Tier 3). origin/main merged first (`git merge --no-ff`, no rebase).
- Low, missing `locations` case: the "valid kinds still plan" test now covers `location.upsert /locations/hq` (seq 3).
- Low, bare roots on element-level steps: `_judge` refuses with `unsupported_value_type` any step whose pointer has fewer segments than `min_pointer_segments(kind)`: `settings.set` 1, `field.reorder` 3, `option.reorder` 5, `option.add`/`option.quarantine` 6, `field.*`/`relation.*` 4, every other kind 2 (`field.*`/`relation.*` keep their existing exact-length check and its `definition_conflict` code). Tested on both adapters (plan refused, nothing written, no `recovery_required`), with and without a recorded `/type` change; a valid shape of every kind still plans.
- Low, leading slash: `_judge` refuses any pointer not starting with `/`, independent of schema validation; tested with `_validator_for` patched out.
- ADR-0051 item 7 states the exact rule (still Proposed).
- Evidence: new module before the fix 4 of 12 tests failing (71 failing subtests), after 12 passed, 230 subtests. 8 mutations (drop the slash check, drop the length check, `settings.set` 2, `option.reorder` 6, `option.add` 5, `field.reorder` 4, default 1, default 3) all killed. Option step pointers are not produced by the compiler or any fixture; their counts follow the Blueprint (`options` lives under a field) and are UNVERIFIED against a live engine.
- Not covered: a kind/root mismatch such as `location.upsert /company/x` still passes the shape check and fails later on existence; not part of this round.
