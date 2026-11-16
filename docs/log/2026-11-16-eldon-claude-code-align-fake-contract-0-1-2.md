# Session log: align-fake-contract-0-1-2

Date: 2026-11-16
Author: eldon
Tool and model: claude-code (Opus-class)
Plan IDs: BPL-025

## Summary
Merged engine adapter contract 0.1.2 (bpl-025-026-adapter-contracts, which resolves Q-36 to Q-40) into the fake-adapter branch and aligned the fake and the conformance suite with it; 625 tests pass in services/blueprint/tests, none skipped.

## Files touched
- services/blueprint/tests/adapter/conftest.py: `assert_no_effect` now takes the exact events 8.2 lists for the case (`expect`) instead of "at most one allowed".
- services/blueprint/tests/adapter/test_adp_apply.py: ADP-C-034 to 037 require outcome `rejected` and exactly one `blueprint.apply_failed`; 040 and 042 require the `ok: false` envelope and no event; new ADP-C-071 (initial-build compensation is journaled removal).
- services/blueprint/tests/adapter/test_adp_rollback_export.py: ADP-C-051 checks `site.applied` is the artifact rolled back to; 052 and 053 require outcome `rejected` and one `blueprint.apply_failed`.
- services/blueprint/tests/adapter/test_adp_envelope.py: ADP-C-008 events depend on outcome or envelope; ADP-C-010 uses the exact-event check.
- services/blueprint/tests/adapter/test_adp_site_artifact.py: ADP-C-013 checks the `exportedProperties` key names of 5.1.
- services/blueprint/adapter/fake.py, testkit.py, harness.py, README.md: contract version 0.1.2, comments point at 5.1, 5.6.2 and 15.1; `testkit.rejected_error`; duplicate stub methods removed from `FakeHarness`.
- docs/open-questions.md, docs/STATUS.md: merge (both sides kept; status regenerated).

## Decisions
- None new; the fake already behaved as 0.1.2 says. Contract decisions are in the BPL-026 log of the same day and open-questions Q-45 to Q-49.

## Tokens or cost
Unknown.

## Next step
Partner re-reviews PR 40 and PR 56 against 0.1.2 (BPL-025, BPL-026).
