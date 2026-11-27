# Blueprint modules

Status: draft
Owner: eldon
Version: 0.8.0

Part of contract 1 ([blueprint.schema.json](blueprint.schema.json), `$defs/modules`). How an engine-core module joins a tenant's Blueprint. Decision: [ADR-0079](../docs/decisions/ADR-0079-engine-core-modules-in-the-blueprint.md) (Proposed); scope: [ADR-0076](../docs/decisions/ADR-0076-phase-1-module-scope.md). Example: [examples/blueprint-modules-minimal.json](examples/blueprint-modules-minimal.json); negative cases: `examples/invalid/blueprint-modules-*-cases.json`, run by `tests/test_blueprint_modules.py`.

## Shape every module follows
- **Opt-in per company.** `modules.<key>` present means the module is on for this company; absent means off. No key, no screens, tools or metrics for it.
- **Component.** `component` names the component that implements the module; it is listed in top-level `components` and its manifest provides `<module>.module`.
- **Entity vocabulary.** `entities` maps each module concept to a Blueprint entity id. Fields, labels and relations stay on the entity as today; the concept tells the compiler and the engine mapping which engine record it is.
- **Workflow vocabulary.** Each module has a fixed-shape state list (pipeline stages, task statuses) mapped onto the engine's own status values. Generic `workflows[]` may still sit on a bound entity for approvals.
- **Role vocabulary.** `roles.manage`, `roles.work`, `roles.view` list the Blueprint role ids that the module's screens treat as managers, workers and viewers. Listing grants nothing: `roles[].permissions` and scope decide everything. A change to a module role list is classed `access` by bpdiff.
- **Report vocabulary.** Reports reference module metrics by id (below). Numbers come from code in the semantic layer; the Blueprint never holds a formula.
- **Rigid zone.** Module settings carry configuration only, and no field on a module-bound entity may match the schema's `x-rigid-zone-terms` (validator `BP-MOD-001`). Posting, valuation, tax and costing stay deterministic engine or certified-component logic, never AI-written (AGENTS.md principle 3).

