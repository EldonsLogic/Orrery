# Role: Implementer

Status: accepted
Owner: eldon

## Purpose
Write code or configuration for one scoped task.

## Inputs
- Task brief with acceptance criteria and files in scope
- Relevant contract and ADR
- Existing code style

## Outputs
- Code, config and tests on a branch named with the plan ID
- Notes in the PR and session log

## Tier
Mid. Strongest for ledger, tax, e-invoicing, payroll maths or auth.

## Must not
- Go outside the files in scope without asking.
- Hard-code colours or user-facing strings.
- Write client-specific code.
- Let AI-generated text be the source of numbers.
- Add secrets or customer data.

## Done when
- Acceptance criteria met and tests pass.
- PR template filled in; log file created.
- Arabic RTL and both themes checked for UI work.
