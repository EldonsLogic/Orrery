# Runbooks

Status: draft
Owner: unassigned

Empty until gate G1; each runbook is written when the process first exists, tested once, then kept current. Format: purpose, preconditions, steps, verification, rollback, who.

| Runbook | Gate | Notes |
|---|---|---|
| Tenant provision (scripted, per region) | G1 | Site creation, keys, storage, roles, baseline Blueprint |
| Deploy and rollback (services, engine apps, components) | G1 | IaC, staging first, version pins |
| Backup and restore (per tenant) | G3 | Scheduled restore test, logged |
| Incident response | G3 | From [../security/incident-response.md](../security/incident-response.md) |
| Rotate secrets and keys | G1 | Includes ZATCA key handling, gateway keys |
| Customer onboarding | G2 | Discovery to go-live checklist |
| Offboard, export and delete tenant | G3 | SLAs TBD ([../security/hosting-rules.md](../security/hosting-rules.md)) |
| Regulation change rollout | G2 | From [../compliance/regulation-watch.md](../compliance/regulation-watch.md) |
| Just-in-time support access | G2 | From [../security/access-policy.md](../security/access-policy.md) |
| Component certification and release | G2 | Component factory |
| Model/provider switch or outage | G2 | Gateway fallback |
| Brand asset incident (malicious upload) | G2 | From [../security/brand-asset-upload-security.md](../security/brand-asset-upload-security.md) |
