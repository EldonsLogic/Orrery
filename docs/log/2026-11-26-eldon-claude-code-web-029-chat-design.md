# Session log: web-029-chat-design

Date: 2026-11-26
Author: eldon
Tool and model: claude-code (Claude Opus 5.5)
Plan IDs: WEB-029

## Summary
WEB-029 part 3: the chat screen design pass, plus every open note from the home review fixed in the shell (stacked on web-029-home-design, #367).

## Files touched
- web/app/src/components/chat/: one calm column (45rem measure); Seshna turns at full width with the mark and name, the person's turns as a quiet pill at the end side; answers cite their source records as chips that open each record; figures in tabular numbers; confirm-before-write as a drafted proposal card (StatusMark, before and after table, Confirm / Edit / Cancel); pending approvals as a drafted proposal card that links to the inbox (no approve in the chat, ADR-0044); thinking state with the loading mark (static under reduced motion); a quiet "What Seshna did" disclosure; clarifications as a Seshna turn; errors and refusals in plain words; empty state with suggested prompts; composer docked at the bottom in glass with mode, send and stop inside, page scrolls to the newest turn.
- web/app/src/chat/: `sources` event (allow-listed: entity and record id patterns, at most 10, duplicates dropped) attached to the matching Seshna message; `sourceHref`; the fixture streams a few words at a time, answers in the language asked and cites three sales orders.
- web/app/src/components/shell/: phones hide the language switch (it is in the account menu) so the company name has the room; tablets (768 to 1023) get an icon rail with hover tooltips (hidden from assistive technology), expanded by a toggle or keyboard focus, solid when expanded; the drawer is now phones only (below 768); the phone dock clears content exactly (its height plus the safe area) and hides with the on-screen keyboard or while the inline Ask field is in view (IntersectionObserver, InlineAskContext); the side navigation glass takes the page band's flat tint.
- web/app/src/ui/Icon.tsx: one Icon component (Lucide placeholders, stroke 1.5, 16 in buttons, 20 in navigation); every lucide import goes through it.
- web/app/src/lib/: dock.ts (dock visibility, keyboard detection), useMedia.ts, viewport.ts (rail range).
- web/app/src/components/home/: the Ask field uses a short placeholder on phones and reports when it is in view; tablet breakpoint aligned to 48rem.
- docs/brand/tools/build_tokens_css.py and the regenerated docs/brand/tokens/tokens.css: type sizes and line heights in rem on a 16 px root; foundation KPI roles in rem.
- web/app/messages/{en,ar}.json: chat, rail and placeholder strings; the assistant is named Seshna.
- web/scripts/check-contrast.mjs and its test: the old chat bubble pairs replaced by the user turn and the rail tooltip.
- docs/open-questions.md: Q-629 (approve in the chat versus ADR-0044).

## Decisions
- Approve / Edit / Reject from the brief is mapped to Confirm / Edit / Cancel on the confirm card; approvals stay in the inbox (ADR-0044 item 2, WEB-004 tests). Open as Q-629.
- Edit declines the draft (fail closed) and returns focus to the composer; there is no edit API.
- Tooltips on the rail use CSS alt text (`content: attr(data-label) / ''`) so names are not read twice.

## Checks
pnpm lint, typecheck, test (vitest and node), next build (tsconfig rewrites reverted), check_docs, check_repo_hygiene. Screenshots at 375/768/1024/1440, EN and AR, light and dark, home and chat (empty and a three-turn conversation), plus the tablet rail hover and expanded, outside the repo; three review rounds; no horizontal overflow anywhere.

## Tokens or cost
Not measured.

## Next step
WEB-029 follow-ups: the AG-UI mapper (WEB-026) must emit `sources` from the server for real answers; prefill the chat composer from the home Ask field; BRD: Seshna icon set from the Nuqta S geometry (swap in ui/Icon.tsx).
