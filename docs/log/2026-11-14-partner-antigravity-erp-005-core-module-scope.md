# Session log: erp-005-core-module-scope

Date: 2026-11-14
Author: partner
Tool and model: antigravity / gemini-4-hydrogen
Plan IDs: ERP-005

## Summary
Defined the v1 core module, doctype, report, print format, and configuration-guardrail scope for trading and distribution in `docs/specs/core-module-scope-trading.md`, grounded in read-only inspection of the pinned synthetic bench.

## Files touched
- `docs/specs/core-module-scope-trading.md`: new spec covering scope rules, per-area doctype tables (`Selling`, `Buying`, `Stock`, `Accounts`, `Setup` and core/HRMS), reports and print formats, out-of-scope modules and `ERP-010` HRMS deferral, enforcement settings/flags, four-market consequences, inputs for `ERP-006`/`ERP-010`/`ERP-011`/`ERP-014`, and open questions.
- `docs/PLAN.md`: set `ERP-005` status to `doing` (orchestrator marks `done` after review).
- `docs/open-questions.md`: appended `Q-21`..`Q-24` (valuation method default `FIFO` vs `Moving Average`, rounding method default `Banker's Rounding (legacy)` vs `Commercial Rounding`, `enable_immutable_ledger` confirmation, and optional trading doctypes).

## Decisions
- No ADR. Scope proposals requiring founder agreement (`Q-21`..`Q-24`) are flagged `PROPOSED` in the spec and logged in `docs/open-questions.md`.

## Evidence (2026-11-14, read-only inspection of synthetic bench `erp001.localhost`)
- Inspected `list-apps` (`frappe 15.126.0`, `erpnext 15.124.5`, `hrms 15.64.8`, `change_engine 0.1.0`), `Module Def`, `DocType`, `Report`, `Print Format`, `Role`, `Domain`, `Workspace`, `DocField` metadata, and settings singletons (`Stock Settings`, `Accounts Settings`, `Selling Settings`, `Buying Settings`, `Global Defaults`, `System Settings`, `Domain Settings`).
- No writes or migrations were run on the bench.

## Review (orchestrator, claude-code / claude-fable-5-2, a different model from the author)
- Every backticked doctype, report, print format and module name in the spec was checked against the bench metadata: all exist. Module attribution, singleton and submittable flags and the quoted setting defaults were re-read from the bench and match.
- Corrected: HR count (78 non-child doctypes, not 77), the Regional list (added `UAE VAT Account`), a pointer to a folder that does not exist on this branch, and the question numbers (Q-21 to Q-24, because Q-17 to Q-19 are taken by an open PR).
- Not checked: runtime enforcement of the proposed settings (needs ERP-014, ERP-021, ERP-022). The scope choices are PROPOSED until both founders review the PR.

## Tokens or cost
Not measured.

## Next step
Founders review the spec in the PR and answer `Q-21`..`Q-24`; the row then unblocks `ERP-006`, `ERP-010`, `ERP-011`, and `ERP-014`.
