# Session log: web-stack-review-fixes

Date: 2026-11-07
Author: eldon
Tool and model: claude-code (cloud session); review by a Sonnet-tier sub-agent, fixes by the orchestrator (Opus)
Plan IDs: WEB-018

## Summary
A cross-model review of ADR-0022 found gaps. Added: app limited to static-export-safe features with a CI build in that mode (in-country hosting marked UNVERIFIED), marketing on Vercel only without personal data collection there, explicit narrowing of ADR-0018 item 2, stronger tokens-only and logical-property lint rules, tenant token loading before first paint, RTL direction provider and bidi isolation for user text, and a human review for major-version bumps of the framework and auth libraries.

## Files touched
- docs/decisions/ADR-0022-web-stack.md (still Proposed).

## Decisions
- None taken; ADR-0022 remains Proposed.

## Tokens or cost
Unknown.

## Next step
Founders: decide ADR-0022 together with ADR-0018.
