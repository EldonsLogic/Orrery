# Session log: agent-redteam

Date: 2026-11-18
Author: eldon
Tool and model: claude-code / sonnet-5.5
Plan IDs: SEC-014

## Summary
Red-team suite for injection via uploads and connectors: 76 cases, 0 breaches, 22 known gaps as strict xfail.

## Files touched
- evals/sets/redteam_uploads/cases.ndjson, evals/harness/redteam.py, evals/tests/test_redteam.py
- docs/security/redteam-uploads-report.md

## Decisions
- None. Corpus uses .ndjson so the arabic_core schema check skips it.

## Tokens or cost
Subagent run, about 150k tokens.

## Next step
Close gaps in Q-159 to Q-161 (egress filter, taint downgrade, detection flags).
