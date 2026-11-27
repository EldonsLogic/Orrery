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

## Review fixes (#396 RULES 42 review at 87629de1)
- Merged bpl-052-crm-blueprint (its #395 fixes) into this branch first.
- M1: rigid-zone field rule. A pure schema rule is not possible (entities do not say which module concept binds them), so the terms live in the schema (root `x-rigid-zone-terms`, shared with the contract guard) and the new validator rule `BP-MOD-001` (services/blueprint/validator/rules_modules.py) refuses a rigid-zone field id (billing_rate, costing_rate, amount and the like) on any module-bound entity and a money field on the bound timesheet or activity_type; tests in services/blueprint/tests/test_modules.py.
- M2: `timesheets.billable: true` needs `enabled: true` and `invoicingComponent` (schema); `BP-MOD-003` checks it is listed and rigid; negative cases `projects-billable-while-disabled`, `projects-billable-without-invoicing-component`.
- L3: `projects-calendar-with-board` uses a valid column id and `projects-unknown-view-kind` expects `/kind`; both now match their path exactly (`exact: true`), checked by deleting each clause.
- L4: timeline and calendar date-field rule is in the validator (`BP-MOD-002`); Q-700 updated.
- L5: module role changes are `access` (from #395).
