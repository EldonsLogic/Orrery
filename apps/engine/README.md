# apps/engine

Status: draft
Owner: eldon

Purpose: Frappe apps for Part 3 (ERP runtime) and the apply layer of Part 2. Architecture: [engine-adapter](../../docs/architecture/engine-adapter.md), [change-engine](../../docs/architecture/change-engine.md), [spec 03](../../docs/specs/03-erp-runtime.md).

Planned apps
| App | Purpose |
|---|---|
| `core` | Platform glue inside the engine: tenant service identity, event emitter, calendar functions, API for the adapter |
| `compliance` | Country packs and e-invoicing. ZATCA via the **MIT-licensed ERPGulf app** (fork or embed with notice). The AGPL lavaloon app is NOT used |
| `change-engine` | The imported change engine module (renamed; CE-SEC-001..005 fixed on import) |
| `components` | Certified components that need engine code (see [components/](../../components/README.md)) |

Version pin: one consistent Frappe / ERPNext / HRMS version set pinned under ERP-001:
- Frappe Framework: `v15.126.0` (commit `53bae3ef2550ca96320f036f581446783cd11b72`)
- ERPNext: `v15.124.5` (commit `e5cde8c4b9e3f7f567a92ca3e65fd411402b89ce`)
- Frappe HRMS: `v15.64.8` (commit `186900a6e3db4e6f927f1ee20df745bbb082638a`)
- Dev environment: [infra/dev/docker/](../../infra/dev/docker/README.md) (MariaDB 10.6, Redis 7.2.7-alpine BSD-3-Clause).

Licence note: Frappe is MIT; ERPNext and HRMS are GPL-3. SaaS only, never distributed without legal review.

**Empty until gate G1.**
