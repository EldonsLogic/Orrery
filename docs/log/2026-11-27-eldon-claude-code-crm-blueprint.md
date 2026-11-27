# Session log: crm-blueprint

Date: 2026-11-27
Author: eldon
Tool and model: claude-code / opus-5.5
Plan IDs: BPL-052

## Summary
Blueprint 0.5.0 adds an optional `modules` object with `crm` (ADR-0079, Proposed): entity, workflow (pipeline stages), role and report vocabulary, opt-in per company, one implementing component. Contract text, schema, example and contract tests only; first of four stacked PRs (BPL-052 to BPL-055) on gov-078-module-scope (#392).

## Files touched
- contracts/blueprint.schema.json: 0.5.0; `modules`, `moduleRoles`, `moduleOption`, `crmModule`; two x-validator-rules.
- contracts/blueprint-modules.md: new contract doc (shape, CRM concepts and internal engine records, metric list, changelog).
- contracts/README.md: version row and example link.
- contracts/examples/blueprint-modules-minimal.json: valid example (fictional).
- contracts/examples/invalid/blueprint-modules-crm-cases.json: 15 negative cases applied by JSON pointer.
- contracts/tests/test_blueprint_modules.py: contract tests (valid, optional, each case fails at its path, versions agree, docs and metric vocabulary, no formula or posting keys).
- services/blueprint/diff/bpdiff/model.py: key-table rows for the three new keyed arrays (required by the bpdiff contract-coverage test); pipeline stage order is significant.
- docs/decisions/ADR-0079-engine-core-modules-in-the-blueprint.md, docs/decisions/INDEX.md, docs/open-questions.md (Q-700, Q-701), docs/PLAN.md (BPL-052 doing), docs/CHANGELOG.md.

## Checks
- Engine records read from the pinned ERPNext v15.124.5 source via the GitHub API (Lead, Opportunity, Sales Stage, Lead Source, Campaign, CRM Note, Opportunity Lost Reason); UNVERIFIED until a bench run (Q-701).
- ADR-0079 and Q-700 up checked free (coordinator: ADR-0077, 0078 and Q-692 to Q-699 are the connector PRs). scripts/check_contracts.py not edited (the payments PR edits it).

## Decisions
- [ADR-0079](../decisions/ADR-0079-engine-core-modules-in-the-blueprint.md) (Proposed).

## Tokens or cost
Unknown.

## Next step
BPL-053 (projects and boards, 0.6.0) stacked on this branch; partner reviews ADR-0079.

## Review fixes (#395 RULES 42 review at f3916b65)
- M1: `moduleRoles` description reworded so it grants nothing (screens treat roles as managers, workers, viewers); contract test `test_module_roles_description_grants_nothing`.
- M2: bpdiff classes `modules/<key>/roles` (and a whole module, which carries role lists) as `access`; impact-rule rows plus `test_module_role_change_is_access`; diff README rule 5.
- L3: rigid-zone guard widened to cost, tax, payroll, rate, price, amount, posting, account terms (substring or camelCase and snake_case token), walking shared module defs; matcher self-tests.
- L4: open pipeline stage needs probabilityPercent 1 to 99 (schema); negative cases `crm-open-stage-zero`, `crm-open-stage-100`.
- L5: Q-701 and blueprint-modules.md note that Converted may be derived from the quotation to order flow (bench item).
