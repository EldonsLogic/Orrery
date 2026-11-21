# Session log: erp-013-review-round-5

Date: 2026-11-21
Author: partner
Tool and model: antigravity / Gemini 4 Neon (High)
Plan IDs: ERP-013

## Summary
Addressed PR #202 round 5 review findings (L1, L2, L3, Nit) from the cross-model re-review of `2cb5de1` on `ERP-013`, following Tier 3 tests-first workflow and keeping every file under 500 lines.

## Brief (ADR-0031 condition 4)
Fix the four items from the PR #202 round 5 re-review of `2cb5de1` (`ERP-013`, Tier 3, ledger-adjacent, tests first):
1. L1 (`importer/backend.py`): replace `executescript` in the legacy `import_distinct_confirmations` rebuild with separate `execute()` calls inside `with self.transaction():`, dropping any leftover `import_distinct_confirmations_v2` first; test interrupted-migration recovery and atomic rollback on mid-migration failure.
2. L2 (partner decision): key AR and AP duplicate detection on `(party, control account)` so a party with balances across two control accounts can be imported while per-account reconciliation stays exact; keep Stock as one row per `(item, warehouse)`; update `importer/README.md` and record open question `Q-554` (UNVERIFIED live engine per-row receivable/payable opening posting, owner `partner`, gate `G2`, links `ERP-013`).
3. L3: store `pending_plan_hash` with each distinct confirmation and require it to match at `preview`/`apply` (preserving idempotent retries of already-applied batches); test that a master-only change after `confirm()` invalidates the confirmation.
4. Nit: record a sanitized failure row in `import_failures` with the authenticated `user_id` for refused `confirm()` calls (wrong/stale hash, wrong id list, wrong `confirmed_by`); test.

## Files touched
- `apps/engine/change_engine/change_engine/importer/backend.py`: made legacy `import_distinct_confirmations` migration atomic via separate `execute()` calls inside `BEGIN IMMEDIATE` with `DROP TABLE IF EXISTS import_distinct_confirmations_v2`; stored and matched `pending_plan_hash` on `import_distinct_confirmations` and `import_batches` (302 lines).
- `apps/engine/change_engine/change_engine/importer/validation.py`: keyed AR/AP duplicate detection on `(party, control account)` while keeping Stock on `(item, warehouse)`; passed `pending_hash` to `distinct_lookup` and exposed `plan["pending_plan_hash"]` (429 lines).
- `apps/engine/change_engine/change_engine/importer/engine.py`: bound `distinct_confirmations` lookup and `record_distinct_confirmation` to `pending_plan_hash` (with exact-retry lookup via committed `journal`); logged refused `confirm()` attempts in `import_failures` with the authenticated `user_id` via shared `_record_failure` helper (181 lines).
- `apps/engine/change_engine/change_engine/importer/README.md`: documented `(party, control account)` AR/AP duplicate keys with `Q-554` and `pending_plan_hash` binding for `confirm`/`preview`/`apply` (200 lines).
- `apps/engine/change_engine/change_engine/tests/test_erp_013_review_round4.py`: added tests-first Round 5 regressions for L1 (interrupted migration recovery + atomic rollback on RENAME failure), L2 (`C1 @ 1100=60` + `C1 @ 1110=40`, duplicate `C1 @ 1100`, AP, Stock), L3 (master-only change invalidates confirmation and journals new confirmer), and Nit (refused `confirm()` failure rows) (496 lines).
- `docs/open-questions.md`: added `Q-554` (owner `partner`, gate `G2`, links `ERP-013`).

## Decisions
- Partner decision (L2): AR and AP duplicate keys are `(party, control account)` while Stock remains `(item, warehouse)`; live engine per-row receivable/payable opening posting is UNVERIFIED and tracked in `Q-554`.
- Distinct confirmations are bound to `pending_plan_hash`; legacy migrated rows store `NULL` and fail closed until re-confirmed against the current pending plan hash.

## Verification
- Tests-first on `test_erp_013_*.py` before implementation: 5 failed, 160 passed.
- After fixes:
  - `uv run --no-project --with pytest --with "pydantic>=2" env PYTHONPATH=apps/engine/change_engine:. python -m pytest apps/engine/change_engine/change_engine/tests/test_erp_013_*.py -q`: 165 passed.
  - `uv run --no-project --with pytest python -m pytest scripts/tests -q`: 22 passed, 29 subtests passed.
  - `python3 scripts/check_docs.py`: 0 errors, 0 warnings.
  - `python3 scripts/check_repo_hygiene.py`: OK.
  - `python3 scripts/scan_secrets.py`: 0 hits.
  - `python3 scripts/check_plan_independence.py`: OK.
  - `python3 scripts/check_lanes.py --base $(git merge-base origin/main HEAD) --actor partner`: OK.

## Tokens or cost
Unknown.

## Next step
Tier 3 human line-by-line review (Eldon) and cross-model re-review of PR #202 (`ERP-013`), plus founder decisions on `Q-303`, `Q-478`, `Q-550`, `Q-551`, and `Q-554`.