Engine record names below are internal (ADR-0016): they never appear in anything a customer sees. Every one is UNVERIFIED until a bench run on the pinned set; names were read from the pinned ERPNext v15.124.5 source on 2026-11-27 (https://github.com/frappe/erpnext/tree/v15.124.5).

## Module `crm`
Core CRM records only (ADR-0076 item 5). Never the separate CRM app or its integration settings.

| Concept | Required | Engine record (internal) |
|---|---|---|
| `lead` | no | Lead (`source` links Lead Source, `campaign_name` links Campaign) |
| `opportunity` | yes | Opportunity (`opportunity_from` customer or lead, `sales_stage`, `probability`, `campaign`) |
| `customer` | yes | Customer |
| `contact` | no | Contact |
| `activity` | when `activityTypes` is set | note: CRM Note rows; call, meeting, visit: Event; follow_up: ToDo; email, message: Communication |
| `campaign` | when `campaignLink` is true | Campaign (shared with the marketing module) |

- `pipeline.stages`: in order; at least one `open` (probability strictly between 0 and 100), exactly one `won` (probability 100) and one `lost` (probability 0). Open stages map to Sales Stage records and the opportunity probability; `won` maps to status Converted and `lost` to status Lost with a lost reason. UNVERIFIED: in the pinned engine Converted may be derived from the quotation to order flow rather than settable from a stage (Q-701).
- `leadSources` map to Lead Source records; `lostReasons` to Opportunity Lost Reason records.
- `activityTypes`: `message` is only sent through a messaging connector integration (DSC-022); inbound text is untrusted.

Metrics: `crm.pipeline_value`, `crm.weighted_pipeline_value`, `crm.win_rate`, `crm.stage_conversion`, `crm.leads_by_source`, `crm.lost_by_reason`, `crm.activities_due`

## Module `projects`
Projects and boards over core projects, tasks and timesheets. Board, timeline and calendar are view declarations over the same task records.

| Concept | Required | Engine record (internal) |
|---|---|---|
| `project` | yes | Project (`expected_start_date`, `expected_end_date`, status Open, On hold, Completed, Cancelled) |
| `task` | yes | Task (`project`, `parent_task`, `exp_start_date`, `exp_end_date`, `depends_on` rows, `priority`) |
| `timesheet` | when `timesheets.enabled` | Timesheet with Timesheet Detail rows (submittable) |
| `activity_type` | no | Activity Type |

- `taskStatuses`: the company's own statuses, in order, each mapped to one engine task status: `open` Open, `working` Working, `pending_review` Pending Review, `completed` Completed, `cancelled` Cancelled. At least one `open` and one `completed`. The engine sets Overdue itself from the end date, so it is never mapped; Template is not used. Several company statuses may share one engine status; the compiler keeps the company status in an adapter-owned field on the task (UNVERIFIED until BPL-057).
- `views[]`: `board` (task only; columns in order, each listing statuses; dropping a card sets the column's first status; optional swimlanes), `timeline` (start and end date fields; dependencies from the task's depends-on rows), `calendar` (start and optional end field), `list`. Each view names the roles that see it; rows stay limited by each viewer's scope.
- Ledger boundary: `timesheets.billable` only allows billing hours through a sales invoice; it needs `enabled: true` and `invoicingComponent`, the certified invoicing component listed in `components` (schema, plus validator `BP-MOD-003`). Costing and billing rates, amounts and the invoice posting come from the engine and that component, never from the Blueprint: no field on a module-bound entity, timesheet and activity_type included, may be named for a rigid-zone term (`billing_rate`, `costing_rate`, `amount` and every `x-rigid-zone-terms` match), and the bound timesheet and activity_type carry no money field (validator `BP-MOD-001`).
- View fields: timeline `startField`, `endField` and calendar `startField`, `endField` are date or datetime fields of the view's concept entity (validator `BP-MOD-002`).

Metrics: `projects.tasks_by_status`, `projects.overdue_tasks`, `projects.hours_logged`, `projects.billable_hours`, `projects.project_progress`

## Module `manufacturing`
Core BOM, work order, job card, routing and subcontracting records. This object only chooses which records and steps a company uses; it never sets a number.

| Concept | Required | Engine record (internal) |
|---|---|---|
| `item` | yes | Item (the inventory item master, shared with stock) |
| `bom` | yes | BOM with BOM Item, BOM Operation and BOM Scrap Item rows (submittable) |
| `work_order` | yes | Work Order (submittable; status Draft to Completed, Stopped, Closed, Cancelled) |
| `job_card` | when `operations.jobCards` | Job Card with time logs (submittable) |
| `operation`, `workstation` | when `operations.enabled` | Operation, Workstation |
| `routing` | no | Routing |
| `subcontracting_order`, `subcontracting_receipt` | when `subcontracting.enabled` | Subcontracting Order, Subcontracting Receipt (submittable) |

- `bom.withOperations` needs `operations.enabled`; `operations.jobCards` needs `operations.enabled`; `materialTransfer: job_card` needs job cards. `batchFromWorkOrder` creates finished-goods batches from the work order for batch-tracked items.
- Inventory touch points (rigid-zone boundary): `warehouses.workInProgress`, `finishedGoods` and optional `scrap` are location ids of kind warehouse (engine manufacturing settings defaults); WIP differs from finished goods and scrap differs from both (validator `BP-MOD-004`). Under perpetual inventory the warehouse's account decides which ledger account carries the value: that warehouse-to-account link stays with the certified component and is never set or drafted by the Blueprint. bpdiff classes a warehouse change `compliance`. Material transfer, manufacture and subcontracting receipt are engine stock entries: stock-class (ADR-0037), human floor on submit (ADR-0027).
- Ledger touch points (rigid-zone boundary): stock valuation, BOM raw-material costing, operating cost, scrap value and every stock or ledger posting are deterministic engine or certified-component logic, never AI-written. The schema offers no field for any of them, and no field on item, bom or any other manufacturing-bound entity may be named for one (`valuation_rate`, `rm_cost_as_per`, `operating_cost`, backflush settings and every `x-rigid-zone-terms` match; validator `BP-MOD-001`); the BOM cost basis and backflush basis stay engine defaults set by the certified component (Q-702).

Metrics: `manufacturing.work_orders_by_status`, `manufacturing.planned_vs_produced`, `manufacturing.job_card_hours`, `manufacturing.material_shortages`, `manufacturing.open_subcontracting`

## Module `marketing`
Segments, campaigns and email campaigns on core records, plus messaging campaigns sent only through the messaging connector. The messaging connector contract is DSC-022, still in progress on another branch. This contract refers to it by row id only and fixes no connector id.

| Concept | Required | Engine record (internal) |
|---|---|---|
| `campaign` | yes | Campaign (the same entity as the CRM campaign link) |
| `email_campaign` | when `channels.email.enabled` | Email Campaign with Campaign Email Schedule rows (`email_campaign_for` Lead, Contact or Email Group) |
| `messaging_campaign` | when `channels.messaging.enabled` | none: a Seshna record kept by the marketing component; sends go through the DSC-022 connector |

- `segments[]`: a saved audience over a CRM concept (`lead`, `contact` or `customer`) with up to ten guard filters (AND); no free-text query. For email the component compiles a segment to Email Group members (UNVERIFIED until BPL-059).
- `consent`: `optInRequired` and `unsubscribeRoute` are always true. A send goes only to recipients with a recorded opt-in for that channel. The engine's unsubscribed flags on leads and contacts, and its unsubscribe records, are honoured before every send. Opt-in records are tenant data kept by the component, never in the Blueprint (PDPL).
- `channels.messaging`: names an `integrations[]` entry whose connector is a messaging connector from DSC-022. Marketing messages use provider-approved templates only. Each customer's provider verification, templates and sender approvals are that customer's go-live items (ADR-0076 item 11). Inbound replies are untrusted content.

Metrics: `marketing.campaign_reach`, `marketing.opt_in_rate`, `marketing.unsubscribes`, `marketing.delivery_rate`, `marketing.leads_from_campaign`

## Changelog
- 0.8.0 (BPL-055): `modules.marketing` with segments, mandatory consent, and email and messaging channels; messaging refers loosely to DSC-022. Additive.
- 0.7.0 (BPL-054): `modules.manufacturing` with BOM, work order, job card, routing and subcontracting concepts, warehouses as inventory touch points (three distinct warehouses), and no costing or valuation fields; `backflush` joins `x-rigid-zone-terms`. Additive.
- 0.6.0 (BPL-053): `modules.projects` with task statuses mapped to engine statuses, board, timeline, calendar and list views, and timesheets (`billable` needs `enabled` and `invoicingComponent`); root `x-rigid-zone-terms`. Additive.
- 0.5.0 (BPL-052): optional `modules` with `crm`; shared `moduleRoles` and `moduleOption`. Additive: every 0.4.0 Blueprint stays valid; `meta.schemaVersion` stays `0.1.0` (Q-141).
