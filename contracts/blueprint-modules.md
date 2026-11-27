# Blueprint modules

Status: draft
Owner: eldon
Version: 0.7.0

Part of contract 1 ([blueprint.schema.json](blueprint.schema.json), `$defs/modules`). How an engine-core module joins a tenant's Blueprint. Decision: [ADR-0079](../docs/decisions/ADR-0079-engine-core-modules-in-the-blueprint.md) (Proposed); scope: [ADR-0076](../docs/decisions/ADR-0076-phase-1-module-scope.md). Example: [examples/blueprint-modules-minimal.json](examples/blueprint-modules-minimal.json); negative cases: `examples/invalid/blueprint-modules-*-cases.json`, run by `tests/test_blueprint_modules.py`.

## Shape every module follows
- **Opt-in per company.** `modules.<key>` present means the module is on for this company; absent means off. No key, no screens, tools or metrics for it.
- **Component.** `component` names the component that implements the module; it is listed in top-level `components` and its manifest provides `<module>.module`.
- **Entity vocabulary.** `entities` maps each module concept to exactly one Blueprint entity id (by design: one concept, one entity; two concepts never name the same entity). Fields, labels and relations stay on the entity as today; the concept tells the compiler and the engine mapping which engine record it is. An empty `modules: {}` is refused: omit `modules` when no module is on.
- **Who implements a concept.** Each concept entity has exactly one implementing component: the module component, which provides `<module>.<concept>`, or, for a **shared concept** (listed in the schema's `x-module-shared-concepts` and in the module's table below), the component that owns it elsewhere, which provides the listed capability. Never both. The module's table says which, per concept.
- **Workflow vocabulary.** Each module has a fixed-shape state list (pipeline stages, task statuses) mapped onto the engine's own status values. Generic `workflows[]` may still sit on a bound entity for approvals.
- **Role vocabulary.** `roles.manage`, `roles.work`, `roles.view` list the Blueprint role ids that the module's screens treat as managers, workers and viewers. Listing grants nothing: `roles[].permissions` and scope decide everything. A change to a module role list is classed `access` by bpdiff; switching a module off (removing `modules.<key>`) is classed `destructive` (Q-700).
- **Report vocabulary.** Reports reference module metrics by id (below). Numbers come from code in the semantic layer; the Blueprint never holds a formula.
- **Rigid zone.** The danger is a Blueprint touching the engine's own rigid-zone fields and logic, not a custom field with a money-sounding name.
  - Engine rigid-zone fields are an explicit, versioned list per engine record type and its rows: [engine-rigid-fields.json](engine-rigid-fields.json) (valuation, costing, posting, tax and ledger fields; read from the pinned source at the tags in [engine-version-policy.md](../docs/architecture/engine-version-policy.md); internal; UNVERIFIED until a bench run). On an entity bound by a module concept, and on every entity reached from it through `child_table` relations at any depth, a Blueprint may not declare, override, rename or set a default or options on those fields, as a field or as a component parameter (validator `BP-MOD-001`, which fails closed when the list is missing or a concept has no entry).
  - A Blueprint field never carries computation, on any entity: no formula, expression, fetch-from, depends-on or default-expression key (schema `field.propertyNames` and `additionalProperties`), and a string `default` never starts with `eval:`, `=` or `:`. `computed` only names a certified function.
  - Custom fields with any name, money and percent included (`tax_id`, `account_manager`, an opportunity `amount`, an item `cost_price`), stay allowed as plain data. They never feed posting, valuation or tax: only the certified component and engine logic do (AGENTS.md principle 3).
  - Module settings carry configuration only; the contract tests lint the modules schema's own setting keys for formula, posting, costing and tax knobs.

