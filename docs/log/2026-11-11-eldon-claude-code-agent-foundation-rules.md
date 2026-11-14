# Session log: agent-foundation-rules

Date: 2026-11-11
Author: eldon
Tool and model: claude-code / sonnet-5.5
Plan IDs: GOV-033,GOV-034,GOV-035

## Summary
Added the agent working principles, the agent team protocol with 30 role contracts, and the phase exit rule with a check script, so every phase is tested and recorded before the next one counts.

## Files touched
- agents/working-principles.md: four habits from the Karpathy guidelines, restated in our words (reference only, no copied text; upstream shows no licence)
- agents/team-protocol.md, agents/roles.md: the founder-supplied self-improving agent team guide turned into repo rules and 30 role contracts
- scripts/phase_exit_check.py, scripts/tests/, docs/specs/phase-exit-criteria.json, .github/workflows/ci.yml: phase exit check and its CI test job
- AGENTS.md, CLAUDE.md, GEMINI.md, agents/README.md, docs/RULES.md (rules 48 to 50), docs/GATES.md, NOTICE.md, docs/PLAN.md: links, rules, gate text, reference notice, rows GOV-033 to GOV-035

## Decisions
- Founder instruction (2026-11-11): after every phase run tests before the next phase; adopt the Karpathy guidelines and the agent team guide into the foundation. Recorded as rules 48 to 50. Partner review pending (shared files).

## Tokens or cost
Not measured.

## Next step
Stacked PR for GOV-036 and later: phased delivery document with lanes, proposed ADRs, plan rows and the phase to gate map. Evidence items still need their plan rows (phase-exit-criteria.json plan_rows). Verified: script unit tests pass (8). An independent Opus review found gaps in the exit check (gates missing, dry run printed CLOSED, weak reviewer and evidence checks); fixed in a second commit. Not verified: first real exit run, partner review.
