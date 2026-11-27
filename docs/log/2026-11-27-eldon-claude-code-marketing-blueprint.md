# Session log: marketing-blueprint

Date: 2026-11-27
Author: eldon
Tool and model: claude-code / opus-5.5
Plan IDs: BPL-055

## Summary
Blueprint 0.8.0 adds `modules.marketing` under ADR-0079 (Proposed): campaign (shared with CRM), email campaign and messaging campaign concepts; guard-based segments over CRM audiences; mandatory consent (opt-in and an unsubscribe route always true); email and messaging channels, where messaging names an integration on the DSC-022 messaging connector, referenced loosely by row id. Last of four stacked PRs.

## Files touched
- contracts/blueprint.schema.json: 0.8.0; `marketingModule`; one x-validator-rule.
- contracts/blueprint-modules.md: marketing section, metrics, changelog; contracts/README.md: version.
- contracts/examples/blueprint-modules-minimal.json: two campaign entities, a messaging integration, a dashboard, `modules.marketing`.
- contracts/examples/invalid/blueprint-modules-marketing-cases.json: 13 negative cases (consent off, free-text messages, SQL segment refused).
- services/blueprint/diff/bpdiff/model.py: key-table rows for segments and segment filters.
- docs/open-questions.md (Q-703), docs/PLAN.md (BPL-055 doing), docs/CHANGELOG.md.

## Checks
- Campaign, Email Campaign (recipients Lead, Contact or Email Group) and Campaign Email Schedule read from the pinned ERPNext v15.124.5 source; UNVERIFIED until a bench run.
- DSC-022 is still todo; BPL-055 depends on it. The contract fixes no connector id (Q-703).

## Decisions
- None new; follows ADR-0079.

## Tokens or cost
Unknown.

## Next step
Partner reviews ADR-0079 and #395 to the BPL-055 PR in stack order; when DSC-022 lands, a patch names its connector ids (Q-703).

## Review fixes (#398 RULES 42 review at 74c2e1bd)
- Merged bpl-054-manufacturing-blueprint (the #395 to #397 fixes) first; conflicts in the changelog, x-validator-rules and Q-700 to Q-703 rows resolved by keeping both sides.
- M1: consent covers contact, channel, country and purpose `marketing` (DSC-022 section 6, MSG-005); a utility consent never covers a campaign (schema text, blueprint-modules.md, x-validator-rule); contract test `test_marketing_consent_text_matches_dsc022`.
- M2: marketing sends and campaigns are R3, `origin: human`, `approvalId` required, never agent-creatable (DSC-022 section 3, AP-MSG-03 proposed); no assistant may list them (tools at most R2).
- M3: lead or customer members without a `contactRef` are skipped; imports and segments never create consent.
- L4: example uses `msg.meta_whatsapp`; schema root `x-messaging-connectors` lists the four DSC-022 ids; validator `BP-MOD-005` checks the messaging integration's connector.
- L5: at least one channel enabled (schema `anyOf`; cases `mkt-all-channels-disabled`, `mkt-only-channel-disabled`, exact path); empty `visibleToRoles` means nobody.
- L6: merge order (#394 before #398) stated in Q-703. L7: bpdiff classes `modules/marketing/consent` and `channels` `compliance` (tests); role lists `access` from #395.
- Q-703 rewritten in place on this branch (row added by this PR, unmerged).
