# Session log: dat-002-synthetic-datasets

Date: 2026-11-17
Author: eldon
Tool and model: claude
Plan IDs: DAT-002

## Summary
DAT-002: a seeded, deterministic generator and committed synthetic trading and distribution datasets for Saudi Arabia, the UAE, Egypt and Qatar (about 215 KB): bilingual Arabic and English parties and items, edge cases (Arabic-Indic digits, bidi controls, long names, apostrophes), a coherent order-to-invoice story with a partial delivery, a credit-limit hold, a credit note and an exact-half-cent rounding probe. 105 tests; `python3 -m services.datasets --check` fails on any drift.

Limits, stated plainly: all identifiers are fake (Saudi VAT `3 99999 NNNN 9999 3`; other markets' formats are invented and UNVERIFIED) and may by chance coincide with real numbers, so they are for dev, demo and eval data only. Tax rates are labelled UNVERIFIED test configuration (SA 15, AE 5, EG 14, QA 0). Expected totals are test expectations using ROUND_HALF_UP per document, not tax-authority output. No evals export: `evals/sets` has no replay format yet. `services/datasets/` is not in `scripts/lanes.json`, so it counts as shared.

Model and prompt: Claude Sonnet subagent from a scoped brief (allowed paths `services/datasets/` only; synthetic and fake identifiers only; no tax logic). Orchestrator re-ran the tests and the check. Not rigid-zone.

## Files touched
- services/datasets/: generator, data (4 markets), manifest, README, tests
- docs/PLAN.md: DAT-002 done

## Decisions
- None.

## Tokens or cost
Unknown or approximate, if known.

## Next step
Dev bench and demos can load the data; QA rows can build eval sets on it. Add an evals replay format if QA needs one.
