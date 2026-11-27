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
