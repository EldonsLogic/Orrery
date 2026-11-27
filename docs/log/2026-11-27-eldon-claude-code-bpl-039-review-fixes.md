# Session log: bpl-039-review-fixes

Date: 2026-11-27
Author: eldon
Tool and model: claude-code / opus-5.5
Plan IDs: BPL-039

## Summary
Fixed the partner's seven review findings on PR #346 (Studio incremental apply and rollback) after merging main.

## Files touched
- services/studio/session.py: each applied revision keeps its engine-form Blueprint and dropped field types; the next incremental compile uses that as its base and drops at least those types (High 1). Compile returns one artifact-level `reversible` answer and `unchanged`; `canRollback` also needs no irreversible step (Medium 2); compile reads state under the lock (Low 6); apply with no edit since the last apply is refused with STUDIO-NO-CHANGES (Low 4).
- services/studio/static/app.js, i18n.js: reversible answer shown before apply, per-step column label, neutral `code.rollback_not_possible` hint with Arabic, recompile after apply or rollback, "no changes since the last apply", approvals row on rollback results, no stray "null" text in the result (all strings in English and Arabic).
- services/studio/tests/test_studio_plugged_engine.py: two applies and two rollbacks on a plugged engine, run with the fake loaded as plugged and with the real BPL-012 adapter when importable (skipped otherwise). Failed before the fix.
- services/studio/tests/test_studio_incremental.py: reversible answer, unchanged and STUDIO-NO-CHANGES, new i18n keys.
- services/studio/__init__.py, README.md: rollback docs updated (Low 7).
- docs/PLAN.md: merge only (kept main's GOV-060 done and SEC-023 doing, this PR's BPL-039 row).

## Decisions
- None. Rollback does not revert the working Blueprint, so after a rollback the edit shows again as an incremental compile (existing behaviour, kept).

## Tokens or cost
Unknown.

## Next step
Partner re-review of PR #346. Separate row worth adding: about 133 Studio English keys have no Arabic entry (pre-existing, from the review).
