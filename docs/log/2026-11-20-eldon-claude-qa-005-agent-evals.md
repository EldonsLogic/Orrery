# Session log: qa-005-agent-evals

Date: 2026-11-20
Author: eldon
Tool and model: claude
Plan IDs: QA-005

## Summary
QA-005 done: 144 deterministic agent-behaviour eval cases (English and Arabic) over four categories, an offline runner and scorers with a per-category pass rate and a regression gate, run against the real runtime, chat and change-by-chat code with fake ports only. All cases pass; the silent arm fails every run case; mutation tests turn the matching cases red.

## Files touched
- evals/harness/agent_behaviour.py: loader, validator, runner, scorers, gate, CLI
- evals/harness/agent_world.py: fake ports (scripted model, Tool API port, Blueprint store, drafter) and the chat world
- evals/sets/agent_behaviour/: tools.json, run_cases.json, chat_cases.json, thresholds.json
- evals/tests/test_agent_behaviour.py: tests for scorers, gate, validator, suite, mutations, CLI
- evals/README.md, docs/PLAN.md (QA-005 done), docs/open-questions.md (Q-350 to Q-354)

## Decisions
- None. Cases follow [ADR-0048](../decisions/ADR-0048-agent-authority-propose-not-act.md) (Proposed). Thresholds are 100 percent per category because the suite is deterministic (Q-351).

## Tokens or cost
Unknown.

## Next step
QA-010 wires `python3 -m evals.harness.agent_behaviour run --baseline` into CI as a release gate (Q-351). Real-model arm waits for PLT-009 (Q-350). Add cases when OPR-004 enforces ADR-0048 item 9 (Q-354).
