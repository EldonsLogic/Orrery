# Runbooks

Status: draft
Owner: unassigned

Empty until gate G1; each runbook is written when the process first exists, tested once, then kept current. Format: purpose, preconditions, steps, verification, rollback, who.

| Runbook | Gate | Notes |
|---|---|---|
| Labels and project board mapping | G0 | [labels-and-board.md](labels-and-board.md), GOV-019 |
| Tenant provision (scripted, per region) | G1 | Site creation, keys, storage, roles, baseline Blueprint |
| Deploy and rollback (services, engine apps, components) | G1 | IaC, staging first, version pins |
| Backup and restore (per tenant) | G3 | Scheduled restore test, logged |
| Incident response | G3 | From [../security/incident-response.md](../security/incident-response.md) |
| Exceptions register (every manual step logged) | G2 | [exceptions-register.md](exceptions-register.md), GOV-017 |
| Periodic plan review | G1 | [plan-review.md](plan-review.md), `scripts/plan_review.py`, GOV-020 |
| Shipping plan rows with parallel subagents | G0 | [parallel-subagent-delivery.md](parallel-subagent-delivery.md), GOV-053 |
| Clear `recovery_required` on a tenant site | G1 | [adapter-recovery-required.md](adapter-recovery-required.md), ERP-026 |
| Rotate secrets and keys | G1 | Includes ZATCA key handling, gateway keys |
| Customer onboarding | G2 | Discovery to go-live checklist |
| Offboard, export and delete tenant | G3 | SLAs TBD ([../security/hosting-rules.md](../security/hosting-rules.md)); rules in [../security/data-retention.md](../security/data-retention.md) |
| Regulation change rollout | G2 | From [../compliance/regulation-watch.md](../compliance/regulation-watch.md) |
| Just-in-time support access | G2 | From [../security/access-policy.md](../security/access-policy.md) |
| Component certification and release | G2 | Component factory |
| Model/provider switch or outage | G2 | Gateway fallback |
| Brand asset incident (malicious upload) | G2 | From [../security/brand-asset-upload-security.md](../security/brand-asset-upload-security.md) |
| Release checklist (tenant environment) | G1 | [release-checklist.md](release-checklist.md), pre-release, release, post-release |
