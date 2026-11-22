# Session log: gov-064-apply-approval-rules

Date: 2026-11-22
Author: eldon
Tool and model: claude-code (Sonnet 5.5)
Plan IDs: GOV-064

## Summary
Applied Eldon's Q-41, Q-42, Q-43 answers to the action-policy table and RULES 21 to 23, and flipped the generated proposed token set to ACCEPTED (Q-70). The web apps now copy and load it after tokens.css.

## Files touched
- docs/security/action-policy-table.md: Q-41/Q-42/Q-43 rules stated, proposal wording dropped, R4 has no self-approval (onboarding needs a second eligible person)
- docs/RULES.md: rules 21 to 23 aligned to ADR-0027
- docs/brand/tools/build_proposed_tokens.py and regenerated docs/brand/tokens/tokens.proposed.json and .css: status ACCEPTED (Q-70)
- web/scripts/copy-tokens.mjs, check-tokens-only.mjs (+ test), web/app layout.tsx and global-error.tsx, web/marketing layout.tsx, .gitignore, web/README.md: copy and import tokens.proposed.generated.css after tokens.generated.css
- docs/brand/README.md, docs/brand/10-open-items.md, services/blueprint/tokens/__init__.py: token set wording PROPOSED to ACCEPTED
- docs/PLAN.md: GOV-064 done

## Decisions
- Q-41, Q-42, Q-43, Q-70 applied as answered; ADR-0027 is the source.

## Tokens or cost
Not measured; one Sonnet session with two short follow-ups (web wiring, review fixes).

## Next step
None for GOV-064. Checks run: web lint, typecheck, test, node --test scripts; services/blueprint tokens tests; brand tools.

Review fixes (PR #268): break-glass list marked Proposed again; sole-owner rule reworded (role holding, not availability); RULES 21 and 23 wording; Q-563 added for Q-41 with Q-42; agent-least-privilege Q-42 references updated.
- Q-563 answered by Eldon in chat (2026-11-22): the sole-owner fallback covers the owner's own agent drafts, R1-R3 only; recorded in the table and open-questions.
