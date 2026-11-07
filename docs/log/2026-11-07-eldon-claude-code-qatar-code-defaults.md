# Session log: qatar-code-defaults

Date: 2026-11-07
Author: eldon
Tool and model: claude-code; built by a Sonnet-tier sub-agent from an Opus-written brief, verified by the orchestrator (458 tests, hygiene)
Plan IDs: GOV-031

## Summary
Added Qatar (QA) to the validator locale defaults and the template instantiator, with tests, per ADR-0024. All Qatar values are UNVERIFIED placeholders until CMP-030 and the Qatar pack.

## Files touched
- contracts/blueprint.schema.json: country descriptions only (enum already had QA).
- services/blueprint/validator/defaults.py, tests/test_rules.py; services/discovery/templates (instantiate.py, questions.json), tests; two READMEs.

## Decisions
- Qatar placeholders: work week Sunday to Thursday, 08:00-17:00, fiscal year 1 January (copied from sa, UNVERIFIED); no VAT or e-invoicing assumed, vat_registered true is rejected for qa until researched.

## Tokens or cost
Unknown or approximate, if known.

## Next step
CMP-030 Qatar research, CMP-031 Qatar pack, GTM-019 Qatar lead calls.
