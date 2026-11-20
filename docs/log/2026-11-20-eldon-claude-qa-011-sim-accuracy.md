# Session log: qa-011-sim-accuracy

Date: 2026-11-20
Author: eldon
Tool and model: claude
Plan IDs: QA-011

## Summary
QA-011 done: four hand-computed fictional months (SAR, KWD 3 decimals, mixed, source warning) and 14 seeded engine faults run through the simulator with the fake adapter; scorer gives 1000 permille detection and 0 false positives. Findings Q-360 to Q-363 (fake port stock-issue currency, omitted metric only a warning, fake-engine caveat, tolerance).

## Files touched
- evals/harness/sim_accuracy.py: fixtures, tampering adapter, scorer, CLI
- evals/tests/test_sim_accuracy.py: 38 tests (written first)
- evals/README.md, docs/architecture/simulator.md: how to run
- docs/PLAN.md: QA-011 done; docs/open-questions.md: Q-360 to Q-363

## Decisions
- None, or link to ADR / strategy decision.

## Tokens or cost
Unknown.

## Next step
Rerun the scorer through the gateway-backed port when it exists (Q-362); resolve Q-360 and Q-361 in the simulator (BPL-018, BPL-019).
