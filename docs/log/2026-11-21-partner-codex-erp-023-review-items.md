# Session log: erp-023-review-items

Date: 2026-11-21
Author: partner
Tool and model: codex (GPT-6.2 Sol)
Plan IDs: ERP-023,ERP-029

## Summary
Addressed Eldon's PR #203 review items 1–4 at base `7acebb5`. ERP-023 stays in progress pending human line-by-line Tier 3 review under ADR-0031.

## Review items

1. **Callback runner.** Made the adapter's raw callback runner private. Updated `ChangeEngineAdapter.execute_action` and the three invocations in the ERP-012 T36 caller impersonation test. The engine backend's own callback primitive is internal infrastructure used by the private wrapper.
2. **Tenant binding.** The adapter looks up the tenant from the authenticated session independently of the action context resolver. Admission refuses a missing binding, a mismatched request tenant or a mismatched action context before claiming anything. The adapter uses the session tenant for backend dispatch.
3. **Outcomes.** SQLite appends one outcome per admitted tenant and request. A successful handler returns after the durable effect and records `applied`. A failure before dispatch or a handler-confirmed rollback records `failed`. Other post-dispatch failures record `unknown`. A process crash or journal write failure can leave the admission without an outcome. ERP-029 owns reconciliation before OPR-004 or OPR-007 enables a live handler. ERP-028 is absent from the base, so ERP-029 follows ERP-027 in PLAN and uses ERP-023's Runtime/G2 classification.
4. **Money.** The policy refuses negative money and precision outside the supported currency scale. For priced lines it compares the submitted total with the exact sum of quantity × price minus the absolute discount on each line. AP-FIN-02 compares a non-negative cancellation amount with the engine's preview for the bound source revision. The starter table enables no credit action. The engine remains the calculation authority under ADR-0031.

## Verification

- ERP-023 tests first against `7acebb5`: 10 failed, 58 passed. With the fixes and additional coverage: 73 passed.
- BPL-012, ERP-012, BPL-027 and CE-SEC mocks: 74 passed, 9 live-bench skips, 22 subtests passed.
- Both BPL-025 conformance harnesses: 208 passed each. Script tests: 22 passed and 29 subtests passed.
- ERP-026 offline baseline on its separate branch at `1218a20`: 30 passed, 36 live-mode skips, 39 subtests passed. Its modules are absent from the ERP-023 branch.

## Founder review

- Item 5 remains a production follow-up for refusal journal growth, per-session limits and database file access.
- Item 6 remains with the founders. ADR-0027 is Proposed and Q-44 is open.

## Implementation brief

Write failing tests first. Close the public callback path, bind the tenant independently of request data, record outcomes after the effect, and refuse invalid money or totals against the bound snapshot. Keep changes within the PR and permitted adapter tests. Leave review items 5 and 6 as notes.
