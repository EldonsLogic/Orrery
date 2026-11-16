# Session log: erp-003-provisioning-review

Date: 2026-11-16
Author: partner
Tool and model: antigravity / gemini-4-hydrogen; codex / gpt-6.1-terra
Plan IDs: ERP-003

## Summary
Addressed the ERP-003 provisioning review with input validation, redaction, supported configuration commands, and fail-closed app verification.

## Files touched
- scripts/provision_tenant_site.py: validate input, use Compose and bench commands, restrict credential input and output, and fail closed on verification errors.
- infra/dev/docker/provision_tenant.sh: target the named Compose project.
- apps/engine/change_engine/change_engine/tests/test_erp_003_tenant_provisioning.py: add regression tests.

## Decisions
- None. Site configuration does not enforce engine invisibility.

## Tokens or cost
Not measured.

## Next step
ERP-003 remains doing. Test live provisioning on an isolated synthetic bench and obtain an independent security review. Bench receives passwords as process arguments inside the container; credential delivery needs review. A credential-file write can fail after site creation; recovery needs review. The old branch base and CI test integration also remain to be resolved.

## Verification
- 13 focused tests passed; shell syntax, secret scan, and repo hygiene passed.
- Pinned bench help and list-apps JSON format were inspected; live provisioning was not run.
