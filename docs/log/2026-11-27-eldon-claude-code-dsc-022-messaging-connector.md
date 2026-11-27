# Session log: dsc-022-messaging-connector

Date: 2026-11-27
Author: eldon
Tool and model: claude-code / opus-5.5 (implementation worker subagent, briefed by Eldon's orchestrating session)
Plan IDs: DSC-022

## Summary
Messaging and SMS connector contract 0.1.0 with schema, examples and contract tests, events 0.2.0 additions, and ADR-0078 (Proposed). Stacked on gov-078-module-scope (PR #392, ADR-0076). ADR-0078 checked unused on main and every open PR branch; ADR-0077 left for the payments PR.
- Coordination: branch merged origin/dsc-021-payments-connector (#393) so events 0.3.0 sits on its 0.2.0; PR #394 retargeted to that branch. Open questions Q-695 to Q-698 added (Q-692 to Q-694 are #393's).

## Files touched
- contracts/connector-messaging.md, contracts/connector-messaging.schema.json: new contract
- contracts/examples/connector-messaging-*.json (7 valid), contracts/examples/invalid/connector-messaging-*.json (10 invalid)
- contracts/tests/test_messaging_contracts.py: schema, examples, version, error-code and event-registry tests
- contracts/events.md (0.3.0, additive messaging events after #393's 0.2.0 payment types), contracts/README.md, scripts/check_contracts.py (example pairs)
- docs/open-questions.md: Q-695 to Q-698
- docs/decisions/ADR-0078-messaging-and-sms-connector.md, docs/decisions/INDEX.md, docs/PLAN.md (DSC-022 doing)

## Decisions
- [ADR-0078](../decisions/ADR-0078-messaging-and-sms-connector.md) Proposed. Auto-reply stays off until a SEC-owned action-policy row allows it (today's table is draft-only for agents).

## Tokens or cost
Unknown.

## Next step
Partner review of ADR-0078 and a security review by a different model; SEC action-policy row for `message.*`; DSC-024 build after acceptance; open points listed in the ADR Consequences.
