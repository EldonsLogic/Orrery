# Session log: cmp-036-pack-loader-followup

Date: 2026-11-23
Author: eldon
Tool and model: claude-code (Claude Opus 5.5)
Plan IDs: CMP-036

## Summary
This session added plan row CMP-036, so that #282 (CMP-035) can merge now. The production loader rules Eldon chose follow in that row.

## Files touched
- `docs/PLAN.md`: new row CMP-036 (partner, G2, depends on CMP-035). It must be done before any pack is certified for a customer.
- `docs/open-questions.md`: new Q-601, asking whether ZATCA mandates invoice rounding (for the accountant, UNVERIFIED).

## Decisions
Eldon decided these on 2026-11-23, for both founders. The partner proposed the same options over chat.
- **Platform defaults:** a PLATFORM-DEFAULT fact may back a locked path only when the path is on a named per-market list of product-choice paths, and never through an ancestor path.
- **Blocking production:** any open `goLiveBlockers` or `pendingRefs` entry, or an UNVERIFIED `factsOutsideSchema` entry on a locked path, blocks production.
- **Timing:** merge #282 as it is now, and build both rules in CMP-036 before any certification. All four shipped packs are refused in production today, so nothing unsafe can load in the meantime.

## Tokens or cost
Unknown.

## Next step
- **Partner:** pick up CMP-036 after #282 merges.
- **Accountant:** answer Q-601 before the Saudi product-choice list is final.
