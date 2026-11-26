# Session log: web-029-onboarding-design

Date: 2026-11-26
Author: eldon
Tool and model: claude-code (Claude Opus 5.5)
Plan IDs: WEB-029

## Summary
Design pass on onboarding, the Business blueprint review and the staff console, plus two fixes from #376 (styled logo upload, single "Primary colour" label). Stacked on `web-029-records-design` (#376). Behaviour, ports and existing tests kept; foundation roles only.

## Files touched
- web/app/src/components/onboarding/: journey (ProgressMarks, Discover current) on the page band, step list beside one card per step, segment meter, mark bullets, "Nothing goes live without your approval" line.
- web/app/src/components/blueprint/ (BlueprintView, new Proposal.tsx, CSS): proposal layout: cover with key figures, numbered sections, modules as cards with StatusMark, flagged gaps, draft price tables, sticky decision card (Approve after three confirmations, Ask for changes opens the chat), contents list. Owner view only; the department view is unchanged in content.
- web/app/src/blueprint/proposal.ts and fixture/proposal.ts: pure view-model (labels never fall back to ids, price shown as the quote's decimal strings, hidden when a figure is malformed) and synthetic data.
- web/app/src/components/console/: staff realm strip on every console page (denied too), top bar, side navigation with current page, page heads, compact filter toolbar, hidden table captions.
- web/app/src/components/settings/branding/: styled translated logo file button with file name; hex field label visually hidden.
- web/app/src/ui/: `labelHidden` on TextField/Field; Table wrapper positioned so a hidden caption no longer widens the page (fixed horizontal overflow on console phones); link buttons not underlined.
- web/app/messages/{en,ar}.json: new strings; "UNVERIFIED" badge now sentence case; the assistant "other action" line no longer prints a tool name.
- web/scripts/check-contrast.mjs: onboarding opacity pair replaced by the staff realm strip pair.
- docs/open-questions.md: Q-683.

## Checks
- pnpm lint, tsc --noEmit, vitest 441 pass, node tests 136 pass, next build ok (tsconfig rewrite reverted).
- Screenshots outside the repo at 375/768/1024/1440, en/ar, light/dark; three rounds (sticky rail, toc order, legend notch, picker alignment, console overflow fixed); no horizontal overflow.

## Decisions
- None needing an ADR. Approve is not wired (Q-683, WEB-027, Q-544).

## Next step
WEB-027 wires the decision to the DSC-009 review view; ProgressMarks labels are tight at 375 in Arabic (shared component, follow-up).

## Addendum: journey marks (Eldon decision 2026-11-26)
- ProgressMarks now fills the Nuqta S up across the five steps (outline, upper tint, upper solid, upper solid plus lower tint, both solid), fixed per step; steps after the current one are muted; labels wrap at 375 in Arabic. Mark gained a `tint` fill (solid at 40% fill opacity). docs/brand/09-applications.md updated. lint, tsc, vitest and next build pass.
