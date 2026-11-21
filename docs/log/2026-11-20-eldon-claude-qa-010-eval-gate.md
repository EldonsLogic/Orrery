# Session log: qa-010-eval-gate

Date: 2026-11-20
Author: eldon
Tool and model: claude
Plan IDs: QA-010

## Summary
QA-010: `python3 -m evals.gate` runs all six deterministic eval suites offline and is a CI release gate (floors, case minimums, baseline regression, vanished cases, skip markers); tests include broken controls that must fail it.

## Files touched
- evals/gate/ (core, suites, thresholds.json, baseline.json, baseline-history.json): the gate; initial baseline recorded in baseline-history.json (reason: initial baseline)
- evals/tests/test_gate.py: 28 tests incl. silent agent, permissive injection defence, dropped and crashed suite controls
- .github/workflows/tests.yml: new step `python3 -m evals.gate` (shared path)
- evals/README.md, docs/open-questions.md (Q-460 to Q-463), docs/PLAN.md

## Decisions
- Confirms Q-351: agent_behaviour thresholds stay 100 percent per category with zero tolerance; any drop blocks.

## Tokens or cost
Unknown or approximate, if known.

## Next step
QA-012 release checklist builds on this gate. Real-model arm waits for PLT-009 (Q-460).
