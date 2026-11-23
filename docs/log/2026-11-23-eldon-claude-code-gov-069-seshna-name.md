# Session log: gov-069-seshna-name

Date: 2026-11-23
Author: eldon
Tool and model: claude-code (Opus-class subagent, briefed by Eldon's orchestrating session)
Plan IDs: GOV-069,BRD-003

## Summary
Recorded the founders' 2026-11-23 decision: the product's final name is Seshna (seshna.com), Latin letters only, with the Nuqta S mark, a Cairo Bold wordmark and Cairo headings over Readex Pro body. ADR-0066 supersedes the ADR-0001 working-name rule and the logo and heading typeface of ADR-0011. Trademark clearance (LEG-008) and domain registration (LEG-005) are still open.

## Files touched
- docs/decisions/ADR-0066-final-name-seshna-and-nuqta-s-mark.md: new, Accepted (both founders, recorded by Eldon).
- docs/decisions/INDEX.md: ADR-0066 row.
- AGENTS.md, CLAUDE.md, GEMINI.md: product name Seshna; repo keeps `EldonsLogic/Orrery` until GOV-002.
- docs/RULES.md: rules 37 (name) and 38 (mark, typefaces) rewritten; rule 52 note that Seshna was published by founder choice.
- docs/00-START-HERE.md, README.md, docs/ONBOARDING.md: Seshna as the product name; the repo URL keeps the old name until GOV-002; ONBOARDING names `SESHNA_FOUNDER` (renamed in the parallel GOV-070 PR); README lists all four phase-1 markets (ADR-0024).
- agents/delegation-playbook.md, agents/team-protocol.md: "Orrery repo" to "Seshna repo" in the starter prompts.
- docs/PLAN.md: GOV-069 and BRD-003 done; LEG-005 reworded to seshna.com and @seshna handles; BRD-009 names the Nuqta S kit and Cairo; WEB-028 self-hosts Cairo instead of Alexandria.
- docs/risks.md: R-034 (uncleared trademark, unregistered domain).
- docs/open-questions.md: Q-602 for counsel (registrability in KSA, UAE, Egypt, Qatar, classes 9, 35, 42); Q-4 resolved; Q-3 update.

## Decisions
- [ADR-0066](../decisions/ADR-0066-final-name-seshna-and-nuqta-s-mark.md): final name Seshna and the Nuqta S mark, decided by both founders 2026-11-23. Eldon knowingly waived RULES 52 for this name; the squatting risk is accepted.

## Tokens or cost
Unknown.

## Next step
- LEG-005: register seshna.com and the @seshna handles (founder action).
- LEG-008: counsel clearance, answer Q-602.
- BRD-009: regenerate `docs/brand/` from the Nuqta S kit (other agent's scope); `docs/brand/04-typography.md` still names Alexandria.
- WEB-028: self-host Cairo and Readex Pro.
- GOV-002: rename the repo, organisation and internal identifiers (env vars `SESHNA_FOUNDER` and `SESHNA_ALLOW_MAIN_PUSH` are renamed under GOV-070).
