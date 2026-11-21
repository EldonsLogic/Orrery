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

## Fix round 1
Addressed Eldon's Fable 5.2 review and the independent Opus review of PR #245 (`ERP-013`, Tier 3, rigid zone: refuse, never repair; tests first):
1. **High — tenant binding in `apply()`, `confirm()`, `preview()`/`validate()` (`importer/engine.py`):**
   - Correction to the earlier log entry above: at `b0d1c4f`/`7af58d1`, `apply()` did **not** anchor `tenant` to the authenticated identity — it took `tenant, batch_id = initial["tenant_id"], initial["batch_id"]` from the pre-detachment plan. That claim is now true: `apply()` takes `tenant, user_id = identity["tenant_id"], identity["user_id"]` from the initial `_authorize(source)` and, inside `try` after `bounded(source)` -> `copy.deepcopy(source)` -> second `_authorize(detached)`, raises `IMP-AUTH` unless `reauth["tenant_id"] == tenant`, `reauth["user_id"] == user_id`, `detached["tenant_id"] == tenant`, `detached["batch_id"] == batch_id`, and `initial["tenant_id"] == tenant` — before any `journal`, `claim_opening`, or `write` runs. Failure rows always go to the authenticated `(tenant, user_id)`.
   - Scope note: `b0d1c4f` moved `deepcopy` and the second `_authorize` inside `try` in `apply()` so post-initial-auth `IMP-AUTH` failures are recorded append-only; fix round 1 retains that placement while binding failure logging strictly to the initial authenticated tenant and user.
   - Applied the same detachment and re-authorization binding to `confirm()` (checking `reauth["tenant_id"]`, `reauth["user_id"]`, `detached["tenant_id"]`, and `detached_batch_id` before transaction/write) and `preview()`/`validate()` (`bounded` -> `deepcopy` -> re-authorize -> verify `tenant` before `_prepare`).
2. **Low — non-NFC names and `U+2800` / blank-filler twins (`importer/validation.py`, `docs/open-questions.md`):**
   - Refused non-NFC values (`unicodedata.normalize("NFC", value) != value`) in name fields (`allow_format_marks=True`) with `IMP-SCHEMA`; did **not** apply NFKC refusal to names. Verified NFC `Café` and common Arabic names (including hamza forms, tatweel, and all five safe marks) pass verbatim while NFD `Café` and decomposed Arabic hamza fail.
   - Refused `U+2800` (Braille pattern blank) with `IMP-SCHEMA` and verified existing `IMP-SCHEMA` coverage for `U+3000`, `U+115F`, `U+1160`, and `U+3164` with explicit tests.
   - Recorded fullwidth (`Ｃａｓｈ` next to `Cash`) and Arabic presentation-form twins in names as a residual in the `Q-556` row of `docs/open-questions.md`.
3. **Low — `Cf` default-ignorable refusal code wording (`importer/README.md`, PR body correction):**
   - Correction to the PR #245 body and previous README wording: `Cf` default-ignorables in names (`U+200B`, `U+00AD`, `U+2060`, `U+FEFF`, `U+180E`, Unicode tag characters) are refused with `IMP-FORMULA` (existing behaviour in `validation.py:135`, unchanged), whereas non-`Cf` default-ignorables, `U+2800`, non-ASCII whitespace, space runs, and non-NFC names are refused with `IMP-SCHEMA`. Updated `importer/README.md` and added explicit name regression tests asserting `IMP-FORMULA`.

### Fix round 1 verification
- Tests-first before fix (`PYTHONPATH=apps/engine/change_engine:. uv run --no-project --with pytest --with "pydantic>=2" python -m pytest apps/engine/change_engine/change_engine/tests/test_erp_013_*.py -q`): **7 failed, 411 passed**.
- After fix:
  - `PYTHONPATH=apps/engine/change_engine:. uv run --no-project --with pytest --with "pydantic>=2" python -m pytest apps/engine/change_engine/change_engine/tests/test_erp_013_*.py -q`: **418 passed**.
  - `uv run --no-project --with pytest python -m pytest scripts/tests -q`: **22 passed, 29 subtests passed**.
  - `python3 scripts/check_docs.py`: 0 error(s), 0 warning(s).
  - `python3 scripts/check_repo_hygiene.py`: Repo hygiene OK (1765 files checked).
  - `python3 scripts/scan_secrets.py`: 0 hit(s).
  - `python3 scripts/check_plan_independence.py`: Plan independence OK.
  - `python3 scripts/check_lanes.py --base origin/main --actor partner`: Lane check OK.

