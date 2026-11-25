# Session log: cmp-040-calendar-review-tests

Date: 2026-11-25
Author: partner
Tool and model: claude-code (Claude Sonnet 5.5 child wrote the tests; Claude Opus 5.5 coordinator reviewed, applied and ran them)
Plan IDs: CMP-040

## Summary
Closes Eldon's three optional follow-ups from the #283 and #303 reviews of `company_calendar`, tests only: the `hijridate` pin check now also covers the pins in `.github/workflows/tests.yml` and `services/discovery/requirements.txt` (read only; that file is in Eldon's lane and is not edited); a label-sort test (N1) with `en`, `ar` input order; and one module-level `disallowed_numbers` helper shared by the real source check and the planted-constant test (N2), so the planted test exercises the real check.

## Files touched
- `components/compliance/company_calendar/tests/test_company_calendar.py`: +40, -9.
- `docs/PLAN.md`: CMP-040 `done`.

## Tests
- `company_calendar`: 47 tests OK (was 45). `country_pack`: 129 OK.
- Seen failing: a copy of the inputs with a changed or missing pin in either file fails the new pin test; dropping the sort at `settings.py:97` in memory fails N1. No repo file was changed for the probes.

## Decisions
- None.

## Tokens or cost
Unknown.

## Next step
None for CMP-040. CMP-023 stays `doing` for its remaining scope.

## Review round 1 (gpt-6.1-sol at `31302b9`: APPROVE, two Lows, fixed by the coordinator)
- R1 Low: removing only the engine-install pin survived, because another pin in the same file stayed. New `test_engine_install_step_pins_hijridate` requires the pin inside the `Install dependencies (apps/engine)` step; dropping it fails the test (seen on a temporary edit, restored).
- R2 Low: bypassing the helper in the real check survived. The real check is now one method, `assert_no_disallowed_numbers`, which the planted test calls with `48` and `29.53` (both must raise) and with allowed values (must pass); a bypass in that method fails the planted test (seen, restored).
- `company_calendar`: 48 tests OK; `country_pack`: 129 OK.
