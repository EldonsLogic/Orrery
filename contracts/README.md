# Contracts

Status: draft
Owner: eldon

The contracts are the source of truth for how the five parts of the platform talk to each other. Code, prompts and docs follow the contracts, not the other way round. Architecture context: [overview](../docs/architecture/overview.md).

| # | Contract | File | Version |
|---|---|---|---|
| 1 | Blueprint schema | [blueprint.schema.json](blueprint.schema.json) | 0.1.0 |
| 2 | Component manifest | [component.manifest.schema.json](component.manifest.schema.json) | 0.1.0 |
| 3 | Tool API | [tool-api.md](tool-api.md) | 0.1.0 |
| 4 | Event stream | [events.md](events.md) | 0.1.0 |
| - | Connector interface | [connector-interface.md](connector-interface.md) | 0.1.0 |
| - | Build states | [build-states.md](build-states.md) | 0.1.0 |
| - | Engine adapter (operations, errors, conformance; schemas in [engine-adapter/](engine-adapter/)) | [engine-adapter.md](engine-adapter.md) | 0.1.0 |
| - | Compiled artifact | [compiled-artifact.schema.json](compiled-artifact.schema.json) | 0.1.0 |

Example: [examples/blueprint-trading-minimal.json](examples/blueprint-trading-minimal.json) (fictional data; must always validate against the schema).
Compiled-artifact samples: [examples/compiled-artifact-add-field.json](examples/compiled-artifact-add-field.json), [examples/compiled-artifact-add-workflow-state.json](examples/compiled-artifact-add-workflow-state.json), [examples/compiled-artifact-remove-field.json](examples/compiled-artifact-remove-field.json) (fictional; built from the example Blueprint with bpdiff hashes).

## Rules
1. **Versioning.** Every file carries a `version` (JSON files: top-level `version`; Markdown files: the `Version:` line). Semantic versioning: patch = clarification, minor = backward-compatible addition, major = breaking change. While the major is 0, minor bumps may break; say so in the ADR.
2. **Changes need an ADR.** Any change to a contract needs a decision record in [docs/decisions/](../docs/decisions/) that links the diff. Patch-level wording fixes are exempt.
3. **Examples travel with schemas.** A schema change that breaks the example must fix the example in the same PR. CI validates every example against its schema (JSON Schema draft 2020-12).
4. **Tooling note.** The schemas use a top-level `version` and an `x-validator-rules` annotation. Strict validators (for example Ajv strict mode) must register them as known keywords or run with `strict: false`.
5. **Names.** The `$id` values are `urn:platform:contract:*`, so renaming the product never touches a contract.
6. **No customer data** in any example. Fictional names only.
7. **Consumers pin.** Services declare the contract versions they support; the control plane refuses to route a Blueprint to a compiler that does not support its `schemaVersion`.

## What is not a contract
Internal service APIs, database tables and prompts are implementation. If two parts depend on it, promote it to a contract here.
