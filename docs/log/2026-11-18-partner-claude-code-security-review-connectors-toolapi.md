# Session log: security-review-connectors-toolapi

Date: 2026-11-18
Author: partner
Tool and model: claude-code / opus-5.5
Plan IDs: DSC-010,DSC-011,OPR-003

## Summary
Read-only cross-model security review (Opus-class reviewer; the code was written with Sonnet-class models) of the connector framework (PR #88), the Excel and CSV parser (PR #97) and the Tool API generator (PR #95). Reviewed on `main` at a64d74b against PI-002 to PI-007 and A01 to A13, the BAU parser rules, ALP-* and `contracts/tool-api.md`. Every finding was reproduced with a scratch script kept outside the repo. Findings were posted as one comment per PR. No code was changed.

## Findings (severity-ranked; details, inputs and fixes are in the PR comments)
Tool API, PR #95 (https://github.com/EldonsLogic/Orrery/pull/95#issuecomment-6977863001)
- Critical T1: ledger and stock entities missing from the name table fall back to `plain` (`journal_entry.submit` R1 with no agent approval; `.cancel` R2 agent-creatable).
- Critical T2: the registry can lower a class or effects (`sales_invoice` to `plain`, so `submit` becomes R1 and `cancel` R2, both agent-creatable).
- High T3: transition kind comes from exact id tokens, so `mark_approved` or `void_invoice` slips past the approve and R4 rules.
- High T4: bank-detail changes (IBAN on `supplier.update`) and permission entities (`user_role.create`) come out as R1 agent-creatable.
- Medium T5 to T8: gaps in forbidden argument names; `export` has kind read; hidden fields can be filtered and grouped on; workflow bypass through a `status` field. Low T9 and T10.
- Even with T1 to T4 present, `check_tool_api` returned no issues.

Connector framework, PR #88 (https://github.com/EldonsLogic/Orrery/pull/88#issuecomment-6977862421)
- High F1: `source.path` is unsanitised, uncapped and unlabelled connector text (a way around the L3 envelope).
- Medium F2: `stats` keys are free text. Medium F3: variation selectors and C0/C1 controls are not stripped. Medium F4: no sandbox; PI-006 rests on what the connector declares, and the connector can change its own budget. Low F5 and F6, Info F7.

Excel and CSV parser, PR #97 (https://github.com/EldonsLogic/Orrery/pull/97#issuecomment-6977863536)
- High X1: cell comments are model-facing (PI section 3.3 says to drop them).
- Medium X2: a hidden sheet's name reaches the model. Medium X3: zero-height rows, zero-width columns, `;;;` format and white 1pt font are not treated as hidden. Low X4 and X5.
- Nothing real found for zip bombs, DOCTYPE and entities, path traversal, formula evaluation, macros, or side effects from the parser.

## Not covered
The odoo and intake connectors; the gateway (OPR-004) and model gateway (PLT-009), not yet built; tools contributed by components; fuzzing; the existing test suites.

## Files touched
- docs/log/2026-11-18-partner-claude-code-security-review-connectors-toolapi.md: this log.

## Decisions
- None. The fixes belong to Eldon's lane (DSC-010, DSC-011, OPR-003 are his rows). T1 to T4 need a decision on where entity classes, transition kinds and field sensitivity come from (reviewed component manifest or Blueprint schema). That likely needs an ADR, which Eldon's side should raise.

## Tokens or cost
Unknown.

## Next step
Eldon's agent triages the PR comments and opens fix rows or PRs for T1 to T4, F1, X1 first, then the Medium findings. A re-review by a different model once the fixes land.
