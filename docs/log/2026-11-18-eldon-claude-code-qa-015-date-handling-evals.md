# Session log: qa-015-date-handling-evals

Date: 2026-11-18
Author: eldon
Tool and model: claude-code
Plan IDs: QA-015

## Summary
Added deterministic date property tests (Hijri round trips 1343 to 1500 AH, month and leap rules, digit normalisation, weekends, fiscal tiling, four time zones). Finding: hijridate has 28 or 31 day months before 1365 AH, so 29/30 holds only from 1365. Sonnet subagent built it; I reran 388 passed, 5 xfailed.

## Files touched
- services/discovery/tests/dates/test_date_properties.py, services/discovery/README.md
- docs/open-questions.md (Q-144, Q-145), docs/PLAN.md

## Decisions
- None, or link to ADR / strategy decision.

## Tokens or cost
Unknown or approximate, if known.

## Next step
Answer Q-144 and Q-145; a Saudi accountant should check the pre-1365 table before historic dates matter (CMP-022 follow-up).
