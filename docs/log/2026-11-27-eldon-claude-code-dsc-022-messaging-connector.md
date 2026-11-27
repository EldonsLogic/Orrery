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

## Update: Tier 3 security review fixes (PR #394, verdict CHANGES: 2 High, 6 Medium, 4 Low)
- Delegated by Eldon's orchestrating session to an implementation worker (opus-5.5); test first: 19 new invalid examples and the stricter tests failed before the schema change.
- H1 marketing `approvalId` a required ref; H2 auto-reply has no `text`, needs `autoReplyPolicyRef`, `approvedTextId`, `classifiedIntent`, `confidence`, `confidenceThreshold` (floor 0.8), Meta channels only.
- M1 `sentBy`, `draftedBy`, `confirmationId`, `payloadHash` (canonical sha256, checked by a test) and the section 10 audit field map; M2 every send proposed R3 (R1 has no external effect), session replies `tainted: true`, Q-720; M3 send `country`, append-only consent with `supersedes` and `afterRevocation`, a contact's STOP lifted only by the contact; M4 dedup by `providerEventId`, retention at least 72 hours, no age window for Meta, unknown `eventType` fails closed (MSG-013), Q-721; M5 `siteClass`, `testAllowlistRef`; M6 SMS sends are templates, a null window refuses a session reply.
- Lows: credentialRef tenant rule and cross-tenant refs (MSG-014); real, unshared example hashes; inbound `flags` required and `retentionClass`; per-file expected keyword test; error codes over invalid examples; events test reads table rows.
- Files: contracts/connector-messaging.md, .schema.json, examples, tests/test_messaging_contracts.py, contracts/events.md (messaging rows), ADR-0078 (Proposed, decisions 3 to 8), docs/open-questions.md (Q-720, Q-721).

## Update: narrow re-review fixes (PR #394 at d66fa037, verdict CHANGES: M3 partly fixed, M7 new, risk class, 3 Low)
- Delegated by Eldon's orchestrating session to an implementation worker (opus-5.5); test first: 8 new invalid examples and 14 new tests failed before the schema change.
- M3 consent chain: platform-set `recordedAt` (required) is the only ordering key, never `capturedAt`; validator rules "supersedes names the latest record" (null only for a key's first record) and afterRevocation copied from a superseded revoke; reference checker and fixtures in the tests, including a tenant-user grant with `supersedes: null` after a STOP (refused).
- M7 replay: inbound `providerSentAt` from the signed body (required on Meta channels); `windowOpenUntil` from it, never from receive time; capability `payloadTimestamp`, `maxEventAgeHours` (37 to 72, inside dedup retention), `dedupStore: durable`; Meta payload timestamp UNVERIFIED, added to Q-721.
- Risk class: auto-reply `riskClass: null` (no class until the SEC row, refused); R3 interim for human and agent-draft sends; migration to an AP-MSG row reference is a 0.2.0 bump later, none now. AP-MSG-01 to AP-MSG-04 proposed in docs/security/action-policy-table.md; Q-720 updated.
- Lows: `tainted` set by platform code, schema-forced when `conversationId` is present; `payloadHash` excludes `sentBy` (example hashes recomputed); `sentBy` `usr_` against `draftedBy` `agt_` makes them disjoint in the schema, plus a validator rule.
- Files: contracts/connector-messaging.md, .schema.json, examples, tests/test_messaging_contracts.py, docs/security/action-policy-table.md, docs/open-questions.md (Q-720, Q-721).
