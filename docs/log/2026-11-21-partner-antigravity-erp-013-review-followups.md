# Session log: erp-013-review-followups

Date: 2026-11-21
Author: partner
Tool and model: antigravity / Gemini 4 Neon (High)
Plan IDs: ERP-013

## Summary
Resolved the three non-blocking Low follow-ups from Eldon's approving review of PR #202 (`99f3ca8`, `ERP-013`, Tier 3): refused name-key twins in `NAME_TEXT_FIELDS`, restored append-only `IMP-AUTH` failure logging in `apply` and `confirm`, and recorded open question `Q-556` for UNVERIFIED live engine code collation.

## Brief (ADR-0031 condition 4)
Address the three Low follow-ups from Eldon's approving review of PR #202 (`ERP-013`, Tier 3, rigid zone: refuse, never repair; tests first; every file under 500 lines):
1. Refuse with `IMP-SCHEMA` in `NAME_TEXT_FIELDS`: leading/trailing whitespace, any non-ASCII space, any default-ignorable code point except the five safe Arabic marks (`\u200c`, `\u200d`, `\u200e`, `\u200f`, `\u061c`), and runs of internal ASCII spaces (refuse, never repair); preserve Arabic names with safe marks (still stripped in `business_key`) and ordinary names with single inner spaces.
2. Record `Q-556` in `docs/open-questions.md` (owner `partner`, gate `G2`, links `ERP-013`) for UNVERIFIED engine collation on visible code twins (`C1`/`c1`, `X Y`/`X  Y`, Arabic-Indic vs ASCII digits), keeping codes unchanged.
3. Restore append-only failure-log writes for `IMP-AUTH` raised inside `apply` or `confirm` (`importer/engine.py`) without logging secrets or caller-supplied roles.

## Files touched
- `apps/engine/change_engine/change_engine/importer/validation.py`: tightened `text()` for `allow_format_marks=True` (`NAME_TEXT_FIELDS`) to refuse leading/trailing whitespace (including mark-masked edge whitespace), non-ASCII spaces, default-ignorables other than `SAFE_FORMAT_MARKS`, and runs of internal ASCII spaces (`IMP-SCHEMA`); codes (`allow_format_marks=False`) unchanged (465 lines).
- `apps/engine/change_engine/change_engine/importer/engine.py`: removed `"IMP-AUTH"` from the `_record_failure` exclusion set, moved post-deepcopy `_authorize` in `apply()` inside `try:` (matching `confirm()`), and anchored `tenant` in `confirm()` and `apply()` to the authenticated identity/validated initial plan so `IMP-AUTH` raised inside `apply` or `confirm` is logged append-only with the authenticated `user_id` and no secrets or caller-supplied roles (181 lines).
- `apps/engine/change_engine/change_engine/importer/README.md`: documented strict name-field hygiene (refuse, never repair), `Q-556` code-collation tracking, and `IMP-AUTH` failure logging inside `apply`/`confirm`.
- `apps/engine/change_engine/change_engine/tests/test_erp_013_review_followups.py`: added tests-first regressions for name-field twins (within one batch and against stored masters across `NAME_TEXT_FIELDS`), positive Arabic/safe-mark and single-space cases, and `IMP-AUTH` failure logging in `apply` and `confirm` without leaking secrets or roles (249 lines).
- `apps/engine/change_engine/change_engine/tests/test_erp_013_review_fixes.py`: updated two existing verbatim-prior-value fixtures from `"  Before  "` to `"\u200fBefore"` so they remain valid under the new leading/trailing whitespace refusal while still proving verbatim preservation (489 lines).
- `.github/workflows/tests.yml`: listed `apps/engine/change_engine/change_engine/tests/test_erp_013_review_followups.py` in the existing ERP-013 step.
- `docs/open-questions.md`: added `Q-556` (owner `partner`, gate `G2`, links `ERP-013`).

## Decisions
- Internal ASCII space runs in `NAME_TEXT_FIELDS` are refused (`IMP-SCHEMA`) rather than collapsed, preserving the rigid-zone rule "refuse, never repair".
- Codes (`allow_format_marks=False`) remain untouched; UNVERIFIED live engine collation on visible twins (`C1`/`c1`, `X Y`/`X  Y`, Arabic-Indic vs ASCII digits) is tracked in `Q-556`.
- Entry-level unauthenticated/cross-tenant `IMP-AUTH` refusals still fail before payload inspection and write nothing to the target tenant's failure log; `IMP-AUTH` raised inside `apply` or `confirm` after initial authorization is recorded append-only in `import_failures`.

## Verification
- Tests-first before fix (`PYTHONPATH=apps/engine/change_engine:. uv run --no-project --with pytest --with "pydantic>=2" python -m pytest apps/engine/change_engine/change_engine/tests/test_erp_013_*.py -q`): 67 failed, 334 passed.
- After fix:
  - `PYTHONPATH=apps/engine/change_engine:. uv run --no-project --with pytest --with "pydantic>=2" python -m pytest apps/engine/change_engine/change_engine/tests/test_erp_013_*.py -q`: 401 passed.
  - `uv run --no-project --with pytest python -m pytest scripts/tests -q`: 22 passed, 29 subtests passed.
  - `python3 scripts/check_docs.py`: 0 errors, 0 warnings.
  - `python3 scripts/check_repo_hygiene.py`: passed.
  - `python3 scripts/scan_secrets.py`: 0 hits.
  - `python3 scripts/check_plan_independence.py`: passed.
  - `python3 scripts/check_lanes.py --base origin/main --actor partner`: passed.

## Tokens or cost
Unknown.

## Next step
Cross-model review and Tier 3 human line-by-line review (Eldon) of the ERP-013 follow-up PR; continue live-wiring and founder decisions tracked in `Q-303`, `Q-478`, `Q-550`, `Q-551`, `Q-554`, and `Q-556`.
