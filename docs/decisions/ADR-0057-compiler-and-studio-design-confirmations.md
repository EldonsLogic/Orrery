# ADR-0057: Compiler, token-resolver and Studio design confirmations

Status: Proposed
Owner: eldon
Approved by: pending (partner review)

## Context
The Blueprint compiler (BPL-004), the token resolver (BRD-004), Studio (WEB-020) and the Blueprint migration framework (BPL-021) each took a conservative reading of points their contracts did not settle, and listed those points in their docstrings. They were copied into [docs/open-questions.md](../open-questions.md) as rows that ask someone to "confirm" a design choice. No ADR recorded an answer, so the rows stayed open. Eldon has asked agents to decide technical calls themselves. This ADR decides the rows that are purely technical, all in Eldon's lane (`services/blueprint`, `services/studio`). Rows that touch tax, ledger, e-invoicing, security, tenancy or approvals, that need a founder decision, or that depend on unbuilt work are left open (listed below).

## Decision
Each row below is either kept as built, or changed. A change is recorded here and not implemented; its follow-up is named in the row. File and line references are on main at the time of writing.

| Q | Decision | Rationale (file:line) |
|---|---|---|
| Q-50 | Keep: an initial build diffs an empty skeleton to the target; no separate initial-build form. | One compile path for initial and incremental builds; the skeleton keeps the same containers so every op is an `add` and `diffHash` is null as the schema requires (`services/blueprint/compiler/steps.py:37-50`, `services/blueprint/compiler/core.py:58-63`). |
| Q-51 | Change: exempt `settings.set` from the (kind, pointer) uniqueness rule; for it the key is (kind, pointer, `params.property`). Keep the section pointer. | The section pointer matches the fake and real adapters' `settings_*` objects; the property already breaks the sort tie (`services/blueprint/compiler/steps.py:73-85`). The rule text in `contracts/compiled-artifact.schema.json:235` is the part that is wrong. Follow-up: new work, a contract patch to the x-validator-rules text (no plan row yet). |
| Q-52 | Keep: `i18n.labelOverrides` compiles as `settings.set`, like `i18n.defaultLocale`. | It is a locale setting, not a glossary; the fake exports it as a `settings_intl` property (`services/blueprint/compiler/steps.py:28`, `:72-76`). Follow-up: name it in `contracts/engine-adapter.md` 9.3 in the same contract patch as Q-51. |
| Q-54 | Keep the contract phase order; the adapter resolves forward references, which `plan_view` lists. | Reordering cannot remove references inside one phase (entities and locations reference each other), so forward references are unavoidable; `plan_view` already reports them per step (`services/blueprint/compiler/plan.py:3-7`, `:82`). |
| Q-55 | Keep: the engine mapping is not recorded in the artifact. | The mapping is a gate and contributes no value to the steps (`services/blueprint/compiler/mapping.py:1-3`); the artifact identity rule covers what the steps depend on (`contracts/compiled-artifact.schema.json:20`). Adding it would make two identical step lists hash differently. |
| Q-56 | Keep: a draft mapping compiles only for sandbox, with a version set equal to the Blueprint's or marked UNVERIFIED. | Fails closed for production (`services/blueprint/compiler/mapping.py:41-49`); sandbox still lets mapping work proceed before verification. |
| Q-58 | Keep: resolve the highest version in range, refuse if it is not eligible; no fallback to a lower eligible version. | A silent fallback would make the compiled version depend on the environment and hide that the intended version is blocked (`services/blueprint/compiler/components.py:36-54`). |
| Q-60 | Keep: post-conditions use `exists`, `count_equals` and `order_equals` only; do not close `exportedProperties`. | Exported property lists are open (contract 16.3), so `property_equals` could fail on a correct site (`services/blueprint/compiler/steps.py:92-108`). |
| Q-64 | Change: the token resolver's OKLCH derive is authoritative; validator rule 10 (`BP-BRAND-001/002`) should call the same derive so a Blueprint that validates is never refused by the resolver. | The resolver is what emits tenant tokens and already fails closed (`services/blueprint/tokens/resolver.py:292-311`); the validator's HSL search is a looser approximation (`services/blueprint/validator/rules_branding.py:13-40`). Follow-up: new work, align rule 10 with `derive_tenant_theme` (no plan row yet; it touches the same runtime dependency as Q-65). |
| Q-66 | Keep: refuse with `TKN-BASE-MISMATCH` when merged layers change the v1 base colours. | The derive constants are calibrated against the v1 base; re-deriving against other bases is untested, so refusing is the fail-closed choice (`services/blueprint/tokens/resolver.py:292-294`, `:328-335`). |
| Q-67 | Keep: no focus-ring token; the ring follows `--color-primary`. | The tenant token allow-list stays small and the ring keeps the primary's checked contrast (`services/blueprint/tokens/resolver.py:14-20`). |
| Q-68 | Keep the slug rule: lowercase letters, digits and hyphen, 1 to 63 characters, no leading or trailing hyphen. | It is the DNS label rule and the slug lands in a CSS selector, so it must be strict (`services/blueprint/tokens/resolver.py:35`, `:266-271`). |
| Q-69 | Keep: display name length counted in Unicode code points; control characters and blank text refused. | Code points are deterministic across runtimes; refusing Cc and Cs blocks invisible or broken text (`services/blueprint/tokens/resolver.py:114-127`). |
| Q-70 | Keep: the resolver accepts any valid layer-1 token set, so accepting the proposed tokens changes data, not code. | Layers are passed in and validated, not hard-coded (`services/blueprint/tokens/resolver.py:188-212`). Accepting the tokens themselves remains a brand decision outside this ADR. |
| Q-71 | Keep: with no tenant accent, `--color-accent` is left alone unless derive falls back to the text colour. | Emits only what differs from the product theme (`services/blueprint/tokens/resolver.py:299-303`). |
| Q-72 | Keep: `tokens` is not a Blueprint field; it exists only so direct override attempts are refused and logged. | Every entry is refused, never applied (`services/blueprint/tokens/resolver.py:131-135`, `:233-234`). |
| Q-73 | Keep: a stored `resolved` block is used verbatim and not re-checked against `primaryColour`; an explicit save drops it and resolves again. | Pinning stops an algorithm change from restyling a tenant; the stored block is still shape- and allow-list-checked (`services/blueprint/tokens/resolver.py:163-177`, `:273-279`). The save path (BRD-005, Studio) must drop `resolved` when the colour changes. |
| Q-75 | Keep: BRD-004 only validates the theme mode and emits `data-theme`; persistence and the theme engine are BRD-005. | Keeps the resolver pure (`services/blueprint/tokens/resolver.py:95-112`, `:321-322`). |
| Q-78 | Keep: Studio compiles as sandbox. | Studio is a local tool on synthetic data and the fixture components are `tested`, which production refuses (`services/studio/session.py:22`, `services/studio/__init__.py:1-7`). |
| Q-81 | Keep: Studio refuses any response containing the engine's name, including tenant text. | Fail closed per ADR-0016; a false refusal on a typed label is cheaper than a leak (`services/studio/server.py:29`, `:95-99`). |
| Q-82 | Keep: a plugged engine drops nothing up front and retries preview once without `attachment` fields, reported in `droppedFields`. | Contract 0.1.2 cannot report unsupported value types (`services/studio/session.py:301-305`, `services/studio/engine.py:17-18`). When the adapter contract next changes, `capabilities` should list unsupported value types; the Studio docstring item 8 is slightly stale (it omits the retry). |
| Q-86 | Keep: a migration does not bump `meta.revision`; the framework refuses a step that changes it. | A re-encoding is not an owner-approved change (`services/blueprint/migrate/core.py:20`, `:76`; `docs/architecture/blueprint-versioning.md:27`). A control-plane migration marker can be added later without changing this rule. |

