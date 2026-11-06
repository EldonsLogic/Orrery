# infra

Status: draft
Owner: unassigned

Purpose: infrastructure as code and environment definitions.

Planned contents
- Environments: local dev, CI, staging, sandbox tenants, production (per country region).
- IaC for networking, compute, storage, secrets vault, backups, observability.
- Scripts references for tenant site provisioning (implementation in [scripts/](../scripts/)).
- Engine version set definition (see [apps/engine](../apps/engine/README.md)).

Rules: [docs/security/hosting-rules.md](../docs/security/hosting-rules.md). In-country placement per tenant country; provider choice recorded in an ADR (availability UNVERIFIED). No secrets in this folder.

**Empty until gate G1.**
