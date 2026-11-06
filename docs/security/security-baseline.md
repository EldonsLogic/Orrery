# Security baseline (v1)

Status: draft
Owner: eldon

Source of the v1 list: [../strategy/05-hosting-and-data.md](../strategy/05-hosting-and-data.md). SOC 2 / ISO 27001 are later items (12-24 months, ESTIMATE). Applicability of NCA ECC/CCC and CST rules to us is UNVERIFIED ([../compliance/vendor-certification.md](../compliance/vendor-certification.md)).

| # | Control | Requirement | Gate |
|---|---|---|---|
| 1 | Identity | MFA for all staff, internal and admin accounts; SSO later; tenant users: MFA available, enforced for owner/admin | G1 (staff), G3 (tenants) |
| 2 | Tenant isolation | One engine site/database per tenant, separate object-storage prefix, per-tenant keys, per-tenant backups; automated cross-tenant access tests in CI | G1 |
| 3 | RBAC | Role-based access in every tenant; tool API checks caller role and scope; no caller-supplied roles trusted | G1 |
| 4 | Audit trail | Immutable log of postings, config changes, AI actions, support access | G1 |
| 5 | Encryption | TLS 1.2+ in transit; encryption at rest; envelope keys per tenant | G1 |
| 6 | Secrets | Secret manager only; none in repo, images or logs; rotation runbook | G1 |
| 7 | Backups | Daily encrypted backups, restore tested on a schedule and logged | G3 |
| 8 | Logging and monitoring | Central logs without secrets or personal data beyond need; alerts on auth anomalies, cost spikes, tenant-boundary errors | G2 |
| 9 | Vulnerability management | Dependency scanning (Dependabot), image scanning, patch SLAs by severity (SLAs TBD) | G0 |
| 10 | Secure development | PR review, protected main, secret scanning, pre-commit hooks, cross-model review | G0 |
| 11 | LLM safety | Untrusted-content handling, tool allow-lists, no secrets in prompts, output validation, budgets ([threat-model.md](threat-model.md)) | G1 |
| 12 | Uploads | All uploads scanned and validated; brand assets per [brand-asset-upload-security.md](brand-asset-upload-security.md) | G1 |
| 13 | Data export/delete | Per-tenant full export and verified deletion | G3 |
| 14 | Incident response | Process in [incident-response.md](incident-response.md), exercised once before first paying customer | G3 |
| 15 | Independent test | External penetration test | G3 |
| 16 | Policies | Access, data classification, hosting rules in this folder, reviewed on change | G0 |

## Known issues to fix before any real use (change engine)
1. Caller-supplied roles accepted from request kwargs on whitelisted endpoints.
2. Role lookup falls back to System Manager on error (fail-open).
3. Runtime-policy registration has no permission check; policies kept in process memory (not persisted, per process, not per site).
4. LLM test-connection endpoint accepts a client-supplied API key and base URL (SSRF and key-handling risk).
5. CI runs mocks, not a real Frappe bench.
6. No LICENSE file.
Tracked as SEC items in [../PLAN.md](../PLAN.md). Gate G0 requires 1-4 fixed.
