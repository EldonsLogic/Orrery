# Session log: opr-019-manifest-risk-class

Date: 2026-11-18
Author: eldon
Tool and model: claude-code
Plan IDs: OPR-019

## Summary
ADR-0037 (Proposed): component manifests declare an entity risk class, Blueprint gains transitions[].kind, Tool API 0.3.0 documents the emitted fields; generator reads manifests (raise only) with 26 new tests. Closes Q-138; adds Q-141.

## Files touched
- contracts/ (blueprint, component manifest schemas, tool-api.md, README), docs/decisions/ADR-0037 and INDEX
- services/operate/toolapi/*, tests/toolapi/test_manifest_classes.py
- docs/open-questions.md, docs/PLAN.md

## Decisions
- ADR-0037 (Proposed; both founders must accept, it changes contracts).

## Tokens or cost
Unknown or approximate, if known.

## Next step
Partner security review (Tier 3); Blueprint meta.schemaVersion migration (Q-141); split generate.py (Q-140).
