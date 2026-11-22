# Session log: sec-022-review-followups-2

Date: 2026-11-21
Author: partner
Tool and model: claude-code (Claude Sonnet 5.5)
Plan IDs: SEC-022,BPL-032

## Summary
Fixed the non-blocking Lows from the Opus review comment and Eldon's review of merged PR #252: trailing newlines accepted by identifier checks, the in-memory adapter refusing own-entity role grants that the offline engine path allows, and two wording items (route guard comment, ADR-0051).

## Findings and fixes
- Trailing newline, envelope context: the pure-Python fallback used `.match` with `$`. The schema validator path (the one that runs in CI and production) also accepted `"t_abcd\n"`, because JSON Schema `pattern` is a search and `$` matches before a final newline. `validate_context` now re-checks `contractVersion`, `requestId`, `correlationId`, `tenantId` and `supportGrantId` with `fullmatch` on both paths. The contract schemas were not touched.
- Trailing newline, `safety_guardrails.VALID_FIELDNAME_RE` now `fullmatch`.
- Trailing newline, `mapping._DECIMAL_ADD_RE` (a `$` pattern also used with `.match` in `frappe_backend.py`, which is not edited here) now ends in `\Z`.
- Searched `adapter/`, `api/`, `guarded_apply/`: `report_engine.IDENTIFIER_REGEX` is always applied after `.strip()`, `policy_expression._FIELD_NAME` is applied to Python AST names that cannot contain a newline, and `mapping._SAFE_IDENT_RE` is unused. All three are left unchanged (not reachable).
- In-memory vs offline engine: with no engine backend, `ChangeEngineAdapter._evaluate` now treats an unmapped, unprotected entity of the same Blueprint as an own entity. A backend that exists but lacks `can_grant_own_doctype` still fails closed. Residual: the in-memory adapter has no engine, so it cannot see a built-in document type that shares the derived name of a Blueprint entity (the engine path refuses that); it is a test double, not a deployment target.
- Wording: `route_guard.py` comment says reviewed set; ADR-0051 items 28, 52 and 53 updated (Proposed ADR, small edits).

## Files touched
- apps/engine/change_engine/change_engine/adapter/contracts_support.py: fullmatch and a schema-path re-check.
- apps/engine/change_engine/change_engine/adapter/mapping.py: `\Z` on `_DECIMAL_ADD_RE`.
- apps/engine/change_engine/change_engine/adapter/engine.py: in-memory own-entity check.
- apps/engine/change_engine/change_engine/guarded_apply/safety_guardrails.py: fullmatch.
- apps/engine/change_engine/change_engine/api/route_guard.py: comment only.
- apps/engine/change_engine/change_engine/tests/test_sec_022_review_followups_2.py: new tests (listed in `.github/workflows/tests.yml`, SEC-022 step).
- apps/engine/change_engine/change_engine/tests/test_sec_022_bpl_032_roles.py: the no-checker test no longer covers the in-memory adapter (moved to the new module).
- docs/decisions/ADR-0051-adapter-role-and-state-namespacing.md: wording.

## Decisions
- No new ADR; edits to Proposed ADR-0051.

## Tokens or cost
Unknown.

## Next step
Eldon's line-by-line review of this PR (Tier 3), then the open ADR-0051 item 4 follow-ups (drift fingerprint, user-permission scoping, managed-name registry).
