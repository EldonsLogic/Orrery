# Session log: leg-006-ip-boundary-and-agpl

Date: 2026-11-27
Author: eldon
Tool and model: claude-code / opus-5.5 (worker subagent for Eldon's orchestrator session)
Plan IDs: GOV-079,QA-022,QA-023,QA-024

## Summary
Turned the partner's (sayegh9) four GPL points of 2026-11-27 into standing rules: ADR-0080 (Proposed), the AGPL forbidden list in the licence register, and the browser-asset and distribution rules in engine-adapter.md "Licence boundary". Docs only; the CI checks are new todo rows. LEG-006 could not be claimed (it depends on LEG-003, still doing), so GOV-079 carries this work.

## Files touched
- docs/decisions/ADR-0080-ip-boundary-business-logic-outside-the-engine.md: new ADR, Proposed, partner pending.
- docs/decisions/INDEX.md: ADR-0080 row.
- docs/legal/licence-register.md: section 2 lists the ten AGPL apps with SPDX, source and access date; section 4 adds the rule to re-check licences at every engine bump.
- docs/architecture/engine-adapter.md: "Licence boundary" adds ADR-0080, no engine assets in the browser (PDFs are output), and the handovers that count as distribution.
- NOTICE.md: one row for the forbidden Frappe AGPL apps, following the existing lavaloon row.
- docs/PLAN.md: GOV-079 (eldon, doing), QA-022 (eldon, todo), QA-023 and QA-024 (partner, todo).

## Checks and evidence
- ADR number: 0080 is unused in `docs/decisions/` on main and on all 302 remote branches (0074 to 0079 taken). Plan ids GOV-079 and QA-022 to QA-024 are unused on all remote branches.
- Licences re-read with `gh api repos/<owner>/<repo>/license` on 2026-11-27: frappe/crm, helpdesk, insights, gameplan, lms, drive, print_designer, books, press and lavaloon-eg/ksa_compliance all return AGPL-3.0. ERPNext and HRMS still return GPL-3.0. Nothing UNVERIFIED.
- `git grep` 2026-11-27: `erpnext` and `hrms` imports under `apps/engine/` appear only in `tests/` and `proofs/`. Under `services/`, the only hit is a test string in `services/blueprint/tests/factory/test_analysis.py`, not an import. QA-022 must not flag it.

## Decisions
- ADR-0080 (Proposed): rigid-zone and country business logic lives in our own services outside the engine process; amends ADR-0076 for CMP-048 and CMP-049.

## Tokens or cost
Unknown.

## Next step
- Partner reviews ADR-0080 on the PR.
- QA-022 (eldon) builds the services import check.
- QA-023 and QA-024 (partner) build the gateway asset-route check and the apps/engine import check.
- ADR-0074 and ADR-0076 links resolve once their PRs merge.
