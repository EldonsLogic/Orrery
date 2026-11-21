# Session log: cmp-034-country-pack-go-live-gate

Date: 2026-11-21
Author: partner
Tool and model: claude-code (Claude Opus 5.5)
Plan IDs: CMP-034

## Summary
Closed the High finding in Eldon's review of PR #255 (item 1): the country pack loader now fails closed in production for a pack below `certified` or with `evidenceStatus: unverified`, through a keyword `environment` (`sandbox`, `test`, `production`, default `production`) on `load_country_pack` and `resolve_country_pack`.

## Files touched
- `components/compliance/country_pack/loader.py`: `ENVIRONMENTS`, `PRODUCTION_STATUSES = {certified, regulated}`, `_check_environment`, `_check_go_live`; the `environment` keyword on both entry points. `allow_test_packs` unchanged and orthogonal.
- `components/compliance/country_pack/tests/test_country_pack_go_live_gate.py`: new, 8 tests (production refuses draft, tested, reviewed and unverified; accepts certified and regulated with verified or secondary evidence; sandbox and test accept draft; unknown environments refused; `allow_test_packs` orthogonal; no unpinned fallback past a draft). Tests written first: 8 failing, 9 existing passing; after the change 17 of 17 pass. Mutations (no gate, no evidence check, no environment check) each fail tests.
- `components/compliance/country_pack/tests/test_country_pack.py`: existing calls that load the draft sample pack pass `environment="test"`.
- `docs/compliance/country-pack-framework.md`: section 6, the gate.
- `docs/PLAN.md`: CMP-034 row. `docs/open-questions.md`: Q-558.

## Decisions
- Production statuses are `certified` and `regulated`: the schema enum puts `regulated` above `certified`, and ADR-0034 makes exactly those two production eligible for components.
- `secondary` evidence passes production; only `unverified` is refused (per the brief). Raised in Q-558.
- Sandbox and test accept `draft` (per the brief), unlike ADR-0034's component rule; raised in Q-558.
- An unpinned production load does not skip a newer draft to reach an older certified pack; it refuses. Production resolve requires a pinned version anyway.

## Tokens or cost
Unknown.

## Next step
- After merge, open pack PRs #255 (Qatar), #256 (Egypt) and #257 (KSA/UAE) need `environment="test"` in their tests.
- Q-558: founders decide who certifies a pack and on what evidence.
- Any production consumer of `compliance.countryPack` (BPL-027, ERP-012) must call the loader with the default `environment="production"`.
