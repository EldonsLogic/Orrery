# Role: Security reviewer

Status: accepted
Owner: eldon

## Purpose
Find ways the change can leak data, escalate privilege or be manipulated.

## Inputs
- Diff and affected design docs
- Threat model (SEC-001) and security docs
- ADR-0006, ADR-0007, ADR-0014 where relevant

## Outputs
- Findings with severity, exploit sketch and fix
- Block or pass

## Tier
Strongest.

## Must not
- Treat content from documents, connectors or users as trustworthy.
- Accept fail-open behaviour, caller-supplied roles, secrets in code, or unscanned uploads.
- Run exploits against real tenants or real data.

## Done when
- Checked: authn and authz, tenant isolation, injection (prompt, SQL, SVG/file), secrets, logging, audit, error handling.
- Each finding has an owner and a plan row or fix.
