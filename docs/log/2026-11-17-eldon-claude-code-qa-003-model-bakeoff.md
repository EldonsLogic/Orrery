# Session log: qa-003-model-bakeoff

Date: 2026-11-17
Author: eldon
Tool and model: claude-code / sonnet-5.5
Plan IDs: QA-003

## Summary
Ran the Arabic eval set blind through three Claude tiers (no API key: subagent runs scored by the offline harness through a new replay adapter): Opus 91%, Sonnet 89%, Haiku 83% in round 2, after a disclosed round 1 that left out the reference date and tool argument names; set the gate threshold to 0.85.

## Files touched
- evals/harness/adapters.py, evals/tests/test_harness.py: replay adapter and test
- evals/results/qa-003/: instructions and the three response files; evals/sets/arabic_core/thresholds.json: 0.85
- docs/research/qa-003-arabic-bakeoff.md: method, results, limits
- docs/PLAN.md, docs/open-questions.md: QA-003 done; Q-122, Q-123

## Decisions
- Gate threshold 0.85 follows the strategy/08 target. No model-routing ADR proposed; evidence is one run per model.

## Tokens or cost
Unknown or approximate, if known.

## Next step
Fix the five arabic_core set issues with a native reviewer and rerun through the gateway when it exists (Q-122, Q-123).
