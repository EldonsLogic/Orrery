# ADR-0001: Working codename Orrery, not cleared

Status: Accepted
Owner: eldon
Approved by: Eldon; partner review pending (GOV-013)

## Context
We need a name to label the repo and docs now. No trademark search has been done. The final name may differ, and Arabic spelling is open (Q-4 in [../open-questions.md](../open-questions.md)).

## Decision
Use "Orrery" as a working codename only. It is not cleared. In prose write "the platform" or "Orrery (working name)". Product name, domain, logo and legal entity wait for name clearance (LEG-008) and the identity decision (BRD-003). Renaming must be a one-edit job: the name lives in a few known places (README, AGENTS.md, brand tokens, package names) and nowhere else is hard-coded.

## Alternatives rejected
- Pick a final name now: risks a rebrand after a trademark conflict.
- Use a placeholder like "project-x": loses the team's shared language.

## Consequences
- Docs avoid hard-coding the name; a rename script can be added when needed.
- Logo is a placeholder (ADR-0011).
- Do not use "ERPNext" or "Frappe" in any product name or ad (trademark policy, LEG-009).

## Supersedes
none
