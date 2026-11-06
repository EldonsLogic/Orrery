# Engine adapter

Status: draft
Owner: eldon

The engine (seed: Frappe + ERPNext) sits behind an adapter so it can be replaced. Decision: ADR-0002 (gated by the G1 spike). Basis: [strategy 04](../strategy/04-architecture-and-seed.md), [open-source research](../research/04-open-source.md).

## Adapter interface
Operations our services use. Each is idempotent where stated, takes a tenant id, and returns a structured result.

| Operation | Purpose |
|---|---|
| `provision_site(tenant, version_set, country_pack)` | Create an empty tenant site on the pinned set (idempotent) |
| `plan(tenant, compiled_config)` | Dry run: list DDL/schema and data changes, risk flags, destructive operations |
| `apply(tenant, change_set)` | Apply atomically; returns result and the stored inverse |
| `rollback(tenant, change_set_id)` | Apply the inverse; destructive parts quarantined |
| `snapshot(tenant)` / `restore(tenant, snapshot_id)` | Backup hooks |
| `export_config(tenant)` | Normalised configuration export for diff and verification |
| `execute(tenant, caller, operation, args)` | Perform a business operation with the **caller's** permissions (used by the tool API) |
| `query(tenant, caller, query)` | Scoped reads; metric queries |
| `subscribe(tenant)` | Stream record events to the event stream |
| `health(tenant)` | Site and queue health |
| `upgrade(tenant, target_set)` / `downgrade` | Version set moves |
| `delete_site(tenant)` | Verified erase |

## Frappe mapping (seed)
| Platform concept | Frappe/ERPNext |
|---|---|
| Tenant | Site (own database, own files directory) |
| Entity | DocType (standard or Custom DocType), Custom Fields |
| Field | DocField |
| Workflow | Workflow + Workflow State + Transition |
| Role/permissions | Role, DocPerm, user permissions (scope: branch, warehouse via User Permission) |
| Approval | Workflow transition conditions or custom approval doctype (decide in spike) |
| Report/dashboard | Query/Script Report definitions generated declaratively, Number Cards, Dashboard Charts |
| Print format | Print Format / Jinja templates from the country pack |
| Component | Frappe app or fixture bundle |
| Events | Doc events/webhooks to the event stream |
| Chat-triggered operation | REST or whitelisted method via a per-tenant service identity acting for the user |
Where Frappe's Flow/MCP features (MIT, noted in research) fit is decided in the spike; our AI layer stays outside the engine process.

## Version pinning
- One consistent **version set** (Frappe, ERPNext, HRMS if used, third-party apps by commit hash, Python and Node runtimes, OS image) is named, stored in the repo and used by every environment. Likely v15; to confirm in the spike (UNVERIFIED).
- No tenant runs a mix of sets. Sets are upgraded as a whole.

## Upgrade, canary, rollback
1. Build the candidate set in CI; run bench tests for every in-use component (the [compatibility matrix](component-library.md)).
2. Upgrade the sandbox tenants, then **canary tenants** (internal or willing pilots), with a fresh backup per site.
3. Watch error rates, financial reconciliation tests, e-invoicing status and performance.
4. Promote in batches; any blocking failure halts and rolls back sites to the previous set from their pre-upgrade snapshots (forward-fix if data has diverged).
5. Security patches follow the same path on a shorter clock.
Events: `engine.upgrade_*` ([events](../../contracts/events.md)).

## Engine invisibility (ADR-0016)
The engine is headless and internal. Our gateway and web app are the only customer-facing surfaces: own API paths, engine paths blocked or rewritten, engine headers removed, cookies renamed, errors mapped to our error model, our own print formats and emails. Nothing customer-visible names the engine. Enforcement: hygiene check in CI plus a staging crawl test.

## Licence boundary
- Frappe Framework: MIT. ERPNext, HRMS: GPL-3. ERPGulf ZATCA app: MIT (used). lavaloon ZATCA app: AGPL (not used). Evidence and access dates: [open-source research](../research/04-open-source.md).
- **SaaS only; the engine is never distributed to customers** without legal review (hybrid or on-prem later is a legal item). GPL has no network clause, so SaaS use does not force source release (counsel to confirm).
- Our AI services, compiler, web apps and control plane are **separate services** that talk to the engine over API; no code of ours is linked into the GPL process. Our Frappe apps that load into the engine process (core, compliance, change-engine, components under `apps/engine/`) are the exposed surface: counsel decides whether they must be GPL-compatible; until then keep them thin and keep proprietary logic in external services where possible.
- Do not use "ERPNext" or "Frappe" in the product name, domain or ads (trademark policy).
- Record the licence of every adopted dependency in NOTICE.md.

## Replaceability test
A second adapter (even a stub on another engine or a minimal in-house ledger) must be able to implement `plan/apply/execute` for the example Blueprint's core entities. We do not build it, but the interface must not leak Frappe types. Review this at each gate.

## Security notes
- Per-tenant service identities with least privilege; admin credentials stay in the control plane.
- `execute` always takes the caller; there is no "run as admin" path from the chat.
- All adapter calls logged with audit ids.

Plan IDs: ERP, BPL, SEC, QA, INF.
