# Session log: leg-006-gpl-review-fixes

Date: 2026-11-27
Author: eldon
Tool and model: claude-code (Claude Opus 5.5, worker subagent)
Plan IDs: LEG-006,LEG-020,LEG-021,QA-026,QA-027,QA-028,QA-029,QA-030

## Summary
Fixed the GPL research note per the partner's CHANGES review of #388 at 75c8de68 (5 High, 4 Medium, 3 Low). Per High 2, the review was split: #388 keeps only the note, and ADR-0074 and the gate change moved to a separate PR (branch `leg-006-gpl-gate-proposal`, base `leg-006-gpl-saas-research`), which merges only on both founders' written acceptance.

## Files touched
- `docs/research/gpl-saas-boundary.md` (on #388): H1 section 2 conditional quoted and carried into rule 4, FAQ #InternalDistribution cited, cloud hosting relabelled INFERENCE; H4 uncertainties (worse written-form outcome, providers, intra-group, database dumps); M7 statutes relabelled unofficial English, RULES 33 noted; M8 UAE Art. 12 opening quoted, effect unresolved; M9 #UnreleasedMods anchor; Lows (two forum posts with the disclaimer, row 6b downgraded, one blocklist plus allowlist licence rule covering pip, npm and containers with AGPL s.13 and MariaDB GPL-2.0, Frappe stated MIT).
- #388 branch: revert commit removes ADR-0074, its INDEX row and the GATES.md edit; main merged in (normal merge, no rewrite).
- Gate PR: `docs/decisions/ADR-0074-gpl-boundary-settled-by-research.md` (Proposed, rewritten per H3 to H5, M6, M7), `docs/GATES.md` G1 line and `docs/specs/phase-exit-criteria.json` G1-5 together, `docs/decisions/INDEX.md`, `docs/PLAN.md` (LEG-006 text and Depends; new LEG-020, LEG-021, QA-026 to QA-030), reconciled wording in `docs/legal/licence-register.md` 4.3, `NOTICE.md`, `docs/architecture/engine-adapter.md` "Licence boundary", R-013 in `docs/risks.md`, counsel-scope Q8 and legal checklist row 4.

## Decisions
- Eldon proposes option B (research replaces counsel for the GPL part, after the fixes). Not effective: needs the partner's written choice of A, B, C or D on the gate PR. ADR-0074 stays Proposed.
- Rules 1 and 9 reuse QA-022, QA-023 and QA-024 from PR #400 (ADR-0080) instead of new rows.

## Checks
- `check_docs`, `check_plan_independence`, `check_repo_hygiene` and `check_lanes` run on both branches; results in the PR bodies.
- Plan ids QA-026 to QA-030, LEG-020 and LEG-021 and ADR number 0074 checked unused on all remote branches (2026-11-27).

## Not checked
- Case-law sources S12 to S17, S24 and S25 were not re-opened. gnu.org refused connections during the re-fetch; the AGPL s.13 text was read from the copy in `frappe/crm` `LICENSE`.
- Conflicts with #400 (engine-adapter.md "Licence boundary", PLAN rows) are likely when both merge.

## Tokens or cost
Unknown.

## Next step
Partner re-reviews #388 and chooses A, B, C or D on the gate PR. Then LEG-020, LEG-021, QA-026, QA-027, QA-030 (eldon) and QA-028, QA-029 (partner).
