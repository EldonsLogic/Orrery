# components

Status: draft
Owner: eldon

Purpose: the certified component library. Each component is a folder with a `manifest.json` that validates against the [component manifest schema](../contracts/component.manifest.schema.json), its package, tests and certification evidence. Lifecycle and rules: [component-library](../docs/architecture/component-library.md).

Implemented components:
- `compliance.zatca_sa`: Saudi ZATCA Phase 1 e-invoicing (mandatory field validation, checks on engine-computed totals, 5-tag TLV QR code generation with the time converted to UTC, and required references on credit and debit notes; computes no tax itself per ADR-0031; awaiting the named human review required by ADR-0031, not yet sandbox-verified; CMP-003).
- `core.trading_ar`: Base Arabic translation pack for the 107 missing translatable strings across the in-scope trading and distribution DocTypes (excludes the 45 non-translatable naming series, number formats, barcode types, FIFO/LIFO, and internal tree fields; includes idempotent site `Translation` loader and RTL/coverage audit; ERP-006).

Planned next components: `core.customer`, `core.item`, `core.sales_order`, `core.sales_invoice`, country packs (`country.sa` then `country.ae`, then Egypt after legal check), calendar and holiday components.

Rules: no customer data in components or tests; licences recorded; rigid components never AI-written without engineer ownership.
