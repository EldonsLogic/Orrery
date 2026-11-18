# Session log: opr-018-domain-error-codes

Date: 2026-11-18
Author: eldon
Tool and model: claude-code / sonnet-5.5
Plan IDs: OPR-018

## Summary
Added domain error codes to the Tool API: a versioned catalog of 14 codes with parameter slots and English and Arabic messages, a catalog schema, a validator and a fail-closed builder and renderer, contract text (tool-api 0.2.0) and ADR-0036 (Proposed). Subagent (sonnet) built it; I reran the tests and the contract check.

## Files touched
- contracts/tool-api-error-catalog.json and .schema.json, contracts/tool-api.md (7.1, version 0.2.0), contracts/README.md
- services/operate/toolapi/errors.py, tests; docs/decisions/ADR-0036 and INDEX
- docs/PLAN.md, docs/open-questions.md: OPR-018 done; Q-133 to Q-135

## Decisions
- ADR-0036 (Proposed): backward-compatible optional domain block; unmapped engine failures stay engine_error. Contract change, so it needs both founders' acceptance.

## Tokens or cost
Unknown or approximate, if known.

## Next step
Partner's PLT-024 fills the catalog from engine failures; native review of the Arabic messages.
