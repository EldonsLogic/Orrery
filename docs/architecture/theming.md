# Theming and tenant branding

Status: draft
Owner: eldon
Decision record: ADR-0014 (Theming and tenant branding). Tokens: [docs/brand/tokens](../brand/tokens/tokens.json) and [tokens.css](../brand/tokens/tokens.css).

## Requirements
1. The platform UI has a light and a dark theme (system preference by default, user choice persisted per user). Components never hard-code colours; everything resolves from tokens.
2. Every tenant can brand its workspace: logo (light and dark variants, or one mark with an auto-derived variant), display name, favicon, login page, primary colour and optional accent, within guardrails.
3. Status colours (success, warning, danger) and typography are fixed. Arabic/RTL behaviour is never affected by branding.

## Token layering (lowest to highest precedence)
```
1 base tokens (platform, docs/brand/tokens)
2 product theme (light | dark)
3 tenant overrides (primary, accent, logos, display name)
4 user preference (theme mode only: light | dark | system)
```
- Layer 4 selects between layers 2 and 3's light/dark outputs; it never changes colours.
- Only a whitelist of tokens can be overridden by a tenant: `color-primary`, `color-accent`, and derived tokens (hover, pressed, tint, focus ring). Background, surface, text and status tokens are not overridable.

## How resolved tokens are served per tenant
1. At apply time the compiler resolves layers 1-3 for both themes and stores a **resolved token set** (version, tenant id, light map, dark map, derived values, contrast report, asset URLs).
2. The app shell requests `/tenant/tokens.css` (cacheable, versioned URL). The response is CSS variables scoped to `:root[data-theme="light"]` and `:root[data-theme="dark"]` plus brand asset URLs.
3. The user preference sets `data-theme` on the root element; the system preference applies when set to "system".
4. Server-rendered documents and emails use the same resolved set, light variant.
5. A preview endpoint serves a candidate set for the admin's session only; it is never visible to other users until applied.

## Branding lives in the Blueprint
- Section `branding` of the [Blueprint](../../contracts/blueprint.schema.json): display name, logos (asset references), `primaryColour`, `accentColour`, favicon, login page, document header options, `poweredBy`.
- It follows the normal change path: edit (settings screen or chat), **preview** (rendered in light and dark, LTR and RTL, with the contrast report), **approve** (owner/admin roles only: `isAdmin`), **apply** (new revision), **audit** (`branding.changed` event with before/after hashes). Rollback restores the previous revision.
- Branding changes are configuration-zone: they do not need team review, but asset uploads pass the pipeline below.

## Guardrails: automatic WCAG AA in both themes
Computed by code on every change and before apply:
| Check | Rule |
|---|---|
| Primary vs surface and background | Contrast >= 4.5:1 for text use, >= 3:1 for large text and UI components, in light and in dark |
| Text on primary (button labels) | >= 4.5:1; the system picks light or dark label colour automatically |
| Accent | Same checks where it carries meaning; never the only signal |
| Focus ring | >= 3:1 against adjacent colours |
| Distinguishability from status colours | Primary and accent must not be too close to success, warning or danger hues (distance threshold TBD) |
Outcomes: **pass**; **auto-adjust** (nudge lightness while keeping hue, show the adjusted colour in the preview and record it); or **reject** with a plain-language reason. Dark theme gets its own derived primary where the light one fails. The brand check tool pattern is in [docs/brand/tools/check_contrast.py](../brand/tools/check_contrast.py).

## Documents versus compliance
Tenant-branded documents (tax invoices, PDFs, emails) use the tenant logo and display name, but **legally required layout wins**: Arabic content on Saudi tax invoices, QR code and its clear zone, mandatory fields, mandated positions and font sizes where specified ([country packs](country-packs.md)). Branding options apply only to non-mandated areas. Template tests check mandatory elements after branding is applied; a branding change that breaks them is rejected. Logos on documents are rendered in the light variant on a white area with a minimum clear space.

## Brand asset storage and favicon generation
- Assets are untrusted files. Accept PNG, JPG, SVG only; max 2 MiB; dimension limits; reject animated/embedded content.
- Pipeline: upload to quarantine, type sniff, malware scan, **SVG sanitisation** (strip scripts, event handlers, external references, foreign objects), re-encode rasters, strip metadata, hash, store in the tenant's own storage prefix with per-tenant encryption, serve from a separate asset origin with `Content-Security-Policy` and `nosniff`, never inline-executed.
- The Blueprint stores an `assetRef` (id, media type, bytes, sha256, `sanitised: true`); the asset record is authoritative.
- **Favicon**: generated from the logo in the required sizes (16, 32, 48, 180, 192, 512) plus a manifest icon; a high-contrast variant for dark browser themes; or a separately uploaded favicon asset.
- **Dark logo**: if only a light-surface logo is supplied and `deriveDark` is true, derive a dark-surface variant (monochrome recolour where legible, else place on a neutral chip) and show it in the preview.

## White-label entitlement
The platform mark appears in the app chrome as "Powered by". `branding.poweredBy.show = false` requires the white-label entitlement on the plan ([tenancy-and-identity](tenancy-and-identity.md)); checked server-side at apply time. Custom domains per tenant are later (see tenancy doc).

## Failure modes and tests
- Contrast and RTL tests for tenant themes in [evals/](../../evals/README.md): sample palettes (including very light, very dark, near-status hues) in both themes, LTR and RTL.
- Golden PDFs for branded tax invoices; QR clear zone check.
- Malicious SVG corpus must be neutralised.
- A tenant cannot read another tenant's assets or tokens (isolation test).

Plan IDs: BRD (token layering, theme engine, asset pipeline), WEB (Branding settings screen, login page, document templates), PLT (brand storage, entitlements), SEC (asset upload security), QA (contrast and RTL tests).
