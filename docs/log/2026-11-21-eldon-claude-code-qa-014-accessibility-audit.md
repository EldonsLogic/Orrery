# Session log: qa-014-accessibility-audit

Date: 2026-11-21
Author: eldon
Tool and model: claude-code / sonnet-5.5
Plan IDs: QA-014

## Summary
WCAG 2.2 AA static audit of web/app: 12 findings (3 high, 5 medium, 4 low), 5 fixed (undefined chat tokens, error announcements, confirm dialog focus, placeholder contrast, aria-busy while streaming); web tests 275 pass, lint and typecheck clean.

## Files touched
- docs/specs/qa-014-accessibility-audit.md
- web/app/src/components/chat/Chat.module.css
- web/app/src/components/chat/Messages.tsx
- web/app/src/components/records/ConfirmWrite.tsx
- web/app/src/ui/Checkbox.tsx
- web/app/src/ui/Field.tsx
- web/app/src/ui/control.module.css
- docs/PLAN.md: row set done

## Decisions
- None, or link to ADR / strategy decision.

## Tokens or cost
Subagent run, approximate cost not tracked.

## Follow-up (same session)
Second pass (sonnet-5.5): new `web/scripts/check-css-vars.mjs` lint (undefined `var(--x)`, wired into `lint`), per-route titles in en and ar (A-06), chat textarea stays focusable while streaming (A-07), confirm and clarify cards announced in a polite live region (A-08), modal and drawer make the page inert (A-09, drawer focus trap left as a design decision), `lang` on single-script chat bubbles and tool names (A-11). Left: A-10 label copy, A-12 dark-theme contrast, focus move on new cards. web: 277 tests pass, lint (eslint, tokens-only, rtl-css, css-vars) and typecheck clean.

## Next step
Open A-06 to A-12 in docs/specs/qa-014-accessibility-audit.md (route titles, textarea focus while streaming, inert background, announcements); add a lint for undefined CSS vars; screen-reader and axe run not done.
