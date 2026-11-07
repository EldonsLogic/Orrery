# ADR-0014: Theming and tenant branding

Status: Accepted
Owner: eldon
Approved by: Eldon and partner

## Context
The UI needs light and dark themes. Customers want their own logo and colours, which sells the product but can break contrast, Arabic layout or legal invoice layout if unconstrained.

## Decision
Light and dark themes, system preference and a per-user choice persisted. Components never hard-code colours; everything resolves from tokens. Token layers, lowest to highest precedence: base tokens, product theme (light or dark), tenant overrides, user preference (theme mode only). Resolved tokens are served per tenant as CSS variables. Each tenant may set: logo (light-background and dark-background variants, or one mark with an auto-derived variant), display name, favicon (auto-generated), login-page branding, a primary colour and an optional accent, within guardrails. Guardrails: WCAG AA contrast checked against surfaces in both themes, auto-adjusted or rejected; status colours (success, warning, danger) and typography are fixed; Arabic and RTL behaviour is never affected. Branding is configuration: a `branding` section of the Blueprint, versioned, previewed before apply, changeable only by owner or admin roles, audited. The platform mark shows as "Powered by" per plan entitlement. Tenant-branded documents (invoices, PDFs, emails) use the tenant logo, but legally required layout wins (Arabic content on Saudi tax invoices, QR clear zone, mandatory fields). Uploaded brand assets are untrusted files: PNG, JPG, SVG only; size limits; SVG sanitised (scripts and external references stripped); malware scan; per-tenant storage; no executable content. Custom domains per tenant come later.

## Alternatives rejected
- Free-form CSS per tenant: breaks accessibility and security.
- No tenant branding: weaker sales story for owners.
- Branding as separate settings outside the Blueprint: loses versioning, preview and audit.

## Consequences
- Plan items: BRD-004 to BRD-008, BPL-013, PLT-017, PLT-018, SEC-006, ERP-016, WEB-007 to WEB-009, QA-007, QA-008.
- Compliance templates lock layout regions that branding cannot touch.
- Theme tests run in both themes and both directions.

## Supersedes
none
