# Session log: bpl-017-review-round-2

Date: 2026-11-23
Author: eldon
Tool and model: claude-code (Opus 5.5, subagent)
Plan IDs: BPL-017

## Summary
Fixed the Fable re-review of PR #287 at a6db4ee (N1 to N3 and the follow-ups), after merging main (#248). Every probe from the review now has a test that was written first. BPL-017 stays `doing`.

## Files touched
- services/blueprint/factory/drafting.py:
  - N1: only `.py` and `.json` files, with the extension casefolded. Any JSON object with a `type`, `fieldtype` or `kind` key is a field and goes through `field_verdict`. More script keys are refused, and so are `eval:`, `{{` and `{%`.
  - N2: `policy.financial_hit` runs on the request and the draft. Arabic money and auth lists are added, matched per word and per adjacent word pair after prefix removal. English money and auth words are added.
  - N3: the reserved namespaces are now built from existing ids and capabilities, plus `engine`, `registry`, `factory` and `components`. A component id equal to an existing capability is refused.
  - Follow-ups: the target is reserved with an exclusive mkdir before the move. The audit gets `drafted` only after the move, and the sink always receives a copy. Stale `.tmp-*` folders are cleaned. `rtlVerified` is forced to false.
- services/blueprint/component_request/text.py: folds ڞ to ض, adds the زكو stem, and joins adjacent token pairs for the Arabic scope check.
- services/blueprint/tests/factory/test_drafting.py: now 141 tests (57 new).
- .github/workflows/tests.yml: the blueprint path filter adds `services/operate/(toolapi|agui)`.
- docs/decisions/ADR-0065: items 3, 5, 6 and 7 updated. They now cover the reviewer's role for Python arithmetic, the known over-refusals and the fail-closed audit sink.

## Decisions
- No new ADR. ADR-0065 is still Proposed, so it was edited in place.

## Checks
- `test_drafting.py`: 141 passed.
- `tests/component_request` (BPL-016, run on its own): 438 passed.
- The whole `services/blueprint/tests` suite passes.
- check_docs, hygiene and plan independence pass.

## Tokens or cost
Unknown.

## Next step
A cross-model re-review of #287. After that, the next BPL-017 slices are a promotion step with a reviewer-is-not-requester check, input from approved BPL-016 records, and the human queue for refusals. Q-600 (the requester role) is still open.

## Q-600 applied
- Eldon decided Q-600 for both founders on 2026-11-23: only platform staff may request drafts for now; tenant admins later.
- `Drafter` now refuses, before any model call and with an audit record (`FDR-015`), any principal that is not a human platform-staff one: `realm` must be the identity staff realm (`Realm.STAFF` in services/control-plane/identity/models.py, the marker the PLT-005 identity claims and the build_state Principal already use) and `actor_kind` must be `user`.
- Tests: a staff principal drafts; a tenant admin, a principal with no realm, a near-miss realm and a staff-realm agent are refused (146 passed).
- Q-600 is marked resolved; ADR-0065 item 7 and the README are updated.
