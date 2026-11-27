# Session log: boards-blueprint

Date: 2026-11-27
Author: eldon
Tool and model: claude-code / opus-5.5
Plan IDs: BPL-053

## Summary
Blueprint 0.6.0 adds `modules.projects` under ADR-0079 (Proposed): project, task, timesheet and activity type concepts; company task statuses mapped to engine task statuses; board, timeline, calendar and list view declarations with board columns; timesheets with the billing boundary named. Stacked on bpl-052-crm-blueprint.

## Files touched
- contracts/blueprint.schema.json: 0.6.0; `projectsModule`, `projectsView`; one x-validator-rule.
- contracts/blueprint-modules.md: projects section, metrics, changelog; contracts/README.md: version.
- contracts/examples/blueprint-modules-minimal.json: project, task, timesheet entities, a dashboard and `modules.projects`.
- contracts/examples/invalid/blueprint-modules-projects-cases.json: 14 negative cases.
- services/blueprint/diff/bpdiff/model.py: key-table rows for task statuses, views and board columns (ordered).
- docs/PLAN.md (BPL-053 doing), docs/CHANGELOG.md.

## Checks
- Task statuses (Open, Working, Pending Review, Overdue, Template, Completed, Cancelled), Project, Timesheet and Activity Type read from the pinned ERPNext v15.124.5 source; UNVERIFIED until a bench run. Overdue is engine-derived and not mappable.

## Decisions
- None new; follows ADR-0079.

## Tokens or cost
Unknown.

## Next step
BPL-054 (manufacturing, 0.7.0) stacked on this branch.
