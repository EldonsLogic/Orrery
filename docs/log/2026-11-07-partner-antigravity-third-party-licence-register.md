# Session log: third-party-licence-register

Date: 2026-11-07
Author: partner
Tool and model: antigravity / gemini-3.8-flash
Plan IDs: LEG-004

## Summary
Recorded the partner's verified local bench installation (Frappe Framework 15.126.0 MIT, ERPNext 15.124.5 GPL-3.0, change engine module 0.1.0, MariaDB 10.6, Redis 7) into the third-party licence register and NOTICE.md, completing LEG-004.

## Files touched
- docs/legal/licence-register.md (new): third-party licence register documenting component sources, versions, licences, and SaaS architecture boundaries.
- NOTICE.md: updated to link to the full licence register and display exact pinned versions.
- docs/legal/checklist.md: marked item 5 (licence register) done.
- docs/PLAN.md: marked LEG-004 done.
- docs/STATUS.md: regenerated status.

## Decisions
- Established Frappe Framework 15.126.0 and ERPNext 15.124.5 as the pinned baseline version set for the ERP-001 runtime spike.

## Tokens or cost
Standard session tokens.

## Next step
CE-SEC-003: persist runtime policies per site with revision and audit, behind an admin permission, and add tests (apps/engine/change_engine).
