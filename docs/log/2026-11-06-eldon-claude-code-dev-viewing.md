# Session log: dev-viewing

Date: 2026-11-06
Author: eldon
Tool and model: claude-code
Plan IDs: INF-012,INF-013,WEB-018,WEB-019,DAT-009,QA-017

## Summary
Recorded the founder request (relayed from a side session) that the developing product is always viewable: a Proposed decision record, early plan rows, a concise agent rule, and the hosting rules updated for dev hosts. Planning only; nothing is deployed and nothing runnable exists yet.

## Files touched
- docs/decisions/ADR-0018 and INDEX: Vercel per-PR previews for the web app, one shared dev server for the engine and services, no Supabase for now, synthetic data only, engine invisible on previews, agent stops and asks for missing accounts or keys.
- docs/PLAN.md: INF-012 dev server and access, INF-013 Vercel project with per-PR previews, WEB-018 web stack decision, WEB-019 host design-system previews, DAT-009 synthetic data generator, QA-017 preview smoke check.
- AGENTS.md and docs/RULES.md (rules 45 and 46): keep progress viewable; PRs say how to view; ask founders for missing pieces.
- docs/security/hosting-rules.md, infra/README.md, docs/architecture/overview.md: dev hosts outside the country allowed for synthetic data only.

## Decisions
- ADR-0018 is Proposed until the partner reviews (GOV-013). Founders create the accounts and projects.

## Tokens or cost
Unknown.

## Next step
Founders: create the Vercel project and choose the dev host (INF-012, INF-013). WEB-018: decide the web stack. Then host the design-system previews (WEB-019).
