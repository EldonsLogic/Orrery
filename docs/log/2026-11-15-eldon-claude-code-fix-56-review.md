# Session log: fix-56-review

Date: 2026-11-15
Author: eldon
Tool and model: claude-code
Plan IDs: BPL-025

## Summary
Fixed the partner's blocking review findings on PR 56 (fake adapter): compensation now runs the stored inverse steps in reverse; a missing harness capability or any skip fails the conformance run; ADP-C-050 judges the adapter's plan evidence; ADP-C-047 uses an execution journal and checks how the apply ends; open questions Q-36 to Q-40 appended.

## Files touched
- services/blueprint/adapter/fake.py: compensation via inverse steps (derived undo for an initial build), execution journal, plan evidence statements
- services/blueprint/adapter/harness.py, README.md: required `plan_evidence` and `execution_journal`; extensions are required, not optional
- services/blueprint/adapter/testkit.py: sealed artifacts now carry a real inverse of their own steps
- services/blueprint/tests/adapter/: conftest (missing capability fails, skips fail the run), test_adp_apply (047, 050, inverse-driven compensation tests), selfcheck, two data-dependent skips turned into no-op returns
- docs/open-questions.md: Q-36 to Q-40 appended

## Decisions
- None. Q-36 to Q-40 in docs/open-questions.md clarify Q-32 to Q-35 and one new gap (compensation of an initial build).

## Tokens or cost
Unknown or approximate, if known.

## Next step
Partner re-review of PR 56; Eldon decides Q-36 to Q-40 in the contracts lane (BPL-025, BPL-012).
