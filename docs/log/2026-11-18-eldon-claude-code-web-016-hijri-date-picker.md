# Session log: web-016-hijri-date-picker

Date: 2026-11-18
Author: eldon
Tool and model: claude-code
Plan IDs: WEB-016

## Summary
Built a DatePicker (Gregorian and Hijri Umm al-Qura via Intl, value always Gregorian ISO, typed entry in Arabic-Indic or Latin digits, ambiguity reported not guessed, keyboard grid, RTL) with 18 tests and a preview entry. Sonnet subagent built it; I reran lint, 13 node and 83 vitest tests.

## Files touched
- web/app/src/ui/DatePicker.tsx, dateLogic.ts, css, test, index, Preview, messages, README
- docs/open-questions.md (Q-146), docs/PLAN.md

## Decisions
- None, or link to ADR / strategy decision.

## Tokens or cost
Unknown or approximate, if known.

## Next step
Decide Q-146 (year range, jsdom); native review of Arabic labels.
