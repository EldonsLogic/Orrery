# Session log: erp-020-review-fixes-2

Date: 2026-11-19
Author: partner
Tool and model: claude-code / sonnet-5.5
Plan IDs: ERP-020

## Summary
Re-checked every finding of the independent review of PR #148 against the code at `4bf1ce8`. The MED items were already fixed there; the one remaining gap (LOW 8, engine import failures) is closed and the ping response now has a test for engine markers.

## Files touched
- `apps/engine/change_engine/change_engine/wsgi.py`: any import-time failure of the engine application answers with the plain 404, not only `ImportError`.
- `apps/engine/change_engine/change_engine/tests/test_erp_020_wsgi_guard.py`: a non-`ImportError` import failure test, and a check that the anonymous ping response carries no `frappe` or `erpnext` text in headers or body even when the engine response does.

## Decisions
- MED 1 (writes and arbitrary DocTypes on `/api/resource/*`): already fixed at `4bf1ce8` by a GET-only allowlist of four DocTypes with a drift test; no change.
- MED 2 (invisibility claim): the PLAN row stays `doing` and `HEADLESS.md` states the limit (engine-side ingress only, PLT-024 and QA-016 for allowed responses); the new ping marker test is the requested assertion.
- MED 3 (CI): the guard unit tests and `infra/dev/docker` discovery (which includes the compose contract test) already run in `tests.yml`; no change.
- LOW 4 (token entropy): left as documented in `HEADLESS.md` (32 to 256 URL-safe characters from secure random bytes); no entropy estimator added.
- LOW 5 to 7: already handled or documented at `4bf1ce8`.
- Differential check outside the repo: 1064 content-type, body and query combinations were compared against the request parsing of Werkzeug 3.1.3 and the `make_form_dict` of Frappe `version-15` (read from source, not the pinned image). No input exposed `cmd` or `run_method` to the engine without the screen rejecting it. Not committed; the pinned image's exact Frappe build was not inspected.

## Verification
- Before the fix the import failure test errored. After: `python3 -m unittest change_engine.tests.test_erp_020_route_guard change_engine.tests.test_erp_020_wsgi_guard` (in `apps/engine/change_engine`): 64 passed.
- `python3 -m unittest discover -s tests` in `infra/dev/docker`: 26 passed, 3 skipped (live bench).
- The live smoke test (`smoke_headless_engine.py`) was not re-run.

## Tokens or cost
Unknown.

## Next step
Founder review and merge decision for ERP-020 (Tier 2). Open follow-ups stay with PLT-024, QA-016 and SEC-002.
