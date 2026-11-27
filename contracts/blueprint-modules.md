# Blueprint modules

Status: draft
Owner: eldon
Version: 0.5.0

Part of contract 1 ([blueprint.schema.json](blueprint.schema.json), `$defs/modules`). How an engine-core module joins a tenant's Blueprint. Decision: [ADR-0079](../docs/decisions/ADR-0079-engine-core-modules-in-the-blueprint.md) (Proposed); scope: [ADR-0076](../docs/decisions/ADR-0076-phase-1-module-scope.md). Example: [examples/blueprint-modules-minimal.json](examples/blueprint-modules-minimal.json); negative cases: `examples/invalid/blueprint-modules-*-cases.json`, run by `tests/test_blueprint_modules.py`.

## Shape every module follows
- **Opt-in per company.** `modules.<key>` present means the module is on for this company; absent means off. No key, no screens, tools or metrics for it.
- **Component.** `component` names the component that implements the module; it is listed in top-level `components` and its manifest provides `<module>.module`.
- **Entity vocabulary.** `entities` maps each module concept to a Blueprint entity id. Fields, labels and relations stay on the entity as today; the concept tells the compiler and the engine mapping which engine record it is.
- **Workflow vocabulary.** Each module has a fixed-shape state list (pipeline stages, task statuses) mapped onto the engine's own status values. Generic `workflows[]` may still sit on a bound entity for approvals.
- **Role vocabulary.** `roles.manage`, `roles.work`, `roles.view` list Blueprint role ids. Listing grants nothing: `roles[].permissions` and scope decide every action.
- **Report vocabulary.** Reports reference module metrics by id (below). Numbers come from code in the semantic layer; the Blueprint never holds a formula.
- **Rigid zone.** Module settings carry configuration only. Posting, valuation, tax and costing stay deterministic engine or certified-component logic, never AI-written (AGENTS.md principle 3).

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

- `pipeline.stages`: in order; at least one `open`, exactly one `won` (probability 100) and one `lost` (probability 0). Open stages map to Sales Stage records and the opportunity probability; `won` maps to status Converted and `lost` to status Lost with a lost reason.
- `leadSources` map to Lead Source records; `lostReasons` to Opportunity Lost Reason records.
- `activityTypes`: `message` is only sent through a messaging connector integration (DSC-022); inbound text is untrusted.

Metrics: `crm.pipeline_value`, `crm.weighted_pipeline_value`, `crm.win_rate`, `crm.stage_conversion`, `crm.leads_by_source`, `crm.lost_by_reason`, `crm.activities_due`

## Changelog
- 0.5.0 (BPL-052): optional `modules` with `crm`; shared `moduleRoles` and `moduleOption`. Additive: every 0.4.0 Blueprint stays valid; `meta.schemaVersion` stays `0.1.0` (Q-141).
