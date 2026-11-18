# Session log: forwarding-intake

Date: 2026-11-18
Author: eldon
Tool and model: claude-code / sonnet-5.5
Plan IDs: DSC-015

## Summary
Email and WhatsApp forwarding connectors (file/string parsing only) behind the sanitiser and runner, with attachment blocking and dedup.

## Files touched
- services/discovery/connectors/forwarding/: parsers, attachments, README
- services/discovery/tests/connectors/forwarding/: 21 tests
- docs/open-questions.md: Q-178

## Decisions
- None.

## Tokens or cost
Sonnet subagent, about 125k tokens.

## Next step
Real inbox receiver (SPF/DKIM) later; Q-178.
