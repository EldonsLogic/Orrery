# ADR-0037: Manifest-declared entity risk class and explicit transition kind

Status: Accepted
Owner: eldon
Approved by: partner (sayegh9, 2026-11-19; cross-model review via Gemini 4 Neon high; follow-up in Q-299); Eldon recorded review on PR #183

## Context
The Tool API generator (OPR-003) decides each entity's risk class from a hard-coded reviewed table in `services/operate/toolapi/policy.py` plus ledger name tokens, and refuses anything else. That table cannot grow with the component library without a code change per entity. Q-138 also found that the generator accepts an explicit transition `kind` but the Blueprint schema has no field for it, so a valid Blueprint cannot carry it. And `contracts/tool-api.md` section 1 does not list fields the generator already emits (`risk_class`, `agent_creatable`, `requires_by_value`, `field_access`, `transitions`). Eldon decided all three in a walkthrough.

## Decision
1. **Component manifest 0.2.0.** An entity artifact (`provides[].artifacts[]` with `type: entity`) may declare an optional `riskClass`: `plain`, `stock`, `ledger`, `tax` or `permission`. The schema forbids it on other artifact types. `tax` means the `ledger` class plus `effects.tax` on every write. `permission` means the identity or permission domain: the entity never gets a tool (`TAPI-DOMAIN-001`).
2. **Raise only.** The generator takes the highest class from the reviewed table, the ledger name tokens, the L0 registry and the manifests. A manifest declaration below the table or token class is refused (`TAPI-MANIFEST-002`); a malformed one is `TAPI-MANIFEST-001`. When several manifests declare the same entity the highest wins. Only a manifest at certification level `reviewed`, `certified` or `regulated` (which names its reviewer, ADR-0034) may classify an entity that no other source knows; a `draft` or `tested` manifest can only raise. An entity absent from every source stays refused (`TAPI-CLASS-001`), as today.
3. **Recorded and rechecked.** `generate_tool_api(blueprint, registry, manifests)` and `check_tool_api(set, registry, manifests)` take the resolved manifests. The set records `manifests: {components, sha256}` (set format `toolApiVersion` 0.2.0); the checker refuses a set rechecked with other manifests (`TAPI-MANIFEST-003`). The CLI gains `--manifest` (repeatable).
4. **Blueprint 0.2.0.** `workflows[].transitions[].kind` is optional, enum `advance`, `approve`, `reject`, `cancel`, `reversal`, the same list as `policy.TRANSITION_KINDS`. It replaces only the generator's structural rule for stock and ledger entities; name tokens still only add restriction and the riskiest candidate wins, so a declared kind never lowers risk.
5. **Tool API 0.3.0.** Section 1.1 lists the generated fields (`risk_class`, `agent_creatable`, `entity_class`, `requires.roles`, `requires.scopes_by_role`, `requires_by_value`, `field_access`, the extra `approval` fields and `transitions[]`); section 1.2 the definition set envelope; section 11 the new class sources.

All three contract changes are backward compatible additions (minor bumps): every 0.1.0 Blueprint and manifest stays valid. `meta.schemaVersion` stays `0.1.0` for now because moving it needs a no-op migration step and `CURRENT_SCHEMA_VERSION` in `services/blueprint/migrate` (Q-141).

## Alternatives rejected
- Keep the hard-coded table only: every new component needs a generator code change and a reviewer in the operate lane; the class belongs to the component that defines the entity.
- Let the manifest set the class outright (also lower it): a manifest error or a hostile component could make a ledger document `plain` and agent-creatable. Fail closed means a declaration may only raise.
- Let any manifest classify an unknown entity: a `draft` manifest has no named reviewer, so it could open an unreviewed entity as `plain`.
- Add `tax` and `permission` as new rows in the risk table: `tax` behaves like `ledger` plus an effect, and `permission` entities must never get tools at all, so new rows would add rules without adding protection.
- Put the class on the Blueprint entity: the Blueprint is drafted by the model from an interview; the risk class must come from reviewed component configuration, not tenant configuration.
- A top-level `entityRiskClasses` map in the manifest: duplicates the entity list already in `provides[].artifacts` and can drift from it.

## Consequences
New components declare their entities' class in the manifest; the reviewed table remains the floor. Generated sets now record which manifests were used, so storage must keep them (or their ids and versions) with the set. Callers that pass no manifests get exactly the old output (plus `manifests: null`). Follow-ups: the gateway (PLT-024) and the compiler pass resolved manifests to the generator; Q-141 moves `meta.schemaVersion` to 0.2.0 with a migration step. Code: `services/operate/toolapi/classify.py` (`Policy`), tests `services/operate/tests/toolapi/test_manifest_classes.py`. Resolves Q-138.

## Supersedes
none
