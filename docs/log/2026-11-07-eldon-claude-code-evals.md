# Session log: evals

Date: 2026-11-07
Author: eldon
Tool and model: claude-code (cloud session); harness by a Sonnet-tier sub-agent, Arabic set by an Opus-tier sub-agent, both verified by the orchestrator (Opus)
Plan IDs: QA-001,QA-002

## Summary
Built the offline eval framework (record schema, loader, deterministic scorers with Arabic digit and letter normalisation, echo and null adapters, per-set thresholds, CLI, 38 tests) with a CI job, and the first Arabic eval set: 100 fictional prompts covering accounting terms, Gulf, Egyptian and MSA intents, numbers, dates, code-switching and safety.

## Files touched
- evals/__init__.py, evals/harness/, evals/schema/eval-record.schema.json, evals/tests/, evals/requirements.txt, evals/README.md.
- evals/sets/arabic_core/ (cases.jsonl, README.md, thresholds.json).
- .github/workflows/ci.yml: new `evals` job (harness tests and set validation).
- docs/PLAN.md: QA-001 done; QA-002 doing until a native speaker and an accountant review the set.

## Decisions
- No model is called yet: real adapters go through the model gateway (PLT-009) and read keys from the environment, never the repo. Threshold stays 0 until the QA-003 bake-off.
- 13 records are marked UNSURE in their notes (placeholder report ids, year assumptions, carton vs piece quantities); listed in the set README.

## Tokens or cost
Unknown.

## Next step
Native-speaker and accountant review of evals/sets/arabic_core (then QA-002 done); QA-003 bake-off needs a gateway or provider keys, which the founders must provide outside the repo.
