# Session log: qa-006-injection-eval-suite

Date: 2026-11-17
Author: eldon
Tool and model: claude-code / sonnet-5.5
Plan IDs: QA-006

## Summary
Built the prompt-injection eval suite: 34 cases from the SEC-003 attack list scored on platform behaviour (blocking, detection and task-success metrics, per case and language), with oracle, permissive and null adapters. Subagent (sonnet) built it; checked by rerunning the tests.

## Files touched
- evals/sets/injection/cases.jsonl, evals/schema/injection-case.schema.json: the 34 cases and their schema
- evals/harness/injection.py, evals/harness/__main__.py: scorer, adapters, `injection` subcommand, `check` support
- evals/tests/test_injection.py, evals/README.md: tests and docs
- docs/PLAN.md, docs/open-questions.md: QA-006 done; Q-83 to Q-85

## Decisions
- None. Gate threshold left open until a real adapter exists (Q-85).

## Tokens or cost
Unknown or approximate, if known.

## Next step
BPL-021, DSC-010, BRD-005. SEC-014 (agent red-team) can now use this suite.
