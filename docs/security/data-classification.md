# Data classification

Status: draft
Owner: eldon

| Class | Examples | Handling rules |
|---|---|---|
| C0 Public | Marketing pages, public docs, status page | No restriction |
| C1 Internal | Repo docs, plans, anonymised samples, architecture | Staff and agents only; no secrets |
| C2 Confidential | Tenant business data (invoices, stock, prices, customers/suppliers), Blueprints with tenant detail, tenant brand assets before publication | Tenant-isolated; encrypted at rest and in transit; access logged; LLM calls only via gateway with minimisation; in-country storage |
| C3 Restricted | Personal data of individuals (employees, IDs, IBANs, phones), payroll data, credentials, signing keys and CSIDs, API keys, support access tokens | As C2 plus field-level protection where possible, redaction before any LLM call unless needed, shortest retention, JIT audited access only, never in logs, never in the repo |

## Rules
- Real customer data never enters the repo, evals or prompts for development; use anonymised samples.
- Tenant data never leaves the tenant's region except under a documented, approved mechanism (legal position UNVERIFIED).
- Cross-tenant learning uses only generalised, de-identified patterns under the contract's anonymised-reuse clause (see [../legal/checklist.md](../legal/checklist.md)); promotion is a reviewed step.
- Derived data (embeddings, memory, caches) inherits the class of its source and the tenant boundary.
- Retention periods per class and per country: TBD, research needed ([../compliance/data-protection-and-residency.md](../compliance/data-protection-and-residency.md)).
- Exports and backups carry the same class as the source.
