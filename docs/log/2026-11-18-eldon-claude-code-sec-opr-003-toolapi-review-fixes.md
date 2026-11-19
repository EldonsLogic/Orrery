# Session log: sec-opr-003-toolapi-review-fixes

Date: 2026-11-18
Author: eldon
Tool and model: claude-code / opus-5.5
Plan IDs: OPR-003

## Summary
Fixed the ten findings (two critical, two high) from the partner's independent security review of the Tool API risk mapping. Opus-class subagent: each finding was reproduced as a failing test first (97 of 100 new tests failed before the fix), then fixed; operate tests 119 pass. Unlisted entities are now refused (never default to low risk), the registry can only raise risk, transitions are classified structurally, sensitive-field writes become R4 tools, and the checker recomputes risk.

## Files touched
- services/operate/toolapi/ (new classify.py; generate, policy, check, result, __main__) and tests (119 pass); contracts/tool-api.md section 11
- docs/open-questions.md: Q-138 to Q-140

## Decisions
- Interim classification rules, easy to swap for the manifest-declared class once the contract change and ADR exist (founder decision: manifests declare entity risk class). Fixture now yields 88 tools. Differences from the review recorded in the PR.

## Tokens or cost
Unknown or approximate, if known.

## Next step
Contract change and ADR for manifest-declared entity class and explicit transition kind; partner re-review.
