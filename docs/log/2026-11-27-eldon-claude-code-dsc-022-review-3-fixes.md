# Session log: dsc-022-review-3-fixes

Date: 2026-11-27
Author: eldon
Tool and model: claude-code / opus-5.5
Plan IDs: DSC-022

## Summary
Fixed every finding of the partner's Tier 3 review of PR #394 at b872370e (2 High, 8 Medium, 5 Low), after merging origin/dsc-021-payments-connector at fda83aa3 and keeping both sides (PLAN DSC-021 from #393, DSC-022 `doing`; both question sets; AP-PAY-01 to 05 and AP-MSG-01 to 04).

## Files touched
- contracts/connector-messaging.md, .schema.json: standing contact revoke (H1); `channelAccountRef` required and hashed, conversation binding MSG-015, blocked or STOP refusal (M3); first-record STOP and STOP scope (M4); stale STOP by `providerSentAt` (M5); per-connector timestamp format, retry and age, Messenger numeric timestamp, Instagram blocked (M6, L12); status webhook block and dedup (M7); `inboundMessageId`, one per window, policy threshold (M8); data class, retention, region, production hold (M9); verification method, keyword grants only from signed dated callbacks (M10); retention at least age plus 1 h from first receipt (L11); batch manifest and interim step-up (L13); `tokenRef` and `webhookSecretRef` (L14).
- contracts/examples/ (connector-messaging-*): examples migrated; new valid first-record STOP; 13 new invalid fixtures; `consent-revoked-no-supersedes` removed (a first-record revoke is now valid).
- contracts/tests/test_messaging_contracts.py, test_messaging_rules.py (new): reference checks for each finding.
- contracts/events.md; services/blueprint/events/schemas/types.json, data.message.schema.json (new), data.meter.schema.json; services/blueprint/tests/events/: messaging types registered, `message` and `consent` domains reserved (H2).
- .github/workflows/tests.yml: `&& !cancelled()` on the eight dependency-install steps that lacked it (shared path, H2).
- docs/decisions/ADR-0078 (Proposed), docs/PLAN.md (DSC-022 Tier 3, DSC-024 floor ADR), docs/open-questions.md (Q-695, Q-720, Q-721 notes; new Q-724, Q-725), docs/security/data-classification.md (two rows), docs/security/action-policy-table.md (AP-MSG note).

## Decisions
- No new ADR; ADR-0078 is still Proposed and was amended in place. Founder items: interim R3 step-up rule, STOP scope default (Q-725), Instagram blocked (Q-724), auto-reply needs a floor ADR (Q-720).

## Tokens or cost
Unknown.

## Next step
Partner re-review of #394 (Tier 3). DSC-024 and WEB-035 stay blocked until G2.
