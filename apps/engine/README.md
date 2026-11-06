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

Version pin: one consistent Frappe / ERPNext / HRMS version set (likely v15, to confirm in the G1 spike; UNVERIFIED). The set is named and stored here when chosen; third-party apps are pinned by commit hash.

Licence note: Frappe is MIT; ERPNext and HRMS are GPL-3. SaaS only, never distributed without legal review.

**Empty until gate G1.**
