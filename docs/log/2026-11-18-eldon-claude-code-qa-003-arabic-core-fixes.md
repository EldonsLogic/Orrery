# Session log: qa-003-arabic-core-fixes

Date: 2026-11-18
Author: eldon
Tool and model: claude-code
Plan IDs: QA-003

## Summary
Fixed the five arabic_core records all three models failed (set problems, not model errors); rescored stored responses: Opus 96, Sonnet 94, Haiku 85. Records stay unreviewed.

## Files touched
- evals/sets/arabic_core/cases.jsonl: records 002, 045, 078, 081, 097
- docs/research/qa-003-arabic-bakeoff.md: addendum

## Decisions
- None, or link to ADR / strategy decision.

## Tokens or cost
Unknown or approximate, if known.

## Next step
Native-speaker review of the five changes (QA-003 follow-up); rerun through the model gateway when it exists.
