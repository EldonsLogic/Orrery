# Session log: opr-009-review-fixes

Date: 2026-11-20
Author: eldon
Tool and model: claude (Opus-class)
Plan IDs: OPR-009

## Summary
Fixed the HIGH and MEDIUM findings of the PR #199 review: the chat change decision now runs on the resulting diff with a default-deny allow-list, consume is compare-and-delete, apply outcomes are honest, the port gets the caller identity, bad clocks are coded and confirm refusals are audited. Tests first; the probes and the listed uncaught mutations now fail when applied.

## Files touched
- services/operate/change/policy.py: new diff-level check (owning entity, tax and money fields, removals, allow-list, forbidden keys, locked fields).
- services/operate/change/service.py, edits.py, store.py, models.py, errors.py, preview.py: wiring, compare-and-delete consume, `ApplyRefused` and `change_status`, `actor` and `risk` to the port, clock and TTL checks, refusal audit, JSON preview values.
- services/operate/tests/change/test_change_policy.py, helpers.py, test_change_flow.py: probes A2 to A20, race, outcome, actor, clock, audit and mutation tests.
- docs/architecture/change-by-chat.md (new design doc), services/operate/README.md, docs/open-questions.md (Q-280, Q-281 edits; Q-290 new).

## Decisions
- Default deny on the diff with an explicit allow-list (Q-280, Q-290). Only a typed `ApplyRefused` may say "nothing was changed".

## Tokens or cost
Unknown.

## Next step
Founder answers on Q-290 scope; real port binding with actor and `change_status` (Q-281). LOW findings L3 to L6 remain (L4 partly: JSON values, no risk code in text).
