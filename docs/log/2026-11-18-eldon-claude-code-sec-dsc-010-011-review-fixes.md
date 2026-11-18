# Session log: sec-dsc-010-011-review-fixes

Date: 2026-11-18
Author: eldon
Tool and model: claude-code / sonnet-5.5
Plan IDs: DSC-010,DSC-011,DSC-014

## Summary
Fixed the defects the partner's independent security review found in the connector framework (#88) and the Excel/CSV parser (#97): source.path bypass, stats keys, invisible and control characters, connector-raisable budget, optional audit sink, reply-to check, fullwidth folding; comments, hidden-sheet names and hidden rows, columns and formats no longer reach the model. Subagent (sonnet) fixed; I reran the suite and aligned the intake locator.

## Files touched
- services/discovery/connectors/ (framework, tabular, intake locator) and their tests (339 pass)
- contracts/connector-interface.md: runtime boundary notes
- docs/open-questions.md: Q-136, Q-137

## Decisions
- Review source: partner's comments on PRs 88 and 97 (Opus 5.5, cross-model). The new tests were written after the fixes, not shown failing first. Behaviour change: connector paths must be strict ASCII locators; the odoo and intake connectors already conform (intake metadata locators are now indexed).

## Tokens or cost
Unknown or approximate, if known.

## Next step
Partner re-reviews the fixes; OS-level sandbox row before real uploads.
