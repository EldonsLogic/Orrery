# Session log: qa-016-review-fail-closed

Date: 2026-11-19
Author: partner
Tool and model: codex / gpt-6.1-sol
Plan IDs: QA-016

## Summary
Hardened the remaining fail-open cases from the QA-016 review after checking the existing fixes at 7f661e2. QA-016 stays doing until a real staging crawl.

## Files touched
- `infra/invisibility/crawler.py`: fail on missing discovered assets, rejected authenticated requests, exhausted page/queue coverage and empty CLI API paths.
- `infra/invisibility/tests/test_fail_closed.py`: four regression tests, all observed failing before the fix (including both auth credential forms).
- `infra/invisibility/README.md`: document incomplete-coverage failure behavior.

## Verification
- `python3 -m unittest discover -s infra/invisibility/tests -v`: 14 tests passed.
- Required docs, hygiene, lane and secret checks passed; finish-session verification recorded after push.
- Existing tests verify connection/bad target errors, regex validation, malformed cookies and redaction, redirect restriction, JS chunks, source maps and authenticated marker inspection. CI test step and Q-261 numbering already present at the old head.
- Live staging crawl remains unverified; no infrastructure provisioned.

## Decisions
- None; existing ADR-0016 behavior.

## Tokens or cost
Unknown.

## Next step
Cross-model re-review of QA-016; staging evidence is still needed before the plan row closes.
