# 12 Tenant theming and branding (PROPOSED)

Status: proposed. Owner: unassigned (decision record: ADR-0014 Theming and tenant branding).
Requirement source: `CONTEXT.md` section 9. Nothing here changes v1. Code: `tools/derive_tenant_theme.py` (stdlib), tests `tools/test_derive_tenant_theme.py`, preview `preview-tenant-themes.html` (generated). Constants below are PROPOSED and were calibrated by me, not by a designer. Arabic copy needs native review.

## 1. Token layers (lowest to highest precedence)
| # | Layer | Source | Notes |
|---|---|---|---|
| 0 | Orrery base | `tokens/tokens.json` (v1) | The 8 colours, type, radii |
| 1 | Product theme, light or dark | `tokens.css` + `tokens.proposed.css` | Dark is a full set, not an inversion |
| 2 | Tenant overrides | Blueprint `branding` section, resolved to CSS | Scoped as `:root[data-tenant="slug"]` (light), plus the same under `prefers-color-scheme: dark` and `[data-theme="dark"]`, loaded after layer 1 |
| 3 | User preference | `data-theme` light, dark or system, persisted per user | Changes theme mode only, never tenant colours |

Components read variables only. The server stores the resolved tokens at apply time with `themeAlgo` (the algorithm version), so a later algorithm change never silently restyles a tenant; re-derive only on an explicit save.

## 2. What a tenant may and may not change
| May override | Input | Becomes |
|---|---|---|
| Primary | One hex colour | `--color-primary`, `-hover`, `-pressed`, `-label`, `--color-link-visited`, `--state-selected`, `--state-secondary-hover/-pressed`, `--color-device-primary`, focus ring colour, in both themes |
| Accent (optional) | One hex colour | `--color-accent` in both themes; graphics only, never text. Default stays Coral |
| Logo set | Files (section 4) | Chrome, login, documents, emails |
| Display name | Text, 1 to 40 characters, any script | Beside the logo when the logo has no wordmark; document headers |
| Favicon | Auto from the logo, or a custom upload under the same rules | Section 5 |

| Locked (never tenant-controlled) | Why |
|---|---|
| Status colours (Jade, Ochre, Crimson) and their pill tokens | Meaning must be the same in every tenant |
| Background, surface, text, muted, border neutrals | Contrast guarantees depend on them |
| Chart palette (including series 1) | Colour-blind separation is verified for this set only. Open question: let series 1 follow the tenant primary |
| Typography, spacing, radii, icon set, motion | Brand and layout integrity |
| Focus ring width, offset and the 3:1 rule (colour follows the primary) | Accessibility |
| Arabic and RTL behaviour, Western digits, mirroring rules, the Latin name "Orrery" | v1 rule |
| The Orrery mark in "Powered by" | Orrery's own mark, mono |

