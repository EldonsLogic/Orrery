# Session log: cmp-005-hijri-dates-impl

Date: 2026-11-19
Author: partner
Tool and model: codex / gpt-6.1-sol
Plan IDs: CMP-005

## Summary
Completed CMP-005 engine entry, derived companion fields and bilingual invoice dates using the pinned Umm al-Qura tables. Merged main into PR #155 without rewriting history; WEB-017 is done and the founder explicitly resolved print ownership, so removed stale Q-213. Older session logs are unchanged.

## Files touched
- `apps/engine/change_engine/change_engine/i18n/hijri.py`: strict explicit-calendar entry, Arabic-Indic and Eastern Arabic digit normalisation, canonical Gregorian boundary, bilingual isolated month-name formatting and safe i18n error codes. Arabic copy is unreviewed; conversions are marked computed.
- `apps/engine/change_engine/change_engine/calendar_dates.py`: preserve the existing interface through the strict converter; refuse numeric coercion and retain timestamp rejection.
- `apps/engine/change_engine/change_engine/i18n/hijri_fields.py` and `hooks.py`: declarative read-only Data companions for nine trading document types; derive on render or synchronise installed fields during validate, submit and submitted updates. Clear empty sources, calculate all values before mutation, retain policy enforcement first. No DDL, database writes, permissions override or automatic field installation.
- `apps/engine/change_engine/change_engine/print_formats/bilingual_tax_invoice.py`: derive from canonical issue/posting date on every HTML/PDF render, ignore cached Hijri input, respect resolved locale and compliance settings, preserve mandatory Gregorian date, totals, QR and layout. Saudi print mode supplies the default when no display choice is resolved; an enabled compliance profile wins over a disabled secondary display.
- `apps/engine/change_engine/change_engine/tests/test_cmp_005_hijri_dates.py`: full-table round-trips, fixed boundary examples, strict entry and range failures, missing dependency, localised formatting, companion sync, lifecycle registration, print configuration and engine invisibility.
- `.github/workflows/tests.yml`: run both CMP-005 suites; the dependency installation already includes the exact 2.6.0 pin from discovery requirements, also pinned in the engine project.
- `docs/PLAN.md`, `docs/open-questions.md`, this log: CMP-005 done; stale ownership doubt removed as instructed.

## Verification
- Python 3.12.3, isolated environment, hijridate 2.6.0. Initial test collection failed because the new calendar API did not exist; the completed implementation passes.
- `PYTHONPATH=apps/engine/change_engine:. python -m unittest change_engine.tests.test_cmp_005_calendar change_engine.tests.test_cmp_005_hijri_dates change_engine.tests.test_erp_007_bilingual_tax_invoice -q`: 32 tests passed, including actual PDF generation with WeasyPrint installed. One upstream HarfBuzz deprecation warning; no skipped PDF test in that run.
- Every supported Gregorian day (1924-08-01 through 2077-11-16) round-tripped through Umm al-Qura; literal fixtures include 1343-01-01, 1446-03-15 and 1500-12-30 AH.
- `PYTHONPATH=apps/engine/change_engine:. python -m pytest apps/engine/change_engine/change_engine/tests --ignore=apps/engine/change_engine/change_engine/tests/test_live_mariadb_suite_b.py -q`: 198 passed, 82 subtests passed.
- Full engine collection including `test_live_mariadb_suite_b.py`: 197 passed; five live database setup errors because no MariaDB service listens on localhost. No live database verification is claimed. The live suite initially required installing PyMySQL into the isolated test environment.

- Initial whole-repository `pytest -q`: 2651 passed, four skipped, 27 expected failures, one failure (`services/blueprint/tests/tokens/test_tkn_brand_tools.py::test_no_bytecode_written_next_to_docs`), five MariaDB setup errors. The runner created brand-tool bytecode during collection; the isolated brand-tools test passes after removing generated caches and running Python with `-B`. No brand source was changed. Pytest also cached synthetic secret-test identifiers; removed that generated cache and moved subsequent pytest caches outside the repo.

- Final whole-repository offline run: `PYTHONPATH=apps/engine/change_engine:. python -B -m pytest -q --ignore=apps/engine/change_engine/change_engine/tests/test_live_mariadb_suite_b.py -o cache_dir=<external-cache-directory>`: **2653 passed, four skipped, 27 expected failures, 96 subtests passed**. The sole excluded file requires the unavailable live MariaDB service; the bytecode assertion passes.
- Required repo gates passed: `check_docs.py` (zero errors/warnings), `check_repo_hygiene.py`, `check_lanes.py --base origin/main --head HEAD --actor sayegh9`, `scan_secrets.py` (zero hits), `check_plan_independence.py` and `git diff --check`. Final committed lane/task-trail checks and push verification run through `finish_session.py`.

## Viewing and integration
- Run the unittest command above to exercise synthetic bilingual invoice HTML and PDF. `render_tax_invoice_html`, `render_tax_invoice_pdf` and `render_frappe_sales_invoice_html` accept `locale={"calendar": {"secondaryDisplay": "hijri_umm_al_qura"}, "numberSystem": "eastern_arabic"}` and/or `compliance_profile={"hijriDisplay": {"enabled": True}}`. Omit the number setting for Western digits.
- `companion_fields("Sales Invoice", language="ar")` returns configuration-apply definitions; install only through the existing configuration/DDL approval path. `derive_companions(doc)` supports display without installing columns. Stored sources stay Gregorian; generated companions are disposable display caches. Persistent locale resolution remains CMP-023, and broader document/template integration remains ERP-019.

## Decisions
- Implements accepted ADR-0015 and ADR-0016, the CMP-022 library choice and ADR-0033 Arabic review status. No new accounting, tax, legal-layout or permission policy.
- Official-table accuracy remains UNVERIFIED as recorded in the licence register; no approximate conversion or moon-sighting inference is used. Native Arabic invoice review and independent compliance/security review remain release controls; no phase or gate exit is claimed.

## Tokens or cost
Unknown.

## Next step
Eldon reviews PR #155 with a different model, including compliance/security and shared workflow changes. Do not merge in this implementation session. CI is not polled after push.
