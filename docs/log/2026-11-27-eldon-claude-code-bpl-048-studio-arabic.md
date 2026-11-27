# Session log: bpl-048-studio-arabic

Date: 2026-11-27
Author: eldon
Tool and model: claude-code / sonnet-5.5
Plan IDs: BPL-047

## Summary
Added Arabic for the 132 Studio keys that fell back to English (BPL-047) and made the dictionary test require identical English and Arabic key sets, matching placeholders and no engine name. The Arabic is a draft needing native review (ADR-0033, Q-689). The brief said BPL-048, but that id was already taken on main, so this row is BPL-047.

## Files touched
- services/studio/static/i18n.js: 132 Arabic entries; header comment updated
- services/studio/tests/test_studio_static.py: key parity test and placeholder/engine-name test
- docs/PLAN.md, docs/open-questions.md: BPL-047 row, Q-689 native review

## Decisions
- None new. Follows ADR-0033 (Arabic review).

## Tokens or cost
Unknown.

## Next step
Native Arabic review of the Studio copy (Q-689); BPL-047 to done once the PR merges.
