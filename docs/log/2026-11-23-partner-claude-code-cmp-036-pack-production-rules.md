# Session log: cmp-036-pack-production-rules

Date: 2026-11-23
Author: partner
Tool and model: claude-code (Sonnet 5.5, as the implementation sub-agent for the partner's coordinator thread)
Plan IDs: CMP-036,CMP-035

## Summary
Built CMP-036, test-first: production loading now needs a per-market product-choice list for PLATFORM-DEFAULT facts on locked paths, refuses open blockers and pending references (resolved only by a recorded status, founder login and date), and applies the Lows from Eldon's review of #282 (evidence status, duplicate keys, manifest meaning, closed evidence keys, founder and reviewer binding, nesting and date hygiene). The four shipped packs stay refused in production and load in sandbox and test; no pack JSON changed.

## Files touched
- components/compliance/country_pack/evidence.py: product-choice list reader and path rule, locked-path PLATFORM-DEFAULT check, verified_official label reconciliation, open-blocker and outside-fact checks, `accessed` lower bound, closed evidence key set
- components/compliance/country_pack/certification.py: founders map binding (owner, reviewer, approving founder), manifest meaning checks, `requires` resolution, strict reads
- components/compliance/country_pack/loader.py: strict reads for pack.json, clean refusal on deep nesting
- components/compliance/country_pack/strict_json.py (new): duplicate-key and recursion-safe JSON reading
- components/compliance/country_pack/product_choice_paths.json (new): per-market list; Saudi rounding provisional (Q-601), UAE and Qatar rounding provisional (UNVERIFIED), Egypt empty
- components/compliance/country_pack/tests/test_production_rules.py (new): 44 tests, one group per rule
- components/compliance/country_pack/tests/test_country_pack_go_live_gate.py: fixture owner and reviewer are now founder logins (sayegh9, EldonsLogic); the founder-loop test sets owner and reviewer per founder
- components/compliance/country_pack/tests/test_certification_evidence.py: the "PLATFORM-DEFAULT with a ref loads" assertion now expects the product-choice refusal (ADR-0067 reverses it)
- components/compliance/country_pack/tests/pack_checks.py: CI `pending()` counts only open entries
- docs/decisions/ADR-0067-country-pack-production-blockers-and-product-choice.md (new, Proposed); docs/decisions/INDEX.md: new row, ADR-0063 row notes the ADR-0059 amendment
- docs/compliance/country-pack-framework.md: documents the new production rules

## Decisions
- [ADR-0067](../decisions/ADR-0067-country-pack-production-blockers-and-product-choice.md) (Proposed): Q1 option C, Q2 option A, blocker resolution record, the Lows. Readings I chose and flagged for review: `resolution.by` must be a founder login; an outside-schema entry blocks only when it lists a locked path in `paths`; `verified_official` is checked per locked leaf; `requires` resolution checks ids and capabilities, not version ranges; the approving founder must be the manifest owner's founder.
- No new open question: Q-601 already covers the Saudi rounding answer.

## Tokens or cost
Unknown.

## Next step
Eldon's Tier 3 review and a different-model security review of this PR. Then, per market, the accountant answers behind the provisional list entries (Q-601) and rework of the Egypt identity-path defaults before any pack is certified.

## Review fixes
ChatGPT gpt-6.1-sol review of #300 at 1998c4a, fixed test-first (new tests in `tests/test_production_review_fixes.py`, shared helper in `test_production_rules.py`). Implementation sub-agent: claude-code (Sonnet 5.5). No pack JSON, statutory fact or tax maths changed.
1. High, unscoped `UNVERIFIED` outside-schema entry loaded: `blocker_refusals` now refuses an `UNVERIFIED` `factsOutsideSchema` entry whose `paths` is missing, not a list or empty; replaced the old test that expected acceptance.
2. High, `requires` checked names only: `certification._providers` registers only manifests that pass the component contract; a requirement needs a provider with a release version in `versionRange`. Strict comparator `version_in_range` (`||`, single-space AND, `>=` `<=` `>` `<` `=` `^` `~` with full `X.Y.Z`; wildcards, partials, prereleases, hyphen ranges, odd spacing refused). `compliance.zatca_sa >=9999.0.0` now refuses against the real registry; the old test's incomplete provider now uses a contract-valid one.
3. High, provisional product-choice entries authorised defaults: new `active_product_choice_paths`; a provisional entry needs `resolution` {`status`, `by`, `at`, `ref`} (same checks as a blocker resolution plus a nonblank `ref`) or it is inactive in production. SA, AE and QA rounding entries stay in the list, marked provisional; tests that loaded a rounding default now use `eInvoicing.mode`.
4. Medium, TypeError on malformed `requires` and scanned manifests: type guards return refusal reasons; loader-level tests cover `component: {}`, `capability: []`, both or neither key, bad `versionRange`, non-list `requires`, registered manifests with `id: {}` and other bad shapes, plus a mutation sweep of manifest and evidence fields that asserts only `PackValidationError` escapes.
ADR-0067 (Proposed) and the framework doc now state these readings. Tests proving each finding failed on 1998c4a before the fixes (run against the unfixed code); the sweep tests and a few guards passed before and stay as regressions.

## Re-review fix (coordinator, Claude Opus 5.5)
- gpt-6.1-sol re-review at `2ce73b1`: findings 1 to 3 closed; finding 4 partly open (a 5,000-digit version segment escaped as `ValueError` from `int()`). Fixed test-first: version segments are capped at 9 digits, so longer numbers do not parse and are refused; an unusable provider is skipped and does not hide a valid one. New test `test_oversized_version_numbers_refuse_cleanly` failed before the fix. Suite: 197 tests OK.
- Re-review 2 at `f6a82be`: finding 4's requires and provider cases closed; two older exception paths found. Fixed test-first: `loader.py` tax-pattern check now also catches `OverflowError` (and `RecursionError`) from `re.compile` (e.g. `a{4294967295}`), recording a validation error; `_semver_key` returns None when a segment exceeds `int()`'s digit limit, so an oversized version selector is `PackNotFoundError`. New tests `test_oversized_regex_repeat_in_a_tax_pattern_refuses_cleanly` and `test_oversized_version_selector_is_not_found` failed before the fix. Suite: 199 tests OK.
- Re-review 3 at `01d2029`: both round-2 paths closed; one more Medium (schema-valid nesting in `holidays.announcedDates` passed every check, then `copy.deepcopy` raised `RecursionError`). Fixed test-first: the final copy now refuses with "nested too deeply". New test `test_schema_valid_deep_nesting_refuses_cleanly` failed before the fix. Suite: 200 tests OK.

## Corrections (review of #300)
Dated 2026-11-24. Eldon's review of #300 at 4ea5173 found stale text and several gaps. Implementation sub-agent: claude-code (Sonnet 5.5), fixed test-first. Earlier text above is left as written.
- The "Decisions" section is stale in two places. `requires` is not names-only: it resolves to a registered provider whose release version is inside `versionRange` (see "Review fixes"). An outside-schema entry does not block only when it lists a locked path: an `UNVERIFIED` entry with missing, non-list or empty `paths` also blocks.
- Medium 1: Saudi `tax.roundingRule` removed from `product_choice_paths.json`; ZATCA XML Implementation Standard v1.2 section 10 mandates half-up, so it is statutory and needs `VERIFIED-OFFICIAL` or signed `SECONDARY` evidence. ADR-0067 and the framework doc say so. UNVERIFIED: `half_away_from_zero` vs half-up for negative amounts (for the accountant). `docs/open-questions.md` untouched; Q-601's status is a founder decision. No rounding maths changed.
- Low 1: ADR-0067 no longer says the list covers every path that defaults today; it names the locked, unlisted `formats.*` (SA, AE) and `printFormats.*` (SA) defaults, refused in production, with a founder decision pending.
- Low 2: `is_product_choice_path` now requires an exact match (no descendants); list file description, ADR-0067 and the framework doc updated; new tests refuse a child path.
- Low 3: CI's `pending()` (`tests/pack_checks.py`) loads the founder set from `scripts/lanes.json` through `certification._founders()`, so it is no weaker than production; new test.
- Low 4: this section.
- Low 5: the `localeDefaults` and `localeDefaults.holidays` cases were added to `test_unverified_outside_entry_on_a_locked_path_refuses`; changing `_overlaps_locked` to `covered` in `blocker_refusals` made it fail, then the mutation was reverted.
- Nit: an outside-schema `PLATFORM-DEFAULT` entry that names a locked path is now refused unless that exact path is on the active list (fail closed); new test.

## Founder decision on display formats (2026-11-24)
- Eldon's decision on #300 (for both founders; the partner agreed on 2026-11-24): Saudi and UAE `formats.numberSystem`, `formats.decimalSeparator`, `formats.thousandsSeparator`, `formats.gregorianDateFormat`, and Saudi `printFormats.legalLayoutPrecedence` and `printFormats.templates` are active product choices (display, not tax). These are exactly the locked paths the SA and AE packs back with `PLATFORM-DEFAULT` today; `formats.currency`, `formats.currencyDecimals`, `formats.hijriDateFormat` and the UAE `printFormats.*` carry UNVERIFIED evidence and stay unlisted.
- Changed by the coordinator (Claude Opus 5.5), test-first: `product_choice_paths.json`; `test_production_rules.py` (pinned list; new `test_display_format_choices_are_active_exact_leaves`, 11 failures before the data change); `test_production_review_fixes.py` (settled Saudi list); ADR-0067 item 1; framework doc. Country pack suite: 205 OK.
