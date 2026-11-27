# Session log: email-marketing-blueprint

Date: 2026-11-27
Author: eldon
Tool and model: claude-code / opus-5.5
Plan IDs: BPL-066

## Summary
Blueprint 0.9.0 (additive) puts email back into `modules.marketing` on the DSC-025 email sending connector: `channels.email`, the `email_campaign` concept, a brand-token template library with saved blocks, A/B tests with a deterministic winner rule, tracking off by default and fixed send windows per country. Contract, schema, examples, validator rules and contract tests only; no editor code (WEB-037). Stacked on `bpl-055-marketing-blueprint` (#398) with `dsc-025-email-connector` (#409) merged in; the INDEX and open-questions conflicts kept both sides.

## Files touched
- contracts/blueprint.schema.json: 0.9.0; `x-email-connectors`; `channels.email`, `emailBlocks`, `emailTemplates`, `abTests`; `$defs` `emailTone`, `emailTextStyle`, `httpsLink`, `emailBlock`, `emailFixedBlock`, `emailTemplateVariant`, `emailTemplate`, `emailAbTest`; one x-validator-rule.
- contracts/blueprint-modules.md: email section, metrics, changelog; contracts/README.md: version; contracts/engine-rigid-fields.json: `marketing.email_campaign` (no engine record).
- contracts/examples/blueprint-modules-minimal.json: email campaign entity, Postmark integration, email channel, one saved block, one template (ar and en), one subject A/B test.
- contracts/examples/invalid/blueprint-modules-email-cases.json: 39 negative cases; marketing cases: the two "email not in 0.8.0" cases removed, one case adjusted.
- contracts/tests/test_blueprint_modules.py: email tests (DSC-025 ids, brand tokens only, block types, tracking off by default) replace the "email waits" test.
- services/blueprint/validator/rules_modules.py: `BP-MOD-006` to `BP-MOD-009`; services/blueprint/tests/test_modules.py: tests written first.
- services/blueprint/diff/bpdiff/model.py and classify.py: key rows for the new arrays, order-significant blocks and A/B variants, compliance for the template unsubscribe and footer blocks and the winner release; tests in tests/diff/test_bpdiff_classify.py; READMEs.
- docs/decisions/ADR-0079 (Proposed): BPL-066 note; docs/open-questions.md Q-730 to Q-733; docs/PLAN.md BPL-066 doing; docs/CHANGELOG.md.

## Checks
- contracts/tests 297 passed; services/blueprint/tests 2665 passed (24 new tests failed before the validator and bpdiff changes).
- check_contracts, check_docs, check_plan_independence, check_repo_hygiene: OK; check_lanes run against the stacked base.
- Footer postal address law and provider terms not researched: UNVERIFIED (Q-731), required on every marketing email (fail closed). Open tracking consent stays UNVERIFIED (LEG-012).

## Decisions
- No new ADR; ADR-0079 note. Design choices for review: the unsubscribe and footer blocks are fixed properties of each variant (platform wording), not free blocks; `clicks` as a winner metric needs click tracking (the brief named opens only); template add or remove is `config` because the schema guarantees both blocks.

## Next step
- Review by the partner (#409 and #398 merge first). BPL-059 enforces the send rules; WEB-037 builds the editor at G2.
