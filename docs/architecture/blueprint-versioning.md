# Blueprint versioning and migration

Status: draft. Plan row BPL-021. Code: `services/blueprint/migrate/`. Contract: [blueprint.schema.json](../../contracts/blueprint.schema.json), rules in [contracts/README.md](../../contracts/README.md), lifecycle in [build-states.md](../../contracts/build-states.md).

## Three kinds of version

| Version | Where | Meaning | Changes when |
|---|---|---|---|
| `meta.schemaVersion` | every Blueprint | Which version of the Blueprint contract the document is written in | The contract changes shape (migration needed if it breaks) |
| Component versions | `components[]` and the registry | Which vetted component release the Blueprint pins | A component is released; resolved by the registry and compiler, never by migration |
| `meta.revision` | every Blueprint | Business history: increments on every approved change; diffs are between revisions | The owner or an agent changes content and it is approved |

These are independent. A schema migration changes the encoding of a document, not what the business decided, so it does not touch component pins or the revision.

## Migration contract

`migrate(blueprint, target_version=None)` is a pure function.
- Input is never mutated; work happens on a deep copy. Same input and same registry give the same output (sorted, no clocks, no randomness).
- Steps are registered per hop (`from`, `to`). One step leaves a version, so the path is a single chain. Gaps, cycles, a step that goes downward and a second step from the same version are refused.
- Versions are strict `X.Y.Z`. Malformed, unknown, future (newer than the latest registered) and downgrade requests are refused with `MIG-VER-*`. Nothing is guessed or best-effort.
- The framework, not the step, sets `meta.schemaVersion` after each hop. A step may not change `meta.revision`, `meta.id` or `meta.buildState` (`MIG-STEP-002`).
- Each hop returns a change list (JSON pointer, add, remove or replace, before and after) so a reviewer can see exactly what moved.
- Migrating a document already at the target is a no-op (idempotent) and returns a copy.
- When the target is the schema's current version, the result is run through the validator. A result that fails is refused (`MIG-VALID-001`); no partial output.

### Revision decision
A migration does not bump `meta.revision`. The revision counts approved business changes; a re-encoding is not one, and bumping it would make the diff between revisions show a change nobody decided. The cost is that two byte-different documents can share a revision, so anything that needs to detect the difference compares `schemaVersion` as well as the revision. Open question Q-86 asks whether the control plane should record a migration marker instead.

### Build state decision
Only a `draft` is migrated by default. After `owner_approved` the revision is frozen and the owner approved what they saw; changing its bytes silently would break that approval. A non-draft migration needs an explicit flag (`allow_non_draft`) and is meant for the control plane, which must then decide whether approvals reset (Q-87). Open drafts are cheap to migrate and are re-approved anyway.

## Compatibility policy

While the contract major is 0, a minor bump may break; every such bump ships a migration. From 1.0:
- Breaking (major, migration required): removing or renaming a field, changing a type, narrowing an enum or a range, making an optional field required, changing the meaning of a value.
- Compatible (minor, migration optional): a new optional field, a widened enum or range, a new optional section.
- Clarification (patch): wording, descriptions; no migration.
A document written for an older compatible version stays valid; the chain still records a step so every version is reachable.

## How a schema change must ship

One PR contains all of: the schema and its `version`; the validator update; a registered migration from the previous version (even if it only sets defaults); a fixture pair (old document, expected new document) under `services/blueprint/fixtures/`; tests that run the chain, check idempotence and validate the result; an ADR for any breaking change; the updated `CURRENT_SCHEMA_VERSION`. CI should fail when the schema version moves without a new step.

## Interaction with other parts

- Diff ([blueprint diff](../../services/blueprint/README.md)): diffs are between revisions of one schema version. Migrate both sides to the same version first, then diff; a diff across schema versions is refused rather than guessed. A migration does not create a diff entry in the change engine's history.
- Compiler: consumers pin the schema versions they support and the control plane refuses to route a Blueprint to a compiler that does not support its `schemaVersion` (contracts/README.md, rule 7). The platform migrates a draft before compiling; the compiler never migrates on its own.
- Validator: loads the schema for the target version. Today there is one schema file; selecting by version is Q-89.
- Events: a migration performed by the platform is an audited action. The event type for it is not defined yet.

## Not covered
Component manifest and other contract migrations, data migrations inside a live tenant (the change engine owns those), and downgrades.
