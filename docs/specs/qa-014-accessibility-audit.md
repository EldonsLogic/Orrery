# QA-014: Accessibility audit (WCAG 2.2 AA), web/app

Status: draft
Owner: eldon
Method: static review of `web/app/src` (ui library, shell, auth, chat, records, blueprint, factory, console). Base token contrast computed by hand (light: text on background 16.6, primary on surface 7.5, danger 5.9, warning 5.6, success 5.4; secondary text now 70% mix). No screen reader, no browser, no axe run: no a11y test dependency is installed (only vitest), and none was added.
Result: 12 findings (0 critical, 3 high, 5 medium, 4 low). 6 fixed in this change, 6 open.

| ID | WCAG | Where | Severity | Finding | Status / fix |
|---|---|---|---|---|---|
| A-01 | 1.4.3 | `components/chat/Chat.module.css:11-45` | High | Eleven CSS variables used here do not exist in the generated tokens (`--color-primary-label`, `--color-text-muted`, `--color-border`, `--color-border-control`, `--color-surface-raised`, `--color-disabled-*`, `--border-width`). The user bubble fell back to dark text on the primary blue (about 2.4:1), borders vanished, textarea border missing. The token lint does not catch undefined variables. | Fixed: mapped to existing tokens (`--color-background` on primary, `color-mix` of `--color-text`). Open: add a lint for undefined `var(--x)` (follow-up). |
| A-02 | 3.3.1, 4.1.3 | `ui/Field.tsx:~46`, `ui/Checkbox.tsx:~35` | High | Field error text was linked by `aria-describedby` but never announced when it appeared. | Fixed: `role="alert"` on the error node. |
| A-03 | 2.1.2, 2.4.3, 4.1.2 | `components/records/ConfirmWrite.tsx:49` | High | `role="dialog" aria-modal` with no focus move, no Escape, no focus containment, focus not restored. | Fixed: focus first button on open, Escape cancels (not while busy), Tab wraps, focus restored on close. Background content is still not `inert` (see A-09). |
| A-04 | 1.4.3 | `ui/control.module.css` (placeholder) | Medium | Placeholder at 55% text colour is about 4.0:1 on the surface, below 4.5. | Fixed: 70%. |
| A-05 | 4.1.3 | `components/chat/Messages.tsx:15` | Medium | Live log re-announces on every streamed token (`aria-relevant="additions text"`). | Fixed: `aria-busy` while any message streams, so the final text is read once. Verify with VoiceOver/NVDA. |
| A-06 | 2.4.2 | `app/layout.tsx:11` | Medium | One static `<title>` for every route (login, chat, records, console). | Open: per-page `metadata` (needs per-route i18n title keys). |
| A-07 | 2.4.3, 3.2.2 | `components/chat/Composer.tsx:41,58` | Medium | Textarea and mode select are `disabled` while a run streams, so focus drops to `<body>` and is not returned when the run ends. `chat.test.tsx:53` pins `disabled`. | Open: use `readOnly`/`aria-disabled` and update that test, or refocus the textarea on run end. |
| A-08 | 4.1.3 | `components/chat/Cards.tsx:13`, `ChatScreen.tsx:42` | Medium | Confirm and clarify cards appear after the user acts elsewhere with no announcement or focus move; a keyboard or screen-reader user may not find the pending confirmation. | Open: `role="alertdialog"` or move focus to the card heading on appear. |
| A-09 | 2.4.11, 4.1.2 | `ConfirmWrite.tsx`, `shell/AppShell.tsx:92` | Low | Modal and open drawer do not make the rest of the page `inert`; drawer has no focus containment or outside-click close (Escape works). Fixed header could overlap focus only if sticky, which it is not. | Open. |
| A-10 | 1.3.1, 2.4.7 | `blueprint/FlowDiagram.tsx:40` | Low | Focusable `role="group"` scroll container with the SVG `aria-hidden`; the text equivalent is the step list in `BlueprintView`. Acceptable, but name should say it is a visual diagram. | Open (label text only). |
| A-11 | 3.1.2 | chat bubbles, tables | Low | `dir="auto"`/`<bdi>` handle direction, but `lang` is not set on embedded text of the other language (screen readers mispronounce). Root `lang` and `dir` are correct and follow the locale (`Providers.tsx`, `layout.tsx`). | Open. |
| A-12 | 1.4.3 | `Shell.module.css .navHeading` | Low | 12px headings at `opacity: .75`: about 8:1 on surface in light, fine; dark theme not computed. | Not verified in dark. |

## Passed (static)
- Skip link to `#main`, one `<main>` per shell, `nav` labelled, `aria-current` on the active link, drawer `aria-expanded`/`aria-controls`.
- Focus ring on all controls (2px token ring, offset 2px); touch targets use `--touch-target` 44px (2.5.8 met) for buttons, inputs, nav links, date picker.
- Reduced motion: spinner animation disabled; other transitions are 150ms colour-only.
- Labels: every input has a visible `<label for>`; tables have captions and `scope`; alerts use `alert`/`status` by tone; spinner buttons set `aria-busy`.
- Colour is never the only signal (badges and alerts carry text).

## Not verified
Screen readers (VoiceOver, NVDA, TalkBack), real-browser keyboard pass, zoom/reflow at 320px and 400%, dark-theme contrast of every pair, marketing site (`web/marketing` not reviewed), `ui/DatePicker` grid semantics, Arabic text rendering. Recommended follow-up: an axe run in CI once an a11y test dependency is approved.
