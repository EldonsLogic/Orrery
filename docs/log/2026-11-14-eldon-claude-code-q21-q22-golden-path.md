# Session log: q21-q22-golden-path

Date: 2026-11-14
Author: eldon
Tool and model: claude-code / sonnet-5-5
Plan IDs: BPL-028,BPL-029

## Summary
Applied the founder's answers to Q-21 (Moving Average, set explicitly) and Q-22 (commercial rounding, half away from zero, negative amounts by magnitude) to the golden path and the mapping fixture.

## Files touched
- `docs/specs/golden-path-trading-sale.md`: valuation and rounding rows, bench questions updated.
- `contracts/engine-mapping.schema.json`: new rounding mode `half_away_from_zero`.
- `contracts/examples/engine-mapping-golden-path.json`: rounding mode changed from `half_up` to `half_away_from_zero`.

## Decisions
- Answers were posted on PR 48 and still need recording in `docs/open-questions.md` by the partner. Both stay UNVERIFIED until run on the bench. Mapping tests: 14 passed.

## Tokens or cost
Unknown.

## Next step
BPL-028: the other founder checks the golden path independently. The partner confirms the two engine settings on the bench (ERP-022).
