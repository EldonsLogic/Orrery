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
- `docs/PLAN.md`: CMP-034 row. `docs/open-questions.md`: Q-560.

## Decisions
- Production statuses are `certified` and `regulated`: the schema enum puts `regulated` above `certified`, and ADR-0034 makes exactly those two production eligible for components.
- `secondary` evidence passes production; only `unverified` is refused (per the brief). Raised in Q-560.
- Sandbox and test accept `draft` (per the brief), unlike ADR-0034's component rule; raised in Q-560.
- An unpinned production load does not skip a newer draft to reach an older certified pack; it refuses. Production resolve requires a pinned version anyway.

## Tokens or cost
Unknown.

## Next step
- After merge, open pack PRs #255 (Qatar), #256 (Egypt) and #257 (KSA/UAE) need `environment="test"` in their tests.
- Q-560: founders decide who certifies a pack and on what evidence.
- Any production consumer of `compliance.countryPack` (BPL-027, ERP-012) must call the loader with the default `environment="production"`.

## Review fix round
Eldon's cross-model review of PR #259 (Fable 5.2) and the Gemini review agreed on four fixes and one question. Merged origin/main first (no-ff, no rebase).
- Medium, `testOnly` in production: `_check_go_live` now refuses a `testOnly: true` pack in production whatever `allow_test_packs` says, pinned or unpinned. The old test that asserted the opposite is flipped and split into pinned, unpinned and message tests.
- Medium, `secondary` evidence: production evidence is an allowlist, `PRODUCTION_EVIDENCE = {verified_official}`. `secondary` is refused because country-matrix.md treats SECONDARY as UNVERIFIED, until Q-560 is answered. Sandbox and test still accept it. Framework section 6 updated.
- Low, `apply_company_overrides`: made private (`_apply_company_overrides`) and dropped from the package exports; `resolve_country_pack` is the only production entry, documented in its docstring and section 6. Chosen over adding an `environment` gate because it is the smaller change and leaves one gated path. The CMP-021 tests import the private name from `loader` directly. No caller outside the package exists on main; open PRs that import it need the same change.
- Low, environment type: `_check_environment` uses `type(environment) is str`. New test with a `str` subclass whose `__eq__` returns True (it inherits `str.__ne__`, so before the fix `"staging"` passed the membership test and skipped the gate). A first draft of this test also overrode `__ne__` and passed before the fix; corrected so it fails without the fix.
- Q-560: added Eldon's point that pack `status` is self-declared, so must it match the manifest `certification.level` and a named reviewer.
- Tests: before 17 of 17 passing; with the new tests and no fix, 12 failures and an import error; after the fix 23 of 23 pass.
