# Session log: bpl-019-sim-report

Date: 2026-11-19
Author: eldon
Tool and model: claude
Plan IDs: BPL-019

## Summary
Added the simulation review layer (derived anomaly rules SIM-132 to SIM-136, bilingual owner sign-off view model) and append-only human sign-off records bound to the report digest, feeding BPL-020 as evidence only.

## Files touched
- services/blueprint/simulator/review.py, signoff.py, labels.json, codes.py, __init__.py: review and sign-off
- services/blueprint/tests/simulator/test_sim_signoff.py: tests
- docs/architecture/simulator.md, docs/PLAN.md, docs/open-questions.md (Q-271 to Q-273)

## Review fixes (PR #197)
- Sign-off records validated on read; duplicates per role or person, cross-tenant records and malformed records fail closed; any rejection wins.
- Verdict recomputed from status, summary, in-doubt list and findings; stored verdict can only tighten it.
- Signer is a typed verified principal with tenant; cross-tenant signers refused (SO-E11); humans only.
- Iterators materialised once; unknown finding codes (SIM-138) and unknown currencies (SIM-137) block; time bounds with caller's `now`; floats, huge integers and deep nesting refused; trivial `0 = 0` rows no longer defeat SIM-135; gate evidence names tenant and required roles; acknowledgements exact and unique.
- 14 targeted mutations (the review's 10 plus 4) each fail the tests. Q-274 added.

## Decisions
- None, or link to ADR / strategy decision.

## Tokens or cost
Unknown or approximate, if known.

## Next step
BPL-020 consumes `gate_evidence`; a web row for the sign-off screen (Q-272); QA-011.
