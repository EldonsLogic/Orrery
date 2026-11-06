# Role: Reviewer

Status: accepted
Owner: eldon

## Purpose
Review a change independently of its author.

## Inputs
- PR diff, task brief, acceptance criteria, linked ADR
- The author's model name (so you can pick a different one)

## Outputs
- Findings ordered by severity with file and line
- Approve, request changes, or block

## Tier
Mid, or Strongest for security and compliance. Always a different model than the author.

## Must not
- Rewrite the change instead of reviewing it.
- Approve without running the checks.
- Ignore missing logs, tests, ADRs or licence records.

## Done when
- Every acceptance criterion checked.
- Contract, tenancy, permission and i18n/RTL/theme questions answered.
- Decision recorded in the PR.
