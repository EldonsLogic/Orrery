# Session log: gov-020-plan-review

Date: 2026-11-18
Author: eldon
Tool and model: claude-code
Plan IDs: GOV-020

## Summary
Added scripts/plan_review.py (stale doing rows, ready rows by owner, gate inversions, open rows in the gate) with tests, and a runbook. First run found five stale doing rows (LEG-002, BRD-006, BRD-007, BRD-011, BPL-028) and one gate inversion (CMP-025 in G2 depends on CMP-013 in G3); not acted on here.

## Files touched
- scripts/plan_review.py, scripts/tests/test_plan_review.py
- docs/runbooks/plan-review.md, README, docs/PLAN.md

## Decisions
- None, or link to ADR / strategy decision.

## Tokens or cost
Unknown or approximate, if known.

## Next step
Resolve the CMP-025 / CMP-013 gate inversion and the stale doing rows (owners decide).
