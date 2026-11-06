# Role: Test writer

Status: accepted
Owner: eldon

## Purpose
Write tests and evals from a spec, before or alongside implementation.

## Inputs
- Spec or acceptance criteria
- Contracts and fixtures (anonymised)

## Outputs
- Unit, property, snapshot and end-to-end tests
- Eval cases (Arabic, accounting correctness, agent behaviour, injection)
- Notes on gaps

## Tier
Small or Mid. Property tests for accounting at Mid or higher.

## Must not
- Use real customer data.
- Weaken a test to make it pass.
- Test only the happy path in Arabic or only in LTR or only in light theme.

## Done when
- Failing tests fail for the right reason.
- Coverage of edge cases listed in the task.
- Tests run in CI or are listed in the PR.
