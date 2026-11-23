# Session log: cmp-038-pack-publishing-rows

Date: 2026-11-23
Author: eldon
Tool and model: claude-code (Claude Opus 5.5)
Plan IDs: CMP-038, CMP-039

## Summary
Added two G3 plan rows so country pack changes can be published without a code change, with two-person sign-off and an urgent-change path.

## Files touched
- `docs/PLAN.md`: new rows CMP-038 (eldon: staff publishing workflow and screen) and CMP-039 (partner: loader reads signed, published versions).

## Decisions
- **Locked values stay central.** Locked legal values (tax, e-invoicing, payroll, formats, legal print layout) are never edited per tenant. A change is a new pack version, signed off by a named accountant and a founder, then rolled out to pinned tenants.
- **Urgent changes keep two people.** The urgent-change path still needs both sign-offs, and adds a mandatory follow-up review.
- **The rows can run in parallel.** Neither row depends on the other (ADR-0025). The interface between them is agreed by contract or ADR before either is built.

## Tokens or cost
Unknown.

## Next step
- Pick up CMP-038 and CMP-039 after CMP-036 and the CMP-037 research.
- Write a contract or ADR for the pack store interface first.
