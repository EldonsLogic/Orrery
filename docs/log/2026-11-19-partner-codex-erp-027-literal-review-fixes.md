# Session log: erp-027-literal-review-fixes

Date: 2026-11-19
Author: partner
Tool and model: codex / gpt-6.1-sol
Plan IDs: ERP-027

## Summary
Fixed the new Medium and Low findings from the independent ERP-027 re-review: custom identifiers stay case-sensitive, and equivalent apostrophe escaping matches database read-back.

## Files touched
- `guarded_apply/ddl_plan_gate.py`: scope SQL keyword/type case folding without folding identifiers; restore the existing rejection-message contract; normalize only the two valid apostrophe-escaping forms for default read-back while preserving other escapes, case and whitespace.
- `test_erp_027_decimal_drift.py`: reject uppercase/non-ASCII custom names and uppercase table prefixes, accept case-insensitive SQL keywords, and test equivalent/distinct default literals including backslash pairs.
- `.github/workflows/tests.yml`: include `test_ai_control_plane.py` in the DDL gate step so the pre-existing naming regression test runs in CI. Shared workflow edit requires Eldon's review.
- This new log; prior logs left unchanged.

## Decisions
- No contract or architecture change. ERP-027 remains doing until re-review and founder acceptance.
- Matching defaults normalizes apostrophe spelling only; other escape bytes and customer data are not folded or decoded twice.

## Tokens or cost
Unknown.

## Next step
Gemini re-check of the small fix diff, then founder review including the shared workflow change. No merge or phase exit claimed.

## Verification

- Reproduced both reported failures and the existing test_ai_control_plane naming/message regression before fixing them. Added an additional failing table-prefix case test before scoping the regex flags.
- The previously failing control-plane and ERP-027 suites pass after the fix; broader engine regression results are recorded in the PR response.
- A fresh private MariaDB 11.4 container created a column with a backslash-escaped apostrophe default, read back the server's doubled-apostrophe form, and matched it to the approved SQL using production code. Container removed in finally. No host port, secrets or database artifacts were committed.