Left open (not decided here):
- Q-59: classifies ledger or tax risk (`touchesLedgerOrTax`).
- Q-74: where the tenant slug comes from is a tenancy question.
- Q-79: auto-granted approvals touch approval authority (ADR-0048, ADR-0049).
- Q-80: ZATCA QR inputs are e-invoicing.
- Q-83, Q-84, Q-85: prompt-injection suite (security); Q-84 depends on the gateway (PLT-009), Q-85 on a real adapter.
- Q-88: `contracts/blueprint.schema.json:4` is version 0.4.0 while `meta.schemaVersion` is const 0.1.0 (`:230`) and the migrator's current version is 0.1.0 (`services/blueprint/migrate/core.py:18`). So the premise of the row does not hold on main. It is tied to Q-89 and needs its own decision.
- Q-93: confusable handling in the connector framework is untrusted-content defence (security).

## Alternatives rejected
- Answer every row in its own ADR: 22 small records for choices that are already built and documented in code.
- Leave the rows open until a reviewer asks: the code already behaves this way, and open "confirm" rows hide the questions that really are open.
- Decide the excluded rows too: they touch rigid zones, security or tenancy, or depend on unbuilt work, and need their own review.

## Consequences
- 22 rows in `docs/open-questions.md` are marked resolved by this ADR; 10 candidates stay open.
- Two changes need follow-up work that has no plan row yet: a contract patch (Q-51 rule text, Q-52 in 9.3), and aligning validator rule 10 with the resolver (Q-64).
- Partner review is needed before this ADR is Accepted.

## Supersedes
None.
