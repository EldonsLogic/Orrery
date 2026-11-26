# Session log: web-029-home-design

Date: 2026-11-26
Author: eldon
Tool and model: claude-code (Claude Opus 5.5)
Plan IDs: WEB-029

## Summary
First design pass, part 2 of 2: the owner home as the reference screen, on the WEB-029 foundation (stacked on branch web-029-design-foundation).

## Files touched
- web/app/src/home/: view-model types, synthetic fixtures (a live trading company and one in its simulated month) and a home port; the fixture port denies money and approvals by default (owner and accountant only), as the server will.
- web/app/src/components/home/: HomeScreen and its styles (greeting with company and date, live or simulation status, Ask Seshna entry in glass with suggested questions, today strip or the ProgressMarks journey, four KPI tiles with tabular figures, currency code and a word beside every change, approvals list with StatusMark and Review, activity grouped by day, record shortcuts); tests.
- web/app/src/components/shell/HomeView.tsx: loads the overview through the port; keeps the empty state for roles that open nothing.
- web/app/src/lib/session.ts: the default fixture workspace (Sample Trading Co) is now the owner, so the preview shows the owner's home.
- web/app/messages/{en,ar}.json: home strings.

## Decisions
- One digit system per view: Western digits in both languages for figures, dates and times (24-hour).
- KPI tiles: 4, 2, then a horizontal snap row on phones (container queries), so the page never scrolls sideways.
- The Ask Seshna field takes the owner to the chat; the question is not put in the URL. Prefilling the chat composer is a follow-up.

## Checks
pnpm lint, typecheck, test, next build, check_docs, check_repo_hygiene: pass. Screenshots at 375/768/1024/1440, EN and AR, light and dark, outside the repo; no horizontal overflow at any width.

## Round 2 (review feedback, same session)
- Ask Seshna is a slim hero on a flat Cobalt-tinted band: label with the Coral mark, a 48 px glass field with the Ask button inside at the end, chips, a caption.
- KPI tiles: sparkline (six month-ends, no axes, low emphasis) on sales and cash only; each change in a success or danger pill with an arrow and a word.
- Today moved beside activity (right column, 5) next to approvals (7); the record chips row is gone (the navigation has them).
- Approvals: whole row is the hover target, amounts in one tabular column, Review as a small secondary button, the drafted mark line in caption size.
- Rhythm: 48 between sections (32 on phones), 24 inside cards, card padding 24 (16 on phones); captions step up to 14 on phones.
- Screenshots: all 16 (375/768/1024/1440 x EN/AR x light/dark) plus the not-live company at 375 and 1440; no horizontal overflow; fonts verified loaded.

## Tokens or cost
Not measured.

## Next step
WEB-029: next screen on the foundation (chat, then records). Wire the home port to the metrics layer when WEB-006 lands.
