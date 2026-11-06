# Theming and tenant branding (user-facing behaviour)

Status: draft
Owner: eldon

Decision record: ADR-0014 (see [../decisions/](../decisions/)). Tokens: [../brand/tokens/](../brand/tokens/). Upload security: [../security/brand-asset-upload-security.md](../security/brand-asset-upload-security.md).

## 1. Themes
| Behaviour | Rule |
|---|---|
| Modes | Light, dark, system (follows OS) |
| Choice | Per user, persisted, user preference beats tenant default for mode only |
| Components | Never hard-code colours; everything resolves from tokens |
| Layering (low to high) | Platform base tokens -> product theme (light/dark) -> tenant overrides -> user preference (theme mode only) |
| Delivery | Resolved tokens served per tenant as CSS variables |

## 2. What a tenant can set
| Item | Behaviour |
|---|---|
| Logo | Upload for light backgrounds and dark backgrounds, or one mark and the system derives the other variant (e.g. light-on-dark inversion check; owner confirms the preview) |
| Display name | Shown in app header, emails, documents; Arabic and English versions |
| Favicon | Generated from the logo in required sizes; owner previews |
| Login page | Logo, name, optional short welcome line (AR/EN); platform legal links stay |
| Primary colour (optional accent) | Chosen within guardrails below |
| Documents | Tax invoices, quotes, PDFs, emails use the tenant logo and name |
| "Powered by" | Platform mark in app chrome; removable only with the matching entitlement ([pricing.md](pricing.md)) |

## 3. Guardrails
| Rule | Detail |
|---|---|
| Contrast | System checks WCAG AA contrast of chosen colours against surfaces in BOTH themes; it auto-adjusts the shade or rejects with the reason |
| Fixed | Status colours (success, warning, danger), typography, spacing, RTL behaviour |
| Legal layout wins | On Saudi tax invoices, Arabic content, QR code clear zone and mandatory fields cannot be moved or covered by branding. Exact mandatory fields and layout: research needed (see [../compliance/e-invoicing.md](../compliance/e-invoicing.md)) |
| Assets | PNG/JPG/SVG only, size limits, SVG sanitised, malware scan |
| Who | Owner and admin roles only; every change audited |
| Process | Branding lives in the Blueprint `branding` section: versioned, previewed before applying, reversible |

## 4. Preview before apply
1. Owner opens Settings > Branding and uploads or picks.
2. System shows live preview: app (light and dark), login page, sample tax invoice, sample email, favicon sizes, in Arabic and English.
3. Contrast report shows pass/adjusted/rejected per surface.
4. Owner clicks Apply; system writes a Blueprint diff, applies, logs. Roll back restores the previous version.

## 5. Examples
| Input | Result |
|---|---|
| Primary `#0B5FA5` on both themes passes AA | Accepted as is |
| Pale yellow `#FFE680` as primary (fails on white surface) | Adjusted: darker shade proposed for light theme, original kept for dark if it passes; owner sees both |
| Neon green primary that cannot pass on either surface | Rejected with message naming the failing surface and contrast ratio |
| Logo SVG with `<script>` or external image link | Scripts/links stripped by sanitiser; if nothing usable remains, rejected |
| Logo 12 MB PNG | Rejected: over size limit; limit stated in the message |
| `.exe` renamed `.png` | Rejected: content check fails; file not stored |
| Logo overlapping invoice QR zone (via custom template) | Rejected: legally required layout wins |
| Request to change danger red to brand colour | Not available: status colours are fixed |
| Request to change font | Not available in v1 |
| Staff (non-admin) opens Branding | View only, or hidden by role |
| Custom domain | Later; not in v1 |

## 6. What tenants cannot change
Status colours, typography, layout structure, RTL behaviour, compliance fields on documents, security banners and legal links, the platform name in the legal footer.

## 7. Platform dependencies
BRD token layering and theme engine; WEB Settings > Branding screen, login page, document templates; PLT brand storage and entitlements; SEC asset upload security; QA contrast and RTL tests for tenant themes. IDs live in [../PLAN.md](../PLAN.md).
