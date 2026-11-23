# Session log: web-027-owner-approval-screen

Date: 2026-11-23
Author: eldon
Tool and model: claude-code (Sonnet-class)
Plan IDs: WEB-027

## Summary
Built the owner approval screen over the DSC-009 view model as a port-based component with fixtures and no live wiring: summary (with item details), price, gaps, test month, Approve / Ask for changes / Reject emitted through `ApprovalPort`. Tokens only, Arabic and English, RTL, untrusted text as plain text, approve blocked where the model says so. Route `/approval/` shows the fixture with a fake port.

## How to view
`corepack enable && pnpm -C web install --frozen-lockfile && pnpm -C web/app dev`, then open `/approval/` (also `/ar` locale switch in the shell; the page uses the fixture in `web/app/src/approval/fixture/` and a fake port, so choosing a decision only shows the success message). Tests: `pnpm -C web test`.

## Files touched
- web/app/src/approval/: types (view model, port), decide.ts (send rules), labels.ts, fixture/ (review.json, variants, fake port)
- web/app/src/components/approval/: OwnerApprovalView, CSS module, approval.test.tsx
- web/app/src/app/(app)/approval/page.tsx: fixture route, no nav link
- web/app/messages/{en,ar}.json: `ownerApproval` namespace (from owner_approval/labels.json and quote labels, plus new keys)
- web/app/README.md, docs/PLAN.md (WEB-027 done), docs/open-questions.md (Q-561)

## Decisions
- None needing an ADR. Screen requires all three confirmations for every decision (Q-526); see Q-561. Not live until Q-544 and Q-505. Arabic unreviewed. Tier 2 proposed.

## Tokens or cost
Approximate, one Sonnet-class session.

## Next step
Q-544 and Q-505 adapters, then wire the port; add step-up prompt and history list (Q-561).