## Fix round 2
Addressed the Claude Opus 5.5 cross-model security re-review of `a4106ec` (PR #245, `ERP-013`, Tier 3, rigid zone: refuse twins, never repair stored values; tests first):
1. **Medium — `apply()` binding order before any backend read (`importer/engine.py`):**
   - Correction to the Fix round 1 log entry above: at `a4106ec`, `apply()` still ran `initial, _ = self._prepare(source)` on the caller-owned `source` **before** `bounded`, `copy.deepcopy`, re-authorization, and the tenant/batch check — so a mid-call tenant mutation still triggered `company_currency`, `master`, and `journal` reads against `tenant-b` (and leaked `IMP-CURRENCY` instead of `IMP-AUTH` when `tenant-b` had no configured currency).
   - Reordered `apply()` so `_authorize(source)` -> capture `tenant`, `user_id`, `batch_id` -> `bounded(source)` -> `detached = copy.deepcopy(source)` -> `_authorize(detached)` -> `tenant`/`user_id`/`batch_id` match check run **before** `_prepare(detached)` or any backend call (`company_currency`, `master`, `journal`, `claim_opening`, `write`). `IMP-AUTH` failures log only to the initial authenticated `(tenant, user_id)` and close the `IMP-CURRENCY` vs `IMP-AUTH` oracle.
   - Aligned `preview()`/`validate()` (also binding `user_id` and `batch_id`) and `confirm()` (moving detachment and re-authorization ahead of `IMP-CONFIRM` checks) to the same pre-backend-read ordering.
   - Added spies on `company_currency`, `master`, `journal`, `claim_opening`, and `write` to every `apply` mutation test (updating `test_erp_013_review_followups.py` and adding oracle and cross-entry-point regressions in `test_erp_013_review_followups_r2.py`, listed by path in `.github/workflows/tests.yml`).
2. **Medium — remove non-NFC refusal on names; key names on `NFC` without modifying stored values (`importer/validation.py`, `importer/README.md`):**
   - Removed the round-1 non-NFC `IMP-SCHEMA` refusal from `text(..., allow_format_marks=True)` so vocalised Arabic (e.g. `محمَّد` typed with shadda before fatha, combining hamza/madda, tanween, kasra) and NFD Latin names (`Café`) are accepted and stored byte-identical to input. Never repairs stored values; never applies `NFKC` to names.
   - Updated `business_key()` and `_resolve_master()` (`_key_value`) to compute name keys on `unicodedata.normalize("NFC", ...)` after stripping `SAFE_FORMAT_MARKS`, and updated `master_context()` to refuse with `IMP-DUPLICATE` when an incoming name-keyed master collides on key with a stored master whose stored spelling differs. Canonically equivalent twins are refused as `IMP-DUPLICATE` both within a batch and against stored masters.
   - Updated `importer/README.md` to document the refuse-twins, never-repair-stored-values rule.
3. **Low — blank-rendering glyph residual (`docs/open-questions.md`):**
   - Recorded `U+1D159` (`Cash` + `U+1D159`, Musical Symbol Null Notehead) as a residual in the `Q-556` row only (no code change).

### Fix round 2 verification
- Tests-first before fix (`PYTHONPATH=apps/engine/change_engine:. uv run --no-project --with pytest --with "pydantic>=2" python -m pytest apps/engine/change_engine/change_engine/tests/test_erp_013_*.py -q`): **11 failed, 417 passed**.
- After fix:
  - `PYTHONPATH=apps/engine/change_engine:. uv run --no-project --with pytest --with "pydantic>=2" python -m pytest apps/engine/change_engine/change_engine/tests/test_erp_013_*.py -q`: **428 passed**.
  - `uv run --no-project --with pytest python -m pytest scripts/tests -q`: **22 passed, 29 subtests passed**.
  - `python3 scripts/check_docs.py`: 0 error(s), 0 warning(s).
  - `python3 scripts/check_repo_hygiene.py`: Repo hygiene OK (1766 files checked).
  - `python3 scripts/scan_secrets.py`: 0 hit(s).
  - `python3 scripts/check_plan_independence.py`: Plan independence OK.
  - `python3 scripts/check_lanes.py --base origin/main --actor partner`: Lane check OK.

## Round 2 review Lows (coordinator, Claude Opus 5.5)
An Opus re-review of e20d02b approved round 2. Its proof of concept made 56 runs, and none called the backend for tenant-b. It left three Lows:
- **Fixed, low 1 (pre-existing):** a dict subclass could answer `tenant_id` differently on a later read. `copy.deepcopy` keeps a subclass's `__getitem__`. `bounded()` now accepts only exact built-in types (`_PLAIN_TYPES`) and refuses any subclass with `IMP-SCHEMA` before the copy.
  - Tests in `test_erp_013_review_followups_r2.py`: a plain dict subclass and a str subclass are refused, and a tenant-shifting dict subclass writes to neither tenant.
  - Before the fix, 2 of these failed. After it, all 431 ERP-013 tests pass.
- **Documented, low 2:** a reference to a master whose name was typed in non-NFC form must be given in NFC. The as-typed spelling is refused with `IMP-SCHEMA` (fails closed). This is now in the README.
- **Accepted, low 3:** U+1D159 is recorded in Q-556.
