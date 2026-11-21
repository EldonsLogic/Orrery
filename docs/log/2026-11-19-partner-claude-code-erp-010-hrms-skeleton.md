# Session log: erp-010-hrms-skeleton

Date: 2026-11-19
Author: partner
Tool and model: claude-code / claude-sonnet-5-5
Plan IDs: ERP-010

## Summary
Built `core.hrms_skeleton`, the Tier 3 HR skeleton for v1 (twelve doctypes, default deny, keyed idempotent configuration, tenant and company scope, backend roles, no self-approval of leave, exact decimal and date checks, no payroll maths), and marked `ERP-010` done.

## Files touched
- `components/core/hrms_skeleton/`: new component (`manifest.json`, `strings.json`, `README.md`, `scope.py`, `specs.py`, `validation.py`, `service.py`, `access.py`, `memory.py`, `frappe_backend.py`, `errors.py`) and `tests/` (74 tests).
- `components/README.md`: lists `core.hrms_skeleton`.
- `.github/workflows/tests.yml`: one new step for the component tests; every existing step kept.
- `docs/PLAN.md`: `ERP-010` set to `done`.
- `docs/open-questions.md`: Q-280 (field names and engine calls unverified on the bench), Q-281 (submit lifecycle), Q-282 (platform HR roles).

## ADR-0031 record (rigid-zone code)
- Model that wrote the code: claude-sonnet-5-5, Claude Code, run for the partner (`sayegh9`).
- Brief it was given: implement `ERP-010` as a Tier 3 component in `components/core/hrms_skeleton/`. Only the twelve doctypes in `docs/specs/core-module-scope-trading.md` section 4; block every other HR and payroll doctype with a fail-closed `is_allowed_doctype` / `assert_allowed_doctype`. No payroll calculation, tax, GOSI or end-of-service maths; Decimal and date validation only. Fail-closed tenant and company scope, roles from the backend session only, `HR Manager` / `System Manager` for salary, leave policy, leave allocation and employee masters, no self-approval of leave, keyed idempotent upserts (ADR-0028). Manifest valid against the schema with `level: tested` and `reviewedBy: []`; Arabic and English strings with the ADR-0033 unreviewed marker and no engine names (ADR-0016); tests, CI step, README, PLAN, log. Stay in the partner lane, never merge, do not poll CI.
- Official vectors (ADR-0031 condition 1): none. The component computes no figure, so no vector applies; the tests are behaviour and refusal checks, and no test claims conformance to a regulator.
- Not yet done, so the component stays at `tested`: line-by-line review by a founder who did not prompt it (Eldon), a different model reviewing it, the security review, accountant review of payroll structure before Phase 2 (LEG-019), and a bench run (Q-280).

## Checks run
- Component tests: 74 pass. Three guards (self-approval, store tenant, role check) were switched off in a scratch copy and each made tests fail, so the tests do detect them.
- The manifest validates against `contracts/component.manifest.schema.json`.

## Decisions
- No ADR. The component declares `riskClass: ledger` for the three payroll entities (raise-only under ADR-0037, which is still Proposed) and declares none for the others, so the Tool API generator keeps its stricter default for them.
- Salary Component and the other payroll doctypes accept fixed amounts only. Any formula, condition or rate field is refused.
- A `Leave Approver` who is not `HR Manager` or `System Manager` must be the designated approver on the application. This goes beyond the brief and is easy to remove if the founders disagree.

## Tokens or cost
Unknown.

## Next step
- Eldon: line-by-line review of the PR (Tier 3), with a different model than the author's, and the security review.
- Partner: run the component on the bench with synthetic data and settle Q-280 to Q-282 before moving past `tested`; then `CMP-015` (WPS file output) can build on it.
