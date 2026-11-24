# Session log: bpl-027-follow-up-rows

Date: 2026-11-21
Author: partner
Tool and model: claude-code
Plan IDs: BPL-027,SEC-022,BPL-031,BPL-032

## Summary
Added plan rows SEC-022, BPL-031 and BPL-032 after BPL-030 for the three gaps the BPL-027 expectedFailure tests record, as Eldon's review finding 3 on PR #150 asked (they were only in a log before).

## Files touched
- docs/PLAN.md: three new todo rows, all depending on BPL-027 (SEC-022: adapter role and state collisions with built-ins, test_04b; BPL-031: entity.add on an existing doctype, test_05; BPL-032: role.upsert applies no permissions, test_06).
- docs/log/2026-11-21-partner-claude-code-bpl-027-follow-up-rows.md: this log.

## Decisions
- None. SEC-022 will need an ADR and a security review by a different model when picked up.

## Tokens or cost
Unknown.

## Next step
Eldon re-reviews PR #150; then pick up SEC-022, BPL-031, BPL-032 once BPL-027 is done.
