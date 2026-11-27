# Blueprint modules

Status: draft
Owner: eldon
Version: 0.5.0

Part of contract 1 ([blueprint.schema.json](blueprint.schema.json), `$defs/modules`). How an engine-core module joins a tenant's Blueprint. Decision: [ADR-0079](../docs/decisions/ADR-0079-engine-core-modules-in-the-blueprint.md) (Proposed); scope: [ADR-0076](../docs/decisions/ADR-0076-phase-1-module-scope.md). Example: [examples/blueprint-modules-minimal.json](examples/blueprint-modules-minimal.json); negative cases: `examples/invalid/blueprint-modules-*-cases.json`, run by `tests/test_blueprint_modules.py`.

## Shape every module follows
- **Opt-in per company.** `modules.<key>` present means the module is on for this company; absent means off. No key, no screens, tools or metrics for it.
- **Component.** `component` names the component that implements the module; it is listed in top-level `components` and its manifest provides `<module>.module`.
- **Entity vocabulary.** `entities` maps each module concept to exactly one Blueprint entity id (by design: one concept, one entity; two concepts never name the same entity). Fields, labels and relations stay on the entity as today; the concept tells the compiler and the engine mapping which engine record it is. An empty `modules: {}` is refused: omit `modules` when no module is on.
- **Who implements a concept.** Each concept entity has exactly one implementing component: the module component, which provides `<module>.<concept>`, or, for a **shared concept** (listed in the schema's `x-module-shared-concepts` and in the module's table below), the component that owns it elsewhere, which provides the listed capability. Never both. The module's table says which, per concept.
- **Workflow vocabulary.** Each module has a fixed-shape state list (pipeline stages, task statuses) mapped onto the engine's own status values. Generic `workflows[]` may still sit on a bound entity for approvals.
- **Role vocabulary.** `roles.manage`, `roles.work`, `roles.view` list the Blueprint role ids that the module's screens treat as managers, workers and viewers. Listing grants nothing: `roles[].permissions` and scope decide everything. A change to a module role list is classed `access` by bpdiff.
- **Report vocabulary.** Reports reference module metrics by id (below). Numbers come from code in the semantic layer; the Blueprint never holds a formula.
- **Rigid zone.** Module settings carry configuration only. Posting, valuation, tax and costing stay deterministic engine or certified-component logic, never AI-written (AGENTS.md principle 3).

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

## Changelog
- 0.5.0 (BPL-052): optional `modules` with `crm` (an empty `modules` is refused); shared `moduleRoles` and `moduleOption`; `x-module-shared-concepts` for concepts another component may implement (#395 review). Additive: every 0.4.0 Blueprint stays valid; `meta.schemaVersion` stays `0.1.0` (Q-141).