## 3. Derivation algorithm (`derive_tenant_theme.py`)
Input: one primary hex, optional accent hex. Work in OKLCH (L lightness, C chroma, H hue; Ottosson matrices). Every colour is gamut-mapped by reducing chroma only; contrast is measured with WCAG 2.x on the final rounded hex.
1. **Reject early.** Invalid hex; chroma below 0.04 (grey: it would not read as actionable); within 0.10 OKLab distance of Crimson (reads as an error).
2. **Light primary.** Keep the colour if every primary-dependent pair passes. Otherwise lower L in 0.005 steps (hue and chroma kept) until all pass. In light the fill, the link text and the white label share one colour, so the bar is: link on Panel, Chalk, raised, hover and selected rows at 4.5:1; secondary label on its 8% and 14% tints at 4.5:1; white label on fill, hover and pressed at 4.5:1; visited link 4.5:1; focus ring 3:1.
3. **Reject if it moved too far.** More than 0.20 L of darkening means it is not the tenant's colour any more: "too light". Less than 1.5:1 against body text: "too dark, looks like text".
4. **Dark primary.** Start at L = max(input L, 0.72), chroma x 0.65, hue kept (v1 maps Cobalt #2443D0 to #86A0FF the same way); raise L in 0.005 steps until every dark pair passes, with the label Carbon deep #0E1117 (white if Carbon cannot reach 4.5). Reject if the result is within 0.10 of dark Crimson or under 0.08 from the dark text colour.
5. **Accent.** If given: reject grey and near-Crimson; darken (light, at most 0.25 L) until 3:1 on Chalk, Panel and raised; lighten in dark likewise; reject if within 0.12 of the primary in either theme. If not given: Coral stays unless it is within 0.12 of the tenant primary, then the accent falls back to the text colour (reported).
6. **Everything else** (hover, pressed, selected, visited, tints, labels) comes from the same formulas as the Orrery base (`tools/themelib.py`), so a tenant gets exactly the states of section 3 of `11-v1.1-additions.md`.
7. **Verify.** All 100 pairs per theme are recomputed from the final hex; any failure rejects (it would be a bug). Warnings, not rejections: closeness to Jade or Ochre (pills always carry icon and label).
Guarantee: for an accepted colour every listed pair passes AA in both themes. Tested on 300 pseudo-random colours: 118 accepted, 0 violations.

| Input | Result (run of the script) |
|---|---|
| #2443D0 Cobalt | Accepted, light unchanged, dark #7CA0FD (v1 dark Cobalt is #86A0FF) |
| #0F766E teal | Accepted. Light #006E67 (darkened 0.026 L), dark #7CB0AA. Warning: close to Jade |
| #9333EA purple | Accepted. Light #8923DE, dark #B988F9 |
| #FFD400 yellow, #F59E0B amber, #7DB6FF sky | Rejected, too light: AA would need 0.39, 0.27, 0.27 L of darkening (would become #756000, #8B5700, #2E64A7) |
| #14B8A6 teal-500 | Rejected, too light: needs 0.22 L, limit 0.20 |
| #6B7280, #808080, #0B1020 | Rejected, near-grey or near-black (chroma under 0.04) |
| #1A1040 | Rejected, too dark: 1.04:1 against body text |
| #C21F3A, #D32F2F, #E53935, #BE185D | Rejected, near Crimson (0.000, 0.047, 0.086, 0.053) |
| #E0552C Coral | Rejected: darkened to AA it becomes #B43200, near Crimson |

Decisions for the founders: the 0.20 limit rejects common mid-tones such as teal-500; raising it to 0.25 admits them with a visible shift. Red brands are rejected outright; allowing them needs a separate rule so the destructive button stays distinct. A "light brand colour with dark label" mode (link colour separate from fill) would admit yellow and amber but adds a second primary token.

## 4. Logo requirements
| Item | Rule |
|---|---|
| Formats | PNG, JPG, SVG only. No PDF, GIF, WebP, animated files |
| Size | SVG up to 200 KB, PNG or JPG up to 2 MB; raster at least 512 px on the short side; 4096 px maximum |
| Variants | Light-background and dark-background logos, or one logo with auto-derived variants. A square mark is optional and recommended |
| Auto-derived | **Mono** (single colour from the alpha channel or SVG fills, in text colour) and **reversed** (white). Needs transparency or vector fills; an opaque JPG cannot be derived and asks for variants. If a logo's median colour is under 3:1 against a theme's Panel, the system substitutes the derived variant for that theme and shows it in the preview |
| Sizes in product | Sidebar height 32 px, max width 160 px; login 48 px; collapsed rail uses the mark at 24 px; never below 16 px high |
| Clear space | 25% of the logo height on every side |
| Never | Stretch, recolour freely, add shadows or effects, mirror in RTL |
| Security | Untrusted: type sniffing, size limits, SVG sanitised (scripts, event handlers, external references, `foreignObject`, embedded fonts removed), malware scan, stored per tenant, served from a cookieless asset host, rasterised copies for PDF and email. Owned by SEC |

## 5. Favicon and icon set (generated from the logo)
16, 32 and 48 px in `favicon.ico` (PNG-compressed entries), apple-touch 180, PWA 192 and 512 plus a 512 maskable with the mark inside the 80% safe circle (UNVERIFIED rule), 1024 for stores and emails. From the square mark when supplied; otherwise a monogram (first letter of the display name, Alexandria 600) on the tenant primary with the label colour. App-icon tiles use the primary fill (light). No hand tuning is possible for tenants; sizes under 32 px get a 1 px safe margin and a legibility warning in the preview if the mark has fine detail. The Orrery pipeline for its own icons is `tools/build_icons.py`.

## 6. Documents (invoices, PDFs, emails)
Legal layout beats branding. Precedence, highest first: (1) mandatory fields and Arabic content on Saudi tax invoices; (2) the ZATCA QR code and its clear zone, to the specification (confirm with a compliance advisor, UNVERIFIED here); (3) the tenant logo; (4) tenant colour; (5) Powered by.
| Rule | Value |
|---|---|
| Invoice header logo | 8 to 16 mm high, max 60 mm wide, at the start edge (Arabic on the right, English on the left on bilingual pages); one-colour (mono) option for single-colour printing |
| Colour | Documents always use the light theme. Tenant primary only for rules and headings on white (4.5:1 checked). The tenant accent and Coral are not used on invoices (v1) |
| Overlap | The logo never enters the QR clear zone. If it cannot fit, it shrinks, then drops to the mark, then is omitted; the QR and mandatory fields never move |
| Emails | Logo 40 px high, primary button with its label colour, text in text colour |
| Fonts | Alexandria and Readex Pro unchanged |

## 7. "Powered by Orrery"
Shown by default: sidebar footer (the mark plus "Powered by Orrery" as caption text; mark only when the rail is collapsed), login page footer, and a one-line document footer. The mark is Orrery's, mono (text-muted), never in tenant colours; the name stays Latin, isolated left-to-right in Arabic. It may be removed only when the plan entitlement `branding.removePoweredBy` is on (PLT; plan names are a founder decision), set by an owner or admin, never during a trial. Even then the About dialog, legal pages and Orrery's own emails keep the name. Each toggle is audited.

## 8. Preview before applying
Settings > Branding shows, side by side in light and dark and in English and Arabic: sidebar with logo and display name, primary and secondary button with hover and pressed, a link and a visited link, status pills, a chat message with the avatar, a table row (hover, selected), the login page, the invoice header on white and the email header. It also shows the derived colours, every adjustment ("darkened 0.026 L"), warnings, and the contrast report. **Apply** is disabled when rejected (with the reason and the nearest accepted colour) and creates a new Blueprint `branding` version; **Roll back** restores the previous one. A static sample is `preview-tenant-themes.html` (6 invented tenants and 1 rejected).

## 9. Audit and permissions
Only owner and admin roles may change branding. Audited, with actor, role, time, before and after: colour inputs and derived output with `themeAlgo` and adjustments; asset upload (hash, size, type, scan result, sanitiser changes); asset rejection; display name; Powered-by entitlement changes; apply and roll back. QA (contrast and RTL tests for tenant themes) re-runs `derive_tenant_theme.py` over the saved colours in CI.

## 10. Blueprint `branding` sketch
```json
{"branding": {"version": 3, "displayName": {"en": "Al Nakhla Trading", "ar": "النخلة للتجارة"},
  "primary": "#0F766E", "accent": null, "themeAlgo": 1,
  "logo": {"light": "asset:...", "dark": "asset:...", "mark": "asset:..."}, "favicon": "auto",
  "resolved": {"light": {}, "dark": {}}, "removePoweredBy": false}}
```

## Open
Founder decisions: the light-shift limit (0.20), red brands, light-brand mode, whether chart series 1 follows the tenant, Powered-by plan tiers, login background images. Needs a designer: logo clear space and sizes, monogram style, preview layouts. Needs a compliance advisor: invoice header and QR precedence. Needs a native speaker: all Arabic strings.
