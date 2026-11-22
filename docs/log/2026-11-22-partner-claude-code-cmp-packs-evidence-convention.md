# Session log: cmp-packs-evidence-convention

Date: 2026-11-22
Author: partner
Tool and model: claude-code (Claude Opus 5.5), implementation sub-agent
Plan IDs: CMP-028,CMP-029,CMP-031

## Summary
The four country packs now use one source convention: per-fact sources live in `evidence.json` in the UAE and KSA format, which the partner founder decided. One shared test checks every pack, and the review Lows from #255, #256 and #257 are fixed. This is Tier 3 rigid-zone data. No statutory value, rate, date, status or evidence label changed. Facts that look wrong are listed below and left unchanged.

## Files touched
- `components/compliance/country_pack/packs/qa/0.1.0/evidence.json` (new): every row of the former `SOURCES.md` became a fact. The claim keeps the value and evidence text, and every URL keeps its access date. KPMG and vatupdate were search excerpts, so they have a note and no `accessed`. The schema-gap facts moved to `factsOutsideSchema`, and the Arabic review section moved to `arabicLabels`. `SOURCES.md` was removed.
- `packs/eg/0.1.0/evidence.json` (new): every row of the README source table became a fact, with `recordedStatus` keeping the README status text verbatim. The data-protection note moved to `factsOutsideSchema`, and the Arabic list (including `strings.json`) moved to `arabicLabels`. `README.md` was removed because nothing else remained; `strings.json` was kept.
- `packs/qa/0.1.0/pack.json`, `manifest.json`: the names are neutral ("Qatar Country Pack", "حزمة دولة قطر"; the Arabic stays `unreviewed` in `evidence.json`), and notes and description point at `evidence.json`. `provides` follows the shared convention, and `requires` adds `qa.holidays` (`>=0.1.0 <0.2.0`), which the pack already references.
- `packs/eg/0.1.0/pack.json`, `manifest.json`: notes point at `evidence.json` and drop the inline `14%/5%` and `5yr`. Those figures are still in the `evidence.json` claims and in the pack value. `provides` follows the shared convention, and `requires` adds `eg.holidays` (`>=0.1.0 <0.2.0`).
- `packs/ae/0.1.0/evidence.json`: swapped two refs, checked against `docs/compliance/uae-einvoicing-provider-selection.md` section 1. Mode now cites items 1 and 9: DCTCE, and the PINT AE spec. Authority now cites items 1 and 3: the MoF page, and the inference that the FTA is Corner 5.
- `packs/README.md`, `docs/compliance/country-pack-framework.md`: document the `evidence.json` format in the layout section, and say there is no `SOURCES.md` or README source table.
- `tests/pack_checks.py` (new, not a test module): shared helpers moved out of `test_pack_sa_ae.py`. The digit check now also covers the top-level `notes` and `name`, which may hold digits only in record ids, ISO dates, semver, `v1` and `Phase N`.
- `tests/test_country_packs.py` (new): shared checks that run over every pack under `packs/`:
  - folder layout;
  - every leaf has evidence;
  - labels follow the rules, and unread sources have no access date;
  - pending refs;
  - referenced components equal `requires`;
  - status equals level;
  - `evidenceStatus` is `unverified` while refs are pending;
  - one `provides` convention;
  - no rate-like digits, with mutations;
  - Arabic review state.
- `tests/test_pack_sa_ae.py`: generic tests moved to the shared module, and SA/AE-specific tests kept. Added a test for the UAE ref swap.
- `tests/test_pack_qa.py`: the `SOURCES.md` tests became `evidence.json` tests (the excerpt sources have no access date) plus a neutral-name test. The per-field coverage test moved to the shared module.
- `tests/test_pack_eg.py`: the override sets `secondaryDisplay: hijri_umm_al_qura` instead of a redundant `gregorian`.

## Decisions
- **`provides` convention:** every pack provides one capability, `country.<cc>.pack_metadata`, whose single artifact is `{type: function, ref: components.compliance.country_pack.loader.resolve_country_pack}`. This was already the UAE and KSA form. I did not choose `entity`, because in the manifest contract an entity ref is an engine entity id and feeds ADR-0037 risk classing; a `pack.json` path is not an entity. Qatar and Egypt capability ids changed (`compliance.country_pack.qa/eg` became `country.qa/eg.pack_metadata`). Nothing in the repo referenced the old ids.
- **Status mapping:** Egypt "Internal decision" became `PLATFORM-DEFAULT`, "VERIFIED (SDK API docs)" became `VERIFIED-OFFICIAL`, and every other status became `UNVERIFIED`. The verbatim text is kept in `recordedStatus`. Qatar statuses map to `UNVERIFIED`, except the rounding rule, which is `PLATFORM-DEFAULT` as `SOURCES.md` said.

## Suspect facts (listed, not changed)
1. **UAE `eInvoicing.authority`** still lists the PINT AE URL (`docs.peppol.eu`) as a source. Provider-selection item 3 cites only the MoF page, so this source backs neither item 1 nor item 3.
2. **Egypt access dates:** the old README showed these sources as accessed on 2026-11-18, but `egypt-research.md` marks them as snippets or PRIMARY-SNIPPET (not read):
   - ETA home page and guides page (1.5);
   - ETA VAT PDF (2.5);
   - Andersen and lookuptax (2.4);
   - the two SDK receipt pages (1.6);
   - vatit (1.7) and storecove (1.10).

   Following the rule that unread sources carry no access date, they now have a note keeping the 2026-11-18 search date and no `accessed`. The Andersen URL is marked a snippet in 2.4 but not in 2.6, so the research conflicts with itself.
3. **Egypt rounding** is labelled UNVERIFIED (as in the README). The other three packs label the same ADR-0033 rule PLATFORM-DEFAULT.
4. **Egypt gaps:** the README had no row for the date formats, `printFormats.templates` or `legalLayoutPrecedence`. These now have UNVERIFIED entries with no source; no value changed.
5. **The Egypt manifest description** still states "standard 14% VAT / 5% machinery". The digit check covers pack values only, not manifest text.
6. **Qatar's Ramadan label** still reads "(unverified)" / "(غير مراجعة)" in a user-facing label. Only the names were in scope.

## Checks
- Unit tests: `uv run --no-project --with "jsonschema==4.26.0" python3 -m unittest discover -s components/compliance/country_pack/tests -t . -v` gives 91 tests, OK.
- Mutations, each caught by the shared test:
  - drop a Qatar fact;
  - give the unread KPMG source an access date;
  - drop `eg.holidays` from `requires`;
  - add a second Egypt `provides` artifact;
  - add `VAT 14%` to the Egypt notes;
  - make a VERIFIED-OFFICIAL source unread;
  - leave a `strings.json` label out of `arabicLabels`;
  - put `SOURCES.md` back.
- Repo checks: `check_docs`, `check_repo_hygiene`, `scan_secrets`, `check_plan_independence` and `check_lanes` (results in the PR).

## Tokens or cost
Unknown.

## Next step
Eldon's line-by-line read (ADR-0031) and a cross-model review of this PR. Sources for the Qatar and Egypt UNVERIFIED facts are still needed before any pack leaves `tested` (CMP-028, CMP-029, CMP-031).
