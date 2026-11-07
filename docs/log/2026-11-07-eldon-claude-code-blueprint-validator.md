# Session log: blueprint-validator

Date: 2026-11-07
Author: eldon
Tool and model: claude-code (cloud session); implemented by a Sonnet-tier sub-agent from an Opus-written brief, reviewed and verified by the orchestrator (Opus)
Plan IDs: BPL-003

## Summary
Blueprint validator for contract 1: JSON Schema 2020-12 step, then one check per x-validator-rule (locale resolution and working time, country and pack match, unique ids and reference resolution, locale coverage of every localized text, workflow graph, approvals, role scopes, component registry and semver ranges, computed functions provided by bound components, WCAG AA contrast in both themes with auto-adjust or reject, asset records, white-label entitlement fail-closed, SA e-invoicing). Stable rule codes, a CLI, 128 tests and a CI job. Never raises on bad input.

## Files touched
- services/blueprint/validator/ (new), services/blueprint/tests/ (new), services/blueprint/README.md, services/blueprint/requirements.txt.
- .github/workflows/ci.yml: new `blueprint-validator` job (tests, and the contract example must validate).
- docs/PLAN.md: BPL-003 done.

## Decisions
- Contrast: each theme judged on its own against surface and background; primary at 4.5:1 (text use), accent at 3:1; auto-adjust keeps hue and shifts lightness by at most 0.30, else reject. The minimal example's primary gets a dark-theme adjustment warning.
- selfApproval read literally: allowed only if an owner-function role holds approve on that entity.
- Larger than the ~400-line PR guideline (about 1,700 lines with tests); it is one coherent unit.

## Tokens or cost
Unknown.

## Next step
BPL-005 fixture validated by this validator; follow-up rules from the threat model (reserved names, typed guards, size caps); BPL-006 diff.
