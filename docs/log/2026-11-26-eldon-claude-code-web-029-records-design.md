# Session log: web-029-records-design

Date: 2026-11-26
Author: eldon
Tool and model: claude-code (Claude Opus 5.5)
Plan IDs: WEB-029

## Summary
WEB-029 part 4: design pass on the records list, record detail, import and export, and Settings > Branding, stacked on #373. Behaviour, ports and the WEB-023/024/007 tests kept; foundation roles only.

## Files touched
- `web/app/src/components/records/RecordList.tsx`, `Cells.tsx`, `StatusBadge.tsx`, `Records.module.css`: list with header actions, search and compact filters, a sticky-header table (40 px rows, tabular grouped figures, muted currency, status word plus icon, whole-row link, aria-sort), intermediate totals hidden below 64rem, phone cards, empty and loading states, range and pager (25 a page).
- `web/app/src/components/records/RecordForm.tsx`: detail header (back link, number, status, actions group), details card (read-only values as text), line items with totals block aligned to the amount column, phone line cards, activity timeline.
- `web/app/src/records/detailModel.ts` (+ `detail.test.ts`): pure models for child-table lines, totals split, history, and digit grouping on decimal strings (no float maths).
- `web/app/src/components/records/ImportWizard.tsx`, `ExportDialog.tsx`, `ConfirmWrite.tsx`: numbered stepper, drop zone (drag and drop plus file button), mapping rows, titled validation alerts, export facts; risk shown in words, never the internal code.
- `web/app/src/components/settings/SettingsLayout.tsx` (+ css), `settings/branding/*`: two-column settings with section nav, stacked setting rows, sticky live preview of both themes, contrast tables folded under their summaries.
- `web/app/src/ui/Table.*`, `ui/Icon.tsx`: sticky header, row hover, aria-sort, column class; new glyphs through the one Icon component.
- `web/app/src/records/fixture/*`, `records/types.ts`: synthetic sales order line items (child table `sales_order_item`) and history; child entities get no record pages.
- `web/app/messages/{en,ar}.json`: new strings; import step names without digits (one digit system).
- `docs/open-questions.md`: Q-682.

## Decisions
- None needing an ADR. Q-682 asks where record history and child rows come from once the gateway exists.

## Checks
- `pnpm lint`, `pnpm typecheck`, `pnpm test` (422 vitest, 136 node), `next build` (tsconfig rewrite reverted).
- Screenshots of the five screens at 375/768/1024/1440, en/ar, light/dark, outside the repo; three review rounds; no horizontal overflow.

## Tokens or cost
Unknown.

## Next step
- Native file input text ("Choose File") follows the browser language, not the app's: style the logo input like the import drop zone (WEB-029 follow-up).
- Branding: the setting title and the field label repeat ("Primary colour"); a visually hidden label option on TextField would remove it.
- PLT-009 / WEB-026: serve history and child rows from the gateway (Q-682).
