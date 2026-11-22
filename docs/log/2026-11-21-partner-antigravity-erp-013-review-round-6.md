# Session log: erp-013-review-round-6

Date: 2026-11-21
Author: partner
Tool and model: antigravity / Gemini 4 Neon (High)
Plan IDs: ERP-013

## Summary
Closed PR #202 Medium M1 and the link-field nit from Eldon's cross-model re-review of `2cb5de1` on `ERP-013`: codes, account numbers, link fields (including `customer_group`, `territory`, `supplier_group`, `item_group`), and batch metadata now refuse leading/trailing whitespace, non-ASCII whitespace, Unicode default-ignorable code points, and non-NFKC values with `IMP-SCHEMA`, keeping every file under 500 lines.

## Brief (ADR-0031 condition 4)
Fix PR #202 round 6 items (`ERP-013`, Tier 3, ledger-adjacent, tests first, minimal diff):
1. M1 (`importer/validation.py`): for codes, account numbers, link fields, and batch metadata (`batch_id`, `company`, `currency`, `tenant_id`, `posting_date`), refuse with `IMP-SCHEMA` any leading/trailing whitespace, any non-ASCII whitespace, any Unicode default-ignorable code point (covering `U+034F`, `U+FE0F`, `U+3164`, and all Unicode 15.0 `Default_Ignorable_Code_Point` ranges), and any value where `unicodedata.normalize("NFKC", value) != value`. Keep name fields on their existing rules (format marks allowed, keys stripped).
2. Review nit (`importer/validation.py`): treat `customer_group` and `territory` (along with `supplier_group` and `item_group`) as link fields rather than name fields so format marks and strict whitespace/ignorable/NFKC rules apply.
3. Documentation (`importer/README.md`): document the strict rules and state explicitly that it is UNVERIFIED whether the live engine strips whitespace on insert.
4. Tests (`test_erp_013_review_round6.py`, wired in `.github/workflows/tests.yml`): test each probe (`C1 `, ` C1`, NBSP `U+00A0`, `U+034F`, `U+FE0F`, `U+3164`, fullwidth `Ｃ１`) against customer codes, account numbers, link fields, and `batch_id` (plus `company`/`currency` and master links), and verify ordinary ASCII codes and Arabic names still pass.

## Files touched
- `apps/engine/change_engine/change_engine/importer/validation.py`: added Unicode 15.0 `DEFAULT_IGNORABLE_RANGES` and `_is_default_ignorable`; removed `customer_group`, `territory`, `supplier_group`, and `item_group` from `NAME_TEXT_FIELDS`; extended `text()` when `allow_format_marks=False` to refuse leading/trailing whitespace, non-ASCII whitespace, default-ignorable code points, and non-NFKC strings with `IMP-SCHEMA` (459 lines).
- `apps/engine/change_engine/change_engine/importer/README.md`: documented strict character/NFKC/whitespace rules on codes, account numbers, link fields, and batch metadata, noted UNVERIFIED whether the live engine strips whitespace on insert, and updated the test command glob (206 lines).
- `apps/engine/change_engine/change_engine/tests/test_erp_013_review_round6.py`: added 157 tests-first regressions covering all whitespace/ignorable/non-NFKC probes across customer codes, account numbers, opening and master link fields, `batch_id`, `company`, and `currency`, plus positive ASCII/Arabic and formula-precedence checks (197 lines).
- `apps/engine/change_engine/change_engine/tests/test_erp_013_review_fixes.py`: updated `variant="whitespace"` expectation in `test_opening_details_reject_links_to_same_master` from `IMP-DUPLICATE` to `IMP-SCHEMA` and removed the trailing space from `"w1"` in `test_stock_openings_allow_distinct_resolved_item_and_warehouse_pairs` (489 lines).
- `apps/engine/change_engine/change_engine/tests/test_erp_013_review_round4.py`: removed `\u200f` from `territory` in `test_alm_allowed_in_names_and_embedded_tab_is_schema_error` because `territory` is now validated as a link field (496 lines).
- `.github/workflows/tests.yml`: wired `test_erp_013_review_round6.py` into the `ERP-013` test step.

## Decisions
- Treated `supplier_group` and `item_group` consistently alongside `customer_group` and `territory` as link fields (all four are Link fields in the live engine).
- Recorded as UNVERIFIED in `importer/README.md` whether the live engine strips whitespace on insert; failing closed on leading/trailing and non-ASCII whitespace protects duplicate guards regardless.

## Verification
- Tests-first on `test_erp_013_review_round6.py` before implementation: 147 failed, 10 passed.
- After fixes:
  - `uv run --no-project --with pytest --with "pydantic>=2" env PYTHONPATH=apps/engine/change_engine:. python -m pytest apps/engine/change_engine/change_engine/tests/test_erp_013_*.py -q`: 322 passed.
  - `uv run --no-project --with pytest python -m pytest scripts/tests -q`: 22 passed, 29 subtests passed.
  - `python3 scripts/check_docs.py`: 0 errors, 0 warnings.
  - `python3 scripts/check_repo_hygiene.py`: OK.
  - `python3 scripts/scan_secrets.py`: 0 hits.
  - `python3 scripts/check_plan_independence.py`: OK.
  - `python3 scripts/check_lanes.py --base $(git merge-base origin/main HEAD) --actor partner`: OK.

## Tokens or cost
Unknown.

## Next step
Cross-model re-review of PR #202 (`ERP-013`) and Eldon's Tier 3 line-by-line human review (ADR-0031/0035), plus founder decisions on `Q-303`, `Q-478`, `Q-550`, `Q-551`, and `Q-554`.
