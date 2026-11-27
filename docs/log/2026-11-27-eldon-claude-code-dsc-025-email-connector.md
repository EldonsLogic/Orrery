# Session log: dsc-025-email-connector

Date: 2026-11-27
Author: eldon
Tool and model: claude-code / opus-5.5 (worker subagent, delegated by the session orchestrator; branch `dsc-025-email-connector` stacked on `gov-078-module-scope`, PR #392)
Plan IDs: DSC-025

## Summary
Email sending connector contract 0.1.0 (six objects, schema, 18 valid and 41 negative examples, contract tests) and ADR-0081 (Proposed), with the `email.*` event types registered and the `email` domain reserved.

## Files touched
- contracts/connector-email.md, contracts/connector-email.schema.json: the contract (bring your own provider, staged secrets, sender domains, webhooks per provider, DSC-022 consent reuse, suppression, RFC 8058 headers, tracking off by default, rate limits and warm-up, error codes EML-001 to EML-016, tenancy, data class, audit, sandbox).
- contracts/examples/connector-email-*.json, contracts/examples/invalid/connector-email-*.json, contracts/tests/test_email_contracts.py: examples; each invalid file asserts its keyword and property.
- contracts/events.md, contracts/README.md, scripts/check_contracts.py: email events table, contract row, example pairs.
- services/blueprint/events/schemas/types.json, data.email.schema.json, services/blueprint/tests/events/ev_helpers.py, test_ev_schemas.py: ten `email.*` types with closed data schemas (bare hex hashes, no address, body or URL).
- docs/decisions/ADR-0081-email-sending-connector.md, docs/decisions/INDEX.md, docs/PLAN.md (DSC-025 doing), docs/open-questions.md (Q-726 to Q-729).

## Decisions
- [ADR-0081](../decisions/ADR-0081-email-sending-connector.md) (Proposed, partner pending).
- External facts read 2026-11-27 with URLs in the ADR: RFC 8058, Gmail and Yahoo sender rules, SES/SNS, Postmark, SendGrid and Mailgun webhook docs. ZeptoMail signing not found: UNVERIFIED, ZeptoMail refused in 0.1.0 (Q-727).

## Tokens or cost
Unknown.

## Next step
- Partner review of the PR (Tier 3: credentials, untrusted inbound webhooks); security review by a different model.
- Q-728: add channel `email` to the DSC-022 consent enum when the second of #394 and this PR merges. Merge conflicts expected with #393 and #394 in events.md, types.json, ev_helpers.py, check_contracts.py and README (additive, keep both); the events.md version bump is left to merge order.
- DSC-026 (G2) builds the adapters; Q-726 (SEC rows), Q-729 (placeholders), LEG-012 (tracking consent).