Engine record names below are internal (ADR-0016): they never appear in anything a customer sees. Every one is UNVERIFIED until a bench run on the pinned set; names were read from the pinned ERPNext v15.124.5 source on 2026-11-27 (https://github.com/frappe/erpnext/tree/v15.124.5).

## Module `crm`
Core CRM records plus framework records (Contact, Event, ToDo, Communication) (ADR-0076 item 5). Never the separate CRM app or its integration settings.

| Concept | Required | Implemented by | Engine record (internal) |
|---|---|---|---|
| `lead` | no | CRM component (`crm.lead`) | Lead (`source` links Lead Source, `campaign_name` links Campaign) |
| `opportunity` | yes | CRM component (`crm.opportunity`) | Opportunity (`opportunity_from` customer or lead, `sales_stage`, `probability`, `campaign`) |
| `customer` | yes | shared: the core customer component (`core.customer.entities`) when the Blueprint lists one, else the CRM component (`crm.customer`) | Customer |
| `contact` | no | CRM component (`crm.contact`) | Contact (framework record) |
| `activity` | when `activityTypes` is set | CRM component (`crm.activity`) | one Blueprint entity over several engine records (mapping owed, BPL-062): note: CRM Note rows; call, meeting, visit: Event; follow_up: ToDo; email, message: Communication |
| `campaign` | when `campaignLink` is true | shared: the marketing component (`marketing.campaign`) when the marketing module is on (one entity, BPL-055), else the CRM component (`crm.campaign`) | Campaign |

- `pipeline.stages`: in order; at least one `open` (probability strictly between 0 and 100), exactly one `won` (probability 100) and one `lost` (probability 0). Open stages map to Sales Stage records and the opportunity probability.
- **Outcomes are not written from a stage** (#395 review; read from the pinned source, UNVERIFIED on a bench, Q-701):
  - `won`: the engine derives opportunity status Converted from the quotation and order flow (an ordered quotation; a sales-order submit or cancel re-derives it). The component reaches `won` through that flow and never writes Converted itself.
  - `lost`: only through the engine's declare-lost flow, with lost reasons from `lostReasons`. The engine refuses it while the opportunity has an active quotation, and the component surfaces that refusal; it never writes status Lost directly.
  - Other engine opportunity statuses: Open is every `open` stage. Quotation and Replied are engine-set statuses inside the open part of the pipeline; they map to no stage and are shown as record state, never as a stage move. Closed is excluded: the component never sets it, and a record the engine closes leaves the pipeline views (UNVERIFIED).
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
- Ledger boundary: `timesheets.billable` only allows billing hours through a sales invoice; it needs `enabled: true` and `invoicingComponent`, the certified invoicing component listed in `components` (schema, plus validator `BP-MOD-003`). Costing and billing rates, amounts and the invoice posting come from the engine and that component, never from the Blueprint: the timesheet, its rows and the activity type may not declare the engine's `billing_rate`, `costing_rate`, `billing_amount`, `costing_amount`, their `base_` forms or `sales_invoice` (validator `BP-MOD-001`). A custom money field on a timesheet is plain data and never reaches the invoice. The billing selectors are rigid too (#396 review): Timesheet Detail `is_billable`, the Timesheet `customer`, `currency` and `company`, and the Project `customer` (read from the pinned `timesheet.py`, UNVERIFIED). A Blueprint never declares them; the projects component sets the project's customer and the billable flag through the engine's own flow (BPL-057), so the example project has no `customer` field.
- View fields: timeline `startField`, `endField` and calendar `startField`, `endField` are date or datetime fields of the view's concept entity (validator `BP-MOD-002`).

Metrics: `projects.tasks_by_status`, `projects.overdue_tasks`, `projects.hours_logged`, `projects.billable_hours`, `projects.project_progress`

## Module `manufacturing`
Core BOM, work order, job card, routing and subcontracting records. This object only chooses which records and steps a company uses; it never sets a number.

| Concept | Required | Engine record (internal) |
|---|---|---|
| `item` | yes | Item (the inventory item master, shared with stock). Shared concept: implemented by the core item component (`core.item.entities`) when the Blueprint lists one, else the manufacturing component (`manufacturing.item`) |
| `bom` | yes | BOM with BOM Item, BOM Operation and BOM Scrap Item rows (submittable) |
| `work_order` | yes | Work Order (submittable; status Draft to Completed, Stopped, Closed, Cancelled) |
| `job_card` | when `operations.jobCards` | Job Card with time logs (submittable) |
| `operation`, `workstation` | when `operations.enabled` | Operation, Workstation |
| `routing` | no | Routing |
| `subcontracting_order`, `subcontracting_receipt` | when `subcontracting.enabled` | Subcontracting Order, Subcontracting Receipt (submittable) |

- **Stock Entry is component-only** (#397 review): no concept, entity, permission or field in the Blueprint; created and posted only by the certified manufacturing component (BPL-058), Tier 3, stock-class (ADR-0037), human floor on submit and cancel (ADR-0027). The same holds for the Subcontracting Receipt submit and cancel.
- Subcontracting: the engine's Subcontracting Order requires a `purchase_order` (a Purchase Order with service items). The Blueprint supplies it through a listed purchasing component providing purchase orders (`purchasing.purchase_order` in the fixtures); a validator check is owed (BPL-060).
- `bom.withOperations` needs `operations.enabled`; `operations.jobCards` needs `operations.enabled`; `materialTransfer: job_card` needs job cards. `batchFromWorkOrder` creates finished-goods batches from the work order for batch-tracked items.
- Inventory touch points (rigid-zone boundary): `warehouses.workInProgress`, `finishedGoods` and optional `scrap` are location ids of kind warehouse (engine manufacturing settings defaults); WIP differs from finished goods and scrap differs from both (validator `BP-MOD-004`). Under perpetual inventory the warehouse's account decides which ledger account carries the value: that warehouse-to-account link stays with the certified component and is never set or drafted by the Blueprint. bpdiff classes a warehouse change `compliance`. The work order and job card post nothing themselves; stock moves are the engine's Stock Entry records (purposes Material Transfer for Manufacture, Material Consumption for Manufacture, Manufacture) and the Subcontracting Receipt (`stock_entry.py`, `work_order.py`, `job_card.py` at v15.124.5, https://github.com/frappe/erpnext/tree/v15.124.5, accessed 2026-11-27; UNVERIFIED on a bench).
- Ledger touch points (rigid-zone boundary): stock valuation, BOM raw-material costing, operating cost, scrap value and every stock or ledger posting are deterministic engine or certified-component logic, never AI-written. The module schema offers no setting for any of them, and item, bom, their rows (BOM lines, operations, scrap rows, item defaults and item taxes, inline or as `child_table` entities) and every other manufacturing-bound entity may not declare the engine's own fields for them (`valuation_rate`, `valuation_method`, `item_tax_template`, `income_account`, `rm_cost_as_per`, `operating_cost`, BOM line `rate` and `amount` and the rest of `engine-rigid-fields.json`; validator `BP-MOD-001`). The backflush basis is an engine manufacturing setting, not a field of any bound record, so the Blueprint has no key for it. The engine settings that shape valuation are listed below with the pinned default; the certified component sets each explicitly, locks it and refuses runtime writes (Q-702). Setting and locking them is Tier 3 with an accountant's sign-off (ADR-0033), never a Blueprint key. The trading template's item fields `cost_price`, `selling_price` and `vat_rate` are custom master data: they stay valid when manufacturing is on and never feed valuation, posting or tax.

| Engine setting (internal) | Where | Pinned default | Set by |
|---|---|---|---|
| `rm_cost_as_per` | each BOM (so per record, not once) | `Valuation Rate` | component on every BOM it writes; a runtime BOM write that changes it is refused |
| `backflush_raw_materials_based_on` | Manufacturing Settings | `BOM` | component, locked |
| `backflush_raw_materials_of_subcontract_based_on` | Buying Settings | `BOM` | component, locked |
| `material_consumption` | Manufacturing Settings | `0` | component, locked |
| `get_rm_cost_from_consumption_entry` | Manufacturing Settings | `0` | component, locked |
| `add_corrective_operation_cost_in_finished_good_valuation` | Manufacturing Settings | `0` | component, locked |
| `set_op_cost_and_scrap_from_sub_assemblies` | Manufacturing Settings | `0` | component, locked |
| `update_bom_costs_automatically` | Manufacturing Settings | `0` | component, locked |

Defaults read from the doctype JSON at v15.124.5 (https://github.com/frappe/erpnext/tree/v15.124.5, accessed 2026-11-27); UNVERIFIED on a bench. The values to set are the accountant's call per company (ADR-0033); the defaults are only the starting point.

Metrics: `manufacturing.work_orders_by_status`, `manufacturing.planned_vs_produced`, `manufacturing.job_card_hours`, `manufacturing.material_shortages`, `manufacturing.open_subcontracting`

## Changelog
- 0.7.0 (BPL-054): `modules.manufacturing` with BOM, work order, job card, routing and subcontracting concepts, warehouses as inventory touch points (three distinct warehouses), and no costing or valuation settings; `engine-rigid-fields.json` 0.1.0 already holds the manufacturing records (added on the BPL-053 base) and gains their stock-shaping and warehouse fields (#397 review; BP-MOD-001); Stock Entry is component-only; engine settings listed with pinned defaults, and the contract test's module-setting term list gains `backflush`. Additive.
- 0.6.0 (BPL-053): `modules.projects` with task statuses mapped to engine statuses, board, timeline, calendar and list views, and timesheets (`billable` needs `enabled` and `invoicingComponent`); engine rigid-zone field list `engine-rigid-fields.json` 0.1.0 (BP-MOD-001); field computation keys and expression defaults refused. Additive for 0.5.0 Blueprints, except a string field default starting with `eval:`, `=` or `:`, now refused.
- 0.5.0 (BPL-052): optional `modules` with `crm` (an empty `modules` is refused); shared `moduleRoles` and `moduleOption`; `x-module-shared-concepts` for concepts another component may implement (#395 review). Additive: every 0.4.0 Blueprint stays valid; `meta.schemaVersion` stays `0.1.0` (Q-141).
