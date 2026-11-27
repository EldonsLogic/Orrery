# ADR-0079: Engine-core modules join the Blueprint as opt-in `modules` with a fixed vocabulary per module

Status: Proposed
Owner: eldon
Approved by: pending (Eldon's agent proposed it on the BPL-052 PR; partner review on that PR)

## Context
[ADR-0076](ADR-0076-phase-1-module-scope.md) (Proposed) adds ten phase-1 modules as Blueprint components and asks for contracts first. Four of them run on records the pinned engine core already has: CRM (BPL-052), projects and boards (BPL-053), manufacturing (BPL-054) and marketing (BPL-055). Blueprint 0.4.0 can describe their entities, workflows, roles and reports generically, but it cannot say "this company runs CRM", which entity is the opportunity, or what the pipeline stages are, so the compiler, the engine mapping and the screens (WEB-031 to WEB-034) would each have to guess. RULES 19 and [contracts/README.md](../../contracts/README.md) rule 2 need an ADR for any contract change.

## Decision
1. **Blueprint 0.5.0 adds an optional top-level `modules` object.** One key per module (`crm` in 0.5.0; `projects`, `manufacturing` and `marketing` follow in their own minor bumps). A key present means the module is on for this company; absent means off. Unknown keys are refused (`additionalProperties: false`). Every 0.4.0 Blueprint stays valid; `meta.schemaVersion` stays `0.1.0` (Q-141), so no migration step ships.
2. **Every module has the same four vocabularies:**
   - **Entity:** `entities` maps each module concept (for CRM: lead, opportunity, customer, contact, activity, campaign) to a Blueprint entity id. Fields and relations stay on the entity; the concept fixes which engine record it compiles to.
   - **Workflow:** a fixed-shape state list per module (CRM pipeline stages; task statuses for boards) mapped onto the engine's own status values. Generic `workflows[]` may still sit on a bound entity for approvals.
   - **Role:** `roles.manage`, `roles.work`, `roles.view` list Blueprint roles. Listing grants nothing; `roles[].permissions` and scope still decide every action, and the human floor ([ADR-0027](ADR-0027-human-floor-action-policy-and-agent-authority.md)) is unchanged.
   - **Report:** a closed list of metric ids per module (`crm.win_rate` and so on), kept in [contracts/blueprint-modules.md](../../contracts/blueprint-modules.md). Numbers come from code; the Blueprint never holds a formula.
3. **Mapping to components.** `component` names the component that implements the module; it must be listed in `components` and provide the capability `<module>.module`, and each concept entity has exactly one implementing component: the module component (providing `<module>.<concept>`) or, for a shared concept listed in the schema's `x-module-shared-concepts` (CRM: `customer` with the core customer component, `campaign` with marketing), the component that owns it, providing the listed capability; the contract doc says which per concept. One concept binds one entity; two concepts never share one. Builds BPL-056 to BPL-059 (partner) supply those components.
4. **Engine basis.** Only engine-core records of the pinned set, named in the internal contract doc and never in anything a customer sees ([ADR-0016](ADR-0016-engine-invisibility.md)). CRM never uses the separate AGPL CRM app (ADR-0076 item 5). Every engine name stays UNVERIFIED until a bench run.
5. **Rigid zone.** Module settings carry configuration only: no formula, posting, valuation, costing or tax field. Where a module touches stock or the ledger (timesheet billing, manufacturing stock entries), the boundary is named in the contract doc and the maths stays deterministic engine or certified-component logic, never AI-written.
6. **Schema-checkable rules live in the schema** (pipeline shape, won 100 and lost 0, required concepts, conditional concepts). Cross-reference rules (ids resolve, component capabilities, metric vocabulary, role read access) are listed in `x-validator-rules`; the validator implements them in BPL-060 (G2), not in this ADR's PRs. Compiler support for `modules` is BPL-061 and the concept-to-engine mapping (including multi-record concepts such as `activity`) is BPL-062, both G2.

## Alternatives rejected
- Generic entities only, no `modules`: the compiler and screens would infer the module from entity names, which is guessing and breaks on tenant renames.
- One `modules[]` array of `{id, settings}`: settings would be untyped per module; a keyed object lets the schema type each module and refuse unknown ones.
- Module role functions in `roles[].function` (for example `crm_manager`): mixes module membership into the single function enum and cannot express one role working in two modules.
- Metric definitions in the Blueprint: formulas in configuration break "numbers come from code".
- Use the AGPL CRM app for richer CRM: rejected by ADR-0076.

## Consequences
- Easier: screens and builds can start from a typed contract; once BPL-060 to BPL-062 land, a company switches a module on by adding one key, through the normal change path and diff. Today the compiler refuses an added or changed `modules` block (`CMP-ART-001`, pinned by a test), so no module reaches a tenant yet.
- Harder: the bpdiff key table must list every new keyed array (done in each PR), and bpdiff classes removing a pipeline stage, lead source or lost reason, rebinding a concept, changing a stage kind or swapping the module component as `destructive`; the validator rules in item 6 are owed before a module goes to a customer (open question Q-700).
- Must do: BPL-053, BPL-054 and BPL-055 extend `modules` in their own PRs (0.6.0, 0.7.0, 0.8.0); BPL-056 to BPL-059 build the components; WEB-031 to WEB-034 build screens on fixtures from these contracts.

## Note (BPL-053, #396 re-review)
Item 5 is enforced by the engine's own field list, not by name: [contracts/engine-rigid-fields.json](../../contracts/engine-rigid-fields.json) lists the pinned engine's valuation, costing, posting, tax and ledger fields per record type, and a Blueprint may not declare or override them on a module-bound entity or its `child_table` rows (`BP-MOD-001`). Blueprint fields never carry computation; custom fields of any name stay plain data and never feed posting, valuation or tax. The name-based term list was dropped because it refused ordinary master data (`tax_id`, `account_manager`, an item `cost_price`) and missed real money names.

## Note (BPL-053, #396 review: the 0.6.0 break)
0.6.0 is not purely additive. The field `default` rule refuses a string default that starts with `eval:`, `=` or `:` (an engine expression, not a literal), so a 0.5.0 Blueprint carrying one no longer validates. [contracts/README.md](../../contracts/README.md) rule 1 allows a 0.x minor to break only when the ADR says so; this note says so. Such a Blueprint drops the default or replaces it with a literal; no tenant Blueprint exists yet, so nothing migrates.

## Note (BPL-055, #398 review: email)
Email is not in 0.8.0. The engine's Email Campaign sends from a scheduler with no approval step, and the messaging connector's consent records do not cover email, so `channels.email` and the `email_campaign` concept move to BPL-066, after the email sending connector contract (DSC-025). Until then marketing sends go only through the messaging connector.

## Note (BPL-066: email in 0.9.0)
Email returns in Blueprint 0.9.0, additive, on the email sending connector contract (DSC-025, [ADR-0081](ADR-0081-email-sending-connector.md)). `channels.email` names a DSC-025 integration (`x-email-connectors`, `BP-MOD-006`) and the `email_campaign` concept is a Seshna record, never the engine's Email Campaign, whose scheduler never sends. Consent is per contact, channel `email`, country and purpose `marketing`, a cross-channel STOP is honoured, and every send and A/B winner send is R3, human, with an `approvalId`. The module gains a template library (brand tokens only; Arabic rtl and English ltr variants; plain-text part; platform-worded unsubscribe block and a footer with the sender's postal address), saved reusable blocks, A/B tests with a deterministic winner rule (no model picks the winner), tracking off by default and fixed send windows per country (`BP-MOD-007` to `BP-MOD-009`). bpdiff classes email consent, sender identity, the unsubscribe and footer blocks, tracking and the winner release as `compliance` and template content as `config`. Open: Q-730 to Q-733.

## Supersedes
none
