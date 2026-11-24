# Session log: gov-070-rename-seshna

Date: 2026-11-23
Author: eldon
Tool and model: claude-code
Plan IDs: GOV-070

## Summary
Renamed Orrery to Seshna in services (except gateway and provisioning), scripts and the product, legal, gtm and runbooks docs; all affected test suites pass.
Other matches are owned elsewhere: docs/brand by BRD-014; AGENTS.md, README, RULES, START-HERE, ONBOARDING and agents/ by GOV-069 (#296).

## Files touched
- services/blueprint, control-plane, datasets, discovery, operate: hash domain strings, dataset name, module-name prefixes
- scripts/check_lanes.py, scripts/check_pre_push.py: env vars ORRERY_* renamed to SESHNA_*
- docs/product/PRD.md, docs/legal/checklist.md, docs/gtm, docs/runbooks: prose; name status text updated to final name (ADR-0066)

## Decisions
- ADR-0066 (final name Seshna), written in parallel by another agent.

## Tokens or cost
Small.

## Next step
GOV-071: partner renames the matches in apps/engine, infra, services/gateway.
