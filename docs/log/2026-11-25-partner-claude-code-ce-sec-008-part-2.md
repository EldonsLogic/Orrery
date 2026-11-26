# Session log: ce-sec-008-part-2

Date: 2026-11-25
Author: partner
Tool and model: claude-code / claude-opus-5-5 (coordinator); implementation by a Claude Sonnet 5.5 child, test-first
Plan IDs: CE-SEC-008

## Summary
CE-SEC-008 part 2 (PR #331) carries the follow-ups from Eldon's line-by-line review of #322, which merged at the content he approved (750dc543). The detail of each round is appended to 2026-11-25-partner-claude-code-ce-sec-008-deploy-path-durability.md.

## Files touched
All paths are under `apps/engine/change_engine/change_engine/`:
- `adapter/frappe_backend.py`:
  - uuid4 deployment ids;
  - the decimal path runs through `execute_single_field_deployment(approved_plan=...)`.
- `api/endpoints.py`:
  - an evidence digest in the plan column, with journal rows chained to it and verified on load;
  - legacy plain-list evidence loads unverified and holds;
  - evidence must match the request's doctype, field and site;
  - `_commit_durable` raises when there is no `commit`;
  - a 60 s timeout ceiling, with the previous value restored on every exit.
- `guarded_apply/schema_reconciler.py`:
  - `approved_plan` is validated before the intent;
  - the reason codes `evidence_unavailable` and `snapshot_unavailable`;
  - the timeout restore.
- Tests: `tests/test_ce_sec_008_review_fixes.py`, `tests/test_ce_sec_008_deploy_path_durability.py` and `tests/test_api_deployment.py`.
- `docs/PLAN.md`: CE-SEC-011 is trimmed to what remains, and now also lists the raw exception text in the three non-DDL engines.

## Decisions
- Merge of main after #322: main held a revert of 049c349c (made to keep Eldon's approved content on #322). This branch keeps its own versions of the files that revert touched, so the merge does not undo part 2. Before resolving, it was checked that main changed those files only through the revert.

## Evidence
- Full change-engine suite: 1775 passed, 86 skipped, 0 failed.
- Reviews:
  - GPT-6.2 Sol at 049c349c: no High findings, two Medium, both fixed.
  - Gemini 4 Argon at 7260840f: approve with nits; both Lows fixed.

## Tokens or cost
Unknown.

## Next step
Eldon's line-by-line read of #331, then the partner's Tier 3 say-so. After that: CE-SEC-009, CE-SEC-010 and CE-SEC-011.
