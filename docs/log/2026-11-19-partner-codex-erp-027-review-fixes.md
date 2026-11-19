# Session log: erp-027-review-fixes

Date: 2026-11-19
Author: partner
Tool and model: codex / gpt-6.1-sol
Plan IDs: ERP-027

## Summary
Completed the interrupted ERP-027 DDL re-review fixes: exact approved/no-op statement admission before SQL dispatch, quote-aware parsing and complete table read-back. ERP-027 stays doing pending Gemini review.

## Files touched
- `guarded_apply/ddl_plan_gate.py`: complete the saved strict literal/type grammar, exact no-op allowlist, default/null/collation checks and full before/after schema comparison. Unknown SQL and obscured/multiple statements fail closed; ordinary transaction commands remain usable.
- `api/endpoints.py`: validate each pending DDL batch prefix before forwarding either db.sql or db.sql_ddl, retain accepted executed statements once, and restore original methods on errors. The saved code already addressed live caller fallbacks and snapshot error handling.
- `tests/test_erp_027_decimal_drift.py`: recover and finish the saved re-review matrix; exercise pre-dispatch rejection, quoted/default parsing, schema invariants, four adapter callers and legitimate transaction restarts.
- `docs/PLAN.md`: ERP-027 stays doing; preserve other founders' merged row states.

## Decisions
- An arbitrary MODIFY is never accepted because final snapshots happen to match. Only exact regenerations of supported before-snapshot definitions may run, at most once per column.
- Apply admission happens before SQL execution: narrowing then restoring a column must not execute and truncate data before a later snapshot detects the violation.
- The schema reader serializes SQL NULL as the string None; normalize that sentinel without changing quoted string defaults. No ledger, tax, payroll or contract behavior changed.
- The existing gate and recovered regression matrix exceed the approximate file/PR size guidelines. The whole change remains a focused ERP-027 fix; independent review must assess that size.

## Tokens or cost
Unknown.

## Next step
Gemini re-review at the pushed SHA; founder review follows. Do not close ERP-027 until the review is clean. No phase exit or merge claimed.

## Verification

- Reproduced interrupted import failure (the partial gate removed is_ddl_statement before callers were updated); completed the caller/checker wiring.
- Focused suite: 99 passed and 104 subtests passed.
- Adapter, apply-preview and API regression suites: 30 passed.
- Real pinned bench: Frappe 15.126.0, ERPNext 15.124.5 and MariaDB 11.4. Fresh Data fields applied on Customer, Sales Order, Sales Invoice and Item; each returned APPLIED/VERIFIED_CONSISTENT without warnings, and Custom Field metadata plus varchar(140)/nullable column read-back matched.
- Real negative control: deliberately changing Sales Order grand_total's decimal default produced REJECTED at INSPECT; the attempted new column and Custom Field metadata stayed absent. The default was restored after the check.
- The live run found START TRANSACTION was incorrectly classified as DDL by the partial rewrite. A new test failed on that exact behavior, then passed after the transaction verb was admitted. Unplanned/comment-prefixed and multi-statement DDL are still refused before dispatch.
- Before/after evidence remains outside the repository; no logs, secrets or synthetic database exports are committed.
