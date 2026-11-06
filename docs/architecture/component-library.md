# Component library

Status: draft
Owner: eldon

The library is the product's compounding asset: versioned, tested, certified building blocks that the compiler assembles into each tenant's system. Contract: [component manifest](../../contracts/component.manifest.schema.json). Principle 9: no client-specific code; a need no component covers becomes a candidate component built once for everyone.

## Rigid vs configurable
| | Rigid | Configurable |
|---|---|---|
| Examples | Ledger posting, tax, e-invoicing (ZATCA), payroll maths, audit trail, country packs | Custom fields, workflows, approvals, roles, print layouts, dashboards, notifications, role views |
| Written by | Engineers; AI may assist, humans own | Engineers or the factory with review |
| Tenant parameters | None beyond enable/disable (manifest rule: `parameters` empty) | Declared in the manifest, set from the Blueprint |
| Min certification | `reviewed`, `regulated` where an authority is involved | `tested`, `certified` before general availability |
| Change after go-live | Team review always | Owner-approved through the change path |

## Lifecycle
```
request -> spec -> build -> test -> certify -> publish -> (deprecate -> retire)
```
1. **Request**: gap analysis or an engineer opens a component request: need, evidence (anonymised pattern, not customer data), proposed capability ids, rigid or configurable.
2. **Spec**: AI drafts the spec and the tests first (acceptance tests, edge cases, Arabic/RTL cases); an engineer edits and approves the spec.
3. **Build**: implementation as a package under `components/` (and engine apps under `apps/engine/` where code is needed). Open-source search first; record licences.
4. **Test**: unit, bench (real engine), simulation, RTL/Arabic text, contrast where UI, compliance sandbox where regulated, security tests. All blocking tests must pass.
5. **Certify**: a named engineer reviews code and config; canary on test tenants; evidence stored in the manifest. Level assigned.
6. **Publish**: version tagged (semver), registry updated, compatibility matrix updated, `component.published` event.
7. **Deprecate / retire**: `lifecycle.status` moves to deprecated with a migration note and `replacedBy`; tenants are migrated through the normal change path; retire when none use it.

## Certification levels
| Level | Meaning | Usable by tenants |
|---|---|---|
| `draft` | Authored, not tested | No |
| `tested` | Blocking tests pass in CI | Sandbox only |
| `reviewed` | Engineer reviewed code and config | Sandbox and team-reviewed builds |
| `certified` | Reviewed + canary + Arabic/RTL checks | Production |
| `regulated` | Certified + compliance evidence (for example ZATCA sandbox) + named compliance owner | Production, required for e-invoicing and tax |
Components with `touchesLedgerOrTax` cannot be below `reviewed`; the manifest schema enforces it.

## Compatibility matrix
Maintained by CI: rows are component versions, columns are engine version sets (pinned sets from [engine-adapter](engine-adapter.md)). A cell is `tested-pass`, `tested-fail` or `untested`. The compiler refuses `fail` and `untested` cells for production. A new engine set cannot be promoted until every in-use component has a passing cell.

## Dependencies and versioning
- `requires` lists components or capabilities with version ranges; the compiler resolves a consistent set or fails with an explanation.
- Semver: patch = fix, minor = backward-compatible capability, major = breaking (needs migration note and a change-path migration).
- Tenants pin resolved versions in the compiled artifact; upgrades go through diff and simulation like any change.

## Promotion rules (learning from clients)
- A pattern seen in a client build can be promoted to the library only as a **generalised pattern**, written fresh by an engineer or the factory, with fictional test data. The contract's anonymised-reuse clause is the legal basis ([data](data.md)).
- Never copy tenant records, names, prices, file contents or free-text answers into a component, test, prompt, eval or template.
- Promotion review checks: could this identify a customer? Is the pattern generic across at least two prospects or an obvious industry norm?
- Template Blueprints (for example trading and distribution) are curated by us, not derived automatically.

## No customer data
Tests and examples use fictional data. CI scans components for patterns resembling real identifiers (VAT numbers, IBANs, phone numbers) and fails the build. Registry stores no tenant data.

## Metrics
Reuse ratio (share of tenant Blueprint elements bound to existing components), new components per client, time from request to certified, share of AI-drafted specs accepted unchanged, components deprecated. Targets: [strategy 08](../strategy/08-product-vs-software-house.md).

Plan IDs: BPL (registry, factory), QA (matrix, golden tests), ERP (rigid components), SEC (reviews), LEG (licence records).
