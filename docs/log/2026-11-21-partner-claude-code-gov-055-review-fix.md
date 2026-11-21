# Session log: gov-055-review-fix

Date: 2026-11-21
Author: partner
Tool and model: claude-code (Claude Opus 5.5, coordinator)
Plan IDs: GOV-055

## Summary
Fixes two findings from the Gemini 4 Hydrogen review of PR #254 (head e7995c6) in `scripts/check_component_reviewers.py`.
- **High, fixed:** a reviewer login with a zero-width character (`sayegh9` + U+200B) or a lookalike letter (Cyrillic `ѕayegh9`) slipped past the owner-is-not-reviewer gate.
  - Owner and reviewer logins must now match the GitHub login charset `[A-Za-z0-9-]{1,39}` after the `@` and whitespace are removed. Any other login is reported as invalid, which fails closed.
- **Low, fixed:** a non-string `certification.level` (a list or a dict) crashed the check with `TypeError`. It is now reported as a problem.

## Files touched
- `scripts/check_component_reviewers.py`: adds `LOGIN_RE` and `valid_login`, checks the level type first, and reports invalid logins.
- `scripts/tests/test_check_component_reviewers.py`: two new tests, written first.
  - **Before the fix:** 2 failed, 9 passed.
  - **After the fix:** `scripts/tests` passes 33, plus 29 subtests.

## Decisions
- None.

## Tokens or cost
Unknown.

## Next step
Eldon's Tier 2 review of #254.
