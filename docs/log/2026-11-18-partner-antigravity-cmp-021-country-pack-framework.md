# Session log: cmp-021-country-pack-framework

Date: 2026-11-18
Author: partner
Tool and model: antigravity / gemini-4-hydrogen
Plan IDs: CMP-021

## Summary
Implemented the `CMP-021` country pack framework specification, Draft 2020-12 pack manifest JSON Schema, fail-closed loader/validator/override merger under `components/compliance/country_pack/`, test-only sample pack fixture, unit tests, CI hook, and `Q-260` (renumbered after merging `origin/main`) for `eldon` on Blueprint schema pack selection without editing `contracts/`.

## Files touched
- `docs/PLAN.md`: claimed `CMP-021` by setting status to `doing`.
- `docs/compliance/country-pack-framework.md`: framework specification covering pack contents, disk layout, overridable vs locked settings, Blueprint company profile selection (plus proposed `contracts/` updates), and pack versioning/upgrades across the four phase-1 markets (`SA`, `AE`, `EG`, `QA`).
- `docs/open-questions.md`: appended `Q-260` (renumbered after merging `origin/main`) for `eldon` on Blueprint schema pack selection, identifier regex delegation, locale currency lockability, and QA/EG e-invoicing & payroll enums.
- `components/compliance/country_pack/__init__.py`: public exports for the country pack loader, validator, and override resolver.
- `components/compliance/country_pack/pack.schema.json`: Draft 2020-12 JSON Schema for country pack manifests (`pack.json`), including strict Blueprint-aligned `reducedPeriod` schema.
- `components/compliance/country_pack/loader.py`: disk loader (`<packs_root>/<country>/<version>/pack.json`), strict `jsonschema.Draft202012Validator` schema/invariant validator (fails loudly if `jsonschema` is absent), `testOnly` enforcement (`allow_test_packs=False` default), pinned version requirement in `resolve_country_pack`, Blueprint-aligned `reducedPeriods` validation, and fail-closed override merger (`apply_company_overrides` / `resolve_country_pack`) with zero per-country code branches.
- `components/compliance/country_pack/tests/__init__.py`: test package init.
- `components/compliance/country_pack/tests/sample_packs/sa/0.1.0/pack.json`: minimal test-only sample pack (`testOnly: true`, no real tax rates or statutory rules).
- `components/compliance/country_pack/tests/test_country_pack.py`: unit tests covering valid load, `testOnly` and unpinned resolve rejection, schema validation, invalid pack/reducedPeriod rejection, locked-setting override rejection, allowed overrides, post-merge constraint rejection, semver selection filtering `testOnly` packs, and unknown-country fail-closed behaviour.
- `.github/workflows/tests.yml`: added CI execution of `components/compliance/country_pack/tests` (with `jsonschema` installed).

## Decisions
- Followed [ADR-0015](../decisions/ADR-0015-country-packs-calendars-locale.md) and [ADR-0024](../decisions/ADR-0024-four-phase-1-markets.md); left `contracts/` untouched and recorded proposed Blueprint schema questions in [open-questions.md](../open-questions.md) (`Q-260`).

## Tokens or cost
Unknown.

## Next step
Review PR for `CMP-021` (different model/founder), answer `Q-260` in `contracts/`, and proceed to `CMP-023` / `CMP-028` / `CMP-029` / `CMP-031` once `CMP-021` and prerequisite research rows are ready.
