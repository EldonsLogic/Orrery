# 09 Applications (PDF p.14; Nuqta S kit)

The mark alone carries the small applications; the lockups carry documents and marketing. All files are generated (`02-logo.md`).

| Application | Specification | Files |
|---|---|---|
| App icon | Cobalt tile (corner radius 14/64), white mark in the small-size cut at 62% of the tile height, centred. Dark: #0E1117 tile, mark #86A0FF | `logo/app-icon.svg`, `logo/app-icon-dark.svg`, `logo/png/app-icon-*.png` |
| Favicon | Mark only, small-size cut, Cobalt on transparent; 16, 32 and 48 px in the ICO, plus SVG | `logo/png/favicon.ico`, `logo/mark-small.svg` |
| Home screen | apple-touch-icon 180 px, full-bleed Cobalt square (iOS masks the corners); PWA 192 and 512 px; maskable 512 px with the mark at 50% so it stays inside the 80% safe circle (UNVERIFIED rule) | `logo/png/apple-touch-icon.png`, `logo/png/app-icon-192.png`, `logo/png/app-icon-512.png`, `logo/png/maskable-512.png` |
| Chat avatar | Mark in Cobalt, 24 px (master) or 20 px (small-size cut) | `logo/mark-primary.svg`, `logo/mark-small.svg` |
| App header, website, email | Horizontal lockup, primary or dark, at least 96 px wide | `logo/lockup-primary.svg`, `logo/lockup-dark.svg` |
| Splash, covers, social | Stacked lockup; the app icon as the social profile picture | `logo/lockup-stacked-*.svg` |
| Running headers and footers | Wordmark alone, at least 64 px wide | `logo/wordmark*.svg` |
| Tax invoices and PDFs | One-colour black lockup or wordmark in the header; Arabic and English at equal size; tabular, Western digits; a clear zone around the ZATCA QR code; no Coral | `logo/mark-mono.svg` (a one-colour lockup is not generated yet, see open items) |
| Marketing moments | All-white horizontal lockup on Cobalt | `logo/lockup-on-cobalt.svg` |
| Slides and email signature | Lockup at the start of the layout, Cairo headings, Readex Pro body text, Cobalt for links only | |

The Latin lockup is used unchanged in Arabic layouts and is never mirrored.

## State marks in the product (BRD-014)

The mark's two halves carry product state (kit "Extending the system", guidelines p.10). Component: `web/app/src/ui/Mark.tsx` renders the halves from the master and small-cut paths (`logo/mark-primary.svg`, `logo/mark-small.svg`); each half is solid or outline, the outline drawn inside the half's own silhouette so both states have the same footprint. Colour is `--seshna-mark` (Cobalt #2443D0, #86A0FF in dark) and, for the one accent bullet, `--seshna-mark-accent` (Coral #E0552C, #FF8A63 in dark), from `tokens.json` `brandMark`. Below 24 px the small-size cut is used.

**Never tenant-coloured** (both founders, 2026-11-24): the state marks are the Seshna logo, so they stay Seshna Cobalt and Coral in tenant-branded workspaces too. Tenant overrides change `--color-primary` and `--color-accent` only; the tenant theme generator refuses to set `--seshna-*` (`12-tenant-theming.md`).

| Use | Rule | Component and where |
|---|---|---|
| Status | Both halves outline = not started; upper solid, lower outline = drafted by the AI; both solid = approved by a person. Always beside its word; status colours always pair with an icon and a word | `StatusMark`: Blueprint viewer header and the draft settings section, component factory request detail, chat approval card |
| Progress | Five marks: Discover, Blueprint, Build, Simulate, Live. The mark fills up across the journey, fixed per step (Eldon, 2026-11-26): Discover outline only; Blueprint outline with the upper half at about 40% opacity; Build upper half solid; Simulate upper solid, lower half at about 40% opacity; Live both halves solid. Progress is shown apart from the fill: steps after the current one are drawn muted, done and current steps at full strength, with a status word (Done, In progress, Not started) and the current label stronger; the connector is solid up to the current step and dashed after it. Mapped from the build state (`contracts/build-states.md`): no state = Discover; `draft` = Blueprint; `owner_approved`, `team_reviewed` = Build; `built_in_sandbox` = Simulate; `simulated` = Live; `live` = all complete. The list follows the reading direction; each mark is never mirrored | `ProgressMarks`: Blueprint viewer header |
| Bullets | A small solid Cobalt mark. Coral (`tone="accent"`) on at most one item per view, always with a text label | `Mark` |
| Loading | See below | `LoadingMark`: app session loading, workspace switch, chat "working", factory list loading |

Every state obeys the misuse rules: never rotated, mirrored (also in RTL), stretched, recoloured outside the palette, split apart or squared at the round ends; no gradients, glows or shadows.

### Loading mark (approved by Eldon, 2026-11-26)
The kit defines no loading animation. Proposal: when the platform is working, the fill cycles outline, then the upper half, then both halves, about 0.8 s per step on a 2.4 s loop with a 150 ms fade. Only fill opacity changes; the halves never rotate, scale or move. It always sits beside a visible text label (`role="status"`).
Under `prefers-reduced-motion: reduce` the animation stops and the mark shows the static drafted state (upper solid, lower outline) with the same label.
Button busy states keep the small generic spinner inside the button; content placeholders keep skeletons.
