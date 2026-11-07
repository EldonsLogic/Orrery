# Session log: lane-guard

Date: 2026-11-07
Author: eldon
Tool and model: claude-code
Plan IDs: GOV-025,LEG-004

## Summary
Founder declined a paid GitHub plan and asked for clear guardrails that keep each founder in their own lane. Added a machine-readable lane map and a guard that fails any change touching the other founder's lane unless a waiver line is logged, in CI, the pre-push hook and the end-of-session gate. Added a first task for the partner to list every Frappe or ERPNext app and add-on used locally, because the repo holds only the change-engine module, not the engine installation.

## Files touched
- scripts/lanes.json (new): founders and lane paths; scripts/check_lanes.py (new).
- .github/workflows/ci.yml, scripts/check_pre_push.py, scripts/finish_session.py: run the lane guard.
- docs/decisions/ADR-0020 and INDEX; docs/RULES.md; AGENTS.md; docs/ONBOARDING.md (waiver line, partner add-on listing task).
- docs/PLAN.md: GOV-025 done; LEG-004 wording.

## Decisions
- ADR-0020 lane guard. Tested on past commits: Eldon editing the engine lane fails, the partner editing the engine lane passes, the partner editing the design-system lane fails, bots are skipped.
- Branch protection stays unavailable without a paid plan; making the repo public would unlock it for free but exposes strategy, research, security and legal docs, so it is not recommended.

## Tokens or cost
Unknown.

## Next step
Partner: list the engine add-ons (LEG-004), then CE-SEC-003. Both: run `pre-commit install` (GOV-010).
