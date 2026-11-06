# Session log: agent-ready-repo

Date: 2026-11-06
Author: eldon
Tool and model: claude-code
Plan IDs: GOV-021,GOV-008,GOV-012

## Summary
Made the repo ready for any agent to open cold: complete standing-rules file, delegation playbook with model-by-tier routing and a starter prompt, a status page that lists what is built and what is ready to start, a rewritten start page with the ordered path by gate, and a decision record for the operating rules. Plan statuses were corrected to match what exists.

## Files touched
- docs/RULES.md (new): every standing founder rule in one place, with pointers to decisions.
- agents/delegation-playbook.md (new), agents/model-registry.md, agents/README.md: delegation procedure, Claude 5.x models by tier, starter prompt.
- AGENTS.md: reads RULES.md at session start, push-and-PR at session end, ask when unclear.
- docs/00-START-HERE.md, README.md, docs/architecture/overview.md: what exists today, the path in order, settled cross-cutting decisions, built versus planned.
- scripts/build_status.py, scripts/check_docs.py, scripts/check_repo_hygiene.py: status shows built items and ready-to-start rows; new required files; RULES.md allowed.
- docs/PLAN.md: statuses corrected (done: first green CI, Blueprint and manifest schemas, branding schema, connector spec, tenancy ADR; doing: fixture, guardrail and asset tooling, branch protection).
- docs/decisions/ADR-0017 and INDEX.

## Decisions
- ADR-0017 operating rules for two founders and their agents (extends ADR-0009).
- Merges of the open pull request were blocked by the tool's auto-mode safety check (merge without review). Founders merge, or give explicit permission, per standing rule 10.

## Tokens or cost
Unknown.

## Next step
GOV-008 branch protection and GOV-009 partner access (owner action on GitHub), GOV-012 model registry for Codex and Antigravity (partner), GOV-013 partner reviews ADR-0001..0017, then the G1 spine tasks listed in docs/00-START-HERE.md.
