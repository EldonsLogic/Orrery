# Session log: cmp-022-hijri-umm-al-qura

Date: 2026-11-18
Author: eldon
Tool and model: claude-code
Plan IDs: CMP-022

## Summary
Replaced the approximate civil Hijri conversion in the document intake with the pinned MIT library hijridate (Umm al-Qura, 1343 to 1500 AH), recorded its licence, and closed Q-115.

Cross-lane: approved by eldon (walkthrough answer 7, 2026-11-18: "I do CMP-022"); partner lane paths docs/legal/licence-register.md and the CMP-022 plan row.

## Files touched
- services/discovery/connectors/intake/{parse,fields}.py, tests, requirements.txt: library conversion, no approximate flag
- .github/workflows/{tests,audit}.yml: install and audit the new requirements file
- docs/legal/licence-register.md, docs/architecture/calendars-and-locale.md, docs/PLAN.md, docs/open-questions.md

## Decisions
- None, or link to ADR / strategy decision.

## Tokens or cost
Unknown or approximate, if known.

## Next step
Saudi accountant spot-check of Hijri month starts (UNVERIFIED); CMP-022 consumers in the Blueprint locale rules.
