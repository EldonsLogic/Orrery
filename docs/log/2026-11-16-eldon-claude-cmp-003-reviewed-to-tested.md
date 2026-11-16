# Session log: cmp-003-reviewed-to-tested

Date: 2026-11-16
Author: eldon
Tool and model: claude
Plan IDs: CMP-003

## Summary
Final fixes on #43 after Eldon's line-by-line read: manifest level `reviewed` to `tested` (ADR-0034: `reviewed` needs a named reviewer), and the seller VAT format now cites rule BR-KSA-40 with a test that ZATCA's illustrative sample number is refused as a seller number.

Cross-lane: approved by eldon (in chat, 2026-11-16: "can't you fix them"), partner lane paths components/compliance/zatca_sa.

Model and prompt (ADR-0031 condition 4): Claude (Sonnet 5.5) in Claude Code, brief: "fix the two remaining items on #43: manifest level and the VAT regex source". No tax maths changed.

## Files touched
- components/compliance/zatca_sa/manifest.json: level tested
- components/compliance/zatca_sa/phase1.py: comment cites BR-KSA-40 (no logic change)
- components/compliance/zatca_sa/tests/test_phase1.py: sample-number test

## Decisions
- None, or link to ADR / strategy decision.

## Tokens or cost
Unknown or approximate, if known.

## Next step
Merge #43 on green CI. CMP-001 re-reads the BR-KSA-40 wording in the official PDF.
