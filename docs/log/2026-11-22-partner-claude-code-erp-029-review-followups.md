# Session log: erp-029-review-followups

Date: 2026-11-22
Author: partner
Tool and model: claude-code (Claude Sonnet 5.5, `claude-sonnet-5-5`)
Plan IDs: ERP-029

## Summary
Follow-up to merged #260 (ERP-029, Tier 3): the four non-blocking Lows in Eldon's security review (APPROVED 2026-11-22, review 6011236489) and the LOOK items in his line-by-line comment (7076555011). Tests were written first and run red before the one code change. Written with a different model from the security review (Fable 5.2) that raised the findings, so the cross-model rule holds. Q-558 stays open; it was not answered, only extended.

## Items
Done:
- Low 1 (subset run does not return a conflict outside `request_ids`): documented, not changed. The design note (section 4) now says the journal is the source of record and OPR-007 reads escalations from it. The existing subset test now asserts that the conflicted request is not returned.
- Low 2 (held-back `failed` journaled as `readback_pending`): a distinct reason, `conflict_hold`, added to the allowlist and used in `_commit`. Two existing tests updated to expect it; design note updated.
- Low 2, Q-558 (d): appended "how a conflict is closed" to the Q-558 row. Nothing decided.
- Low 3 (one `stuck = 1` row per reason change after the threshold): documented in section 4, OPR-007 escalates on the first `stuck = 1` row per request. No code change.
- Low 4 (design note line 77, section 7 item 2): reworded. `outcome_conflict` is a returned, journaled result, not a run failure that pages the operator. Only `journal_tampered` and `clock_unavailable` page.
- Low 4 / LOOK, untested `prev` link in the MAC: new test computes the chain MAC independently and refuses a row whose MAC skips the previous link.
- Low 4 / LOOK, untested reason allowlist: new test refuses a row with an unlisted reason and an otherwise valid MAC.
- LOOK, "no test for a subset run leaving the conflicted request out": already covered by `test_unrelated_stuck_request_still_journals_and_escalates_when_conflict_exists`; made the assertion explicit.
- Test list in the design note updated.

Skipped (not Lows, or not in the allowed paths):
- HUMAN-ONLY items (thresholds, the six gates, key custody, attestation, live-reader fencing): founder decisions, left open.
- Tail truncation needing an external head anchor, ERP-023 audit rows without a MAC, unverified engine facts: on the section 7 gate list, by design.
- LOOK on `_admissions` trusting unauthenticated audit rows, and on the shrink check being per instance: same gate items.
- Redundant-guard survivors (unique indexes, duplicate check): redundant by design, not changed.
- LOOK that the session log names the models for #260 and that the founder accepts three models on a Tier 3 change: a founder judgement, not a code change.

## Mutation checks
Each mutated and run, then restored: `prev` removed from the MAC body (new chain test fails); `reason not in _REASONS` removed (new allowlist test fails); `conflict_hold` reverted to `readback_pending` (conflict test fails).

## Files touched
- `apps/engine/change_engine/change_engine/guarded_apply/action_outcome_reconciler.py`: `conflict_hold` reason (2 lines).
- `apps/engine/change_engine/change_engine/tests/test_erp_029_action_outcome_reconciliation.py`: two new tests, three expectations updated, one assertion added.
- `docs/architecture/action-outcome-reconciliation.md`: rewording and additions above.
- `docs/open-questions.md`: Q-558 row, part (d) only.

## Decisions
- None. No ADR; the new reason is internal to the journal's allowlist.

## Tokens or cost
Unknown.

## Next step
Eldon's Tier 3 line-by-line read of this diff, then Q-558 for the founders (ERP-029, OPR-004, OPR-007).
