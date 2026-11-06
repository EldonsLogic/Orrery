# components

Status: draft
Owner: eldon

Purpose: the certified component library. Each component is a folder with a `manifest.json` that validates against the [component manifest schema](../contracts/component.manifest.schema.json), its package, tests and certification evidence. Lifecycle and rules: [component-library](../docs/architecture/component-library.md).

Planned first components: `core.customer`, `core.item`, `core.sales_order`, `core.sales_invoice`, country packs (`country.sa` then `country.ae`, then Egypt after legal check), `compliance.zatca_sa`, calendar and holiday components.

Rules: no customer data in components or tests; licences recorded; rigid components never AI-written without engineer ownership.

**Empty until gate G1.**
