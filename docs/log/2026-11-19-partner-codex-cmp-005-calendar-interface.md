# Session log: cmp-005-calendar-interface

Date: 2026-11-19
Author: partner
Tool and model: codex
Plan IDs: CMP-005

## Summary
Added an engine-side date conversion interface using the same pinned Umm al-Qura library as document intake, without changing intake or invoice output.

## Files touched
- `apps/engine/change_engine/change_engine/calendar_dates.py`: Gregorian and Hijri conversion boundary, rejecting timestamps and unsupported dates.
- `apps/engine/change_engine/pyproject.toml`: pin the existing licensed conversion library for the engine.
- `apps/engine/change_engine/change_engine/tests/test_cmp_005_calendar.py`: common intake example, invalid dates, and timestamp rejection.

## Decisions
- ADR-0015: Gregorian dates remain canonical; the Hijri string is a display value, not a stored Gregorian date. The founder confirmed CMP-005 ownership and that WEB-017 owns print UI.

## Tokens or cost
Unknown or approximate, if known.

## Next step
CMP-005 remains doing: wire this interface into field, display and print consumers with company calendar settings; verify Arabic formatting and range boundaries; arrange compliance security and cross-model review. With the pinned dependency installed, `PYTHONPATH=apps/engine/change_engine python -m unittest change_engine.tests.test_cmp_005_calendar -v` passed (3 tests). CI wiring remains outstanding; INF-003 owns the concurrent workflow changes. Table accuracy against the official calendar remains UNVERIFIED as recorded in the licence register.
