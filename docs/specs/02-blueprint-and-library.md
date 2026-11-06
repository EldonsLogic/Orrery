# Spec 02: Blueprint and Library (Part 2, the spine)

Status: draft
Owner: unassigned
Plan IDs: BPL (plus QA, SEC)

## Purpose
Everything that turns an approved Blueprint into a safe, reversible, reusable configuration of the engine, and keeps the reusable library healthy. This is the part that makes us a product company: schema, validator, compiler, change engine, simulator, registry, component factory, reuse metrics.

## Responsibilities
1. **Blueprint schema and validator**: JSON Schema plus cross-reference rules ([schema](../../contracts/blueprint.schema.json), `x-validator-rules`).
2. **Compiler**: Blueprint to a neutral intermediate form, then through the engine adapter to engine configuration ([engine-adapter](../architecture/engine-adapter.md)).
3. **Change engine** (imported module): diff, preview, pre-execution plan gate, audited apply, rollback, declarative workflows and reports, runtime policy enforcement ([change-engine](../architecture/change-engine.md)).
4. **Simulator**: replay a month of the owner's data (or sample data) against the compiled configuration in a sandbox tenant; produce reconciliation and exception reports.
5. **Component registry and certification**: manifests, versions, compatibility matrix, levels ([component-library](../architecture/component-library.md)).
6. **Component factory**: gap to AI-drafted component request (spec, tests) to engineer review to certification to library.
7. **Reuse metrics**: autonomy rate, component reuse ratio, human hours per go-live, new components per client (strategy 08 owns targets).
8. **Branding validation** and compilation to resolved tenant tokens ([theming](../architecture/theming.md)).

## Interfaces
| Contract | Use |
|---|---|
| Blueprint schema | Owns and validates |
| Component manifest | Owns and enforces |
| [Tool API](../../contracts/tool-api.md) | Generates the per-tenant tool set from each approved revision and hands it to Operate |
| [Events](../../contracts/events.md) | Emits `blueprint.*`, `build.*`, `component.*`; consumes record events for simulation baselines |
| [Build states](../../contracts/build-states.md) | Executes sandbox build and simulation transitions |
| Engine adapter | Calls `plan`, `apply`, `rollback`, `snapshot` |

## Data owned
Blueprint revisions and diffs, change sets with inverses, compiled artifacts, simulation reports, the component registry (manifests, packages, certification evidence), component requests, reuse metrics. Per-tenant items are tenant-isolated; registry and metrics are platform data containing no customer data.

## Key behaviours
- Compile is deterministic: same Blueprint + same component versions = same output (hash recorded).
- Apply is atomic per change set; each change set stores an inverse; destructive inverses are quarantined, not executed.
- A change that touches a rigid component's parameters (`affectsLedgerOrTax`) is flagged for team review.
- Simulation cannot post to a live tenant; it runs against a clone or an empty sandbox with imported data.
- The registry refuses a component whose manifest is invalid, whose blocking tests fail, or whose licence is not recorded.
- Promotion of patterns to the library is by generalised pattern only, reviewed by an engineer; no tenant data ([component-library](../architecture/component-library.md)).

## Failure modes
| Failure | Handling |
|---|---|
| Blueprint valid but not compilable (component missing or incompatible) | Block at validation with a specific message; raise a gap or version upgrade |
| Apply fails midway | Roll back with the stored inverse; tenant stays on previous revision; `blueprint.apply_failed` |
| Simulation shows ledger mismatch | Stop; the Blueprint cannot reach `simulated`; human triage |
| Engine upgrade breaks a component | Canary tenant fails blocking tests; promotion halted; roll back ([engine-adapter](../architecture/engine-adapter.md)) |
| AI-drafted component is wrong | Never auto-published; engineer review and tests are mandatory |

## Security notes
- Known defects in the prototype change engine (CE-SEC-001..005) must be fixed before any real use.
- Compiler and change engine never execute tenant-supplied code; Blueprint contains no expressions beyond guards and named component functions.
- Registry packages are signed or hash-pinned; third-party code needs a licence record and review.
- Branding assets are untrusted files ([theming](../architecture/theming.md)).

## Open questions
1. Neutral intermediate form: invent our own or reuse an existing metadata format? (Search first; record licence.)
2. How are Blueprint diffs presented to non-technical owners in Arabic? (With Discovery/Operate.)
3. Simulation data source for tenants with no history: synthetic vs template data.
4. Registry storage: monorepo `components/` only, or packaged artifacts in a registry service?

## Acceptance criteria
**G1 (spine proven)**
- The hand-written example Blueprint validates, compiles to a fresh sandbox tenant, applies, produces a diff for a second revision, and rolls back to the first with byte-identical configuration export.
- Change engine imported as a module, renamed, with CE-SEC-001..005 fixed and tests running against a real Frappe bench in CI (not mocks).
- Manifest validation and the compatibility matrix run in CI for at least the core and ZATCA components.
- A branding section compiles to resolved tokens, and the contrast guard rejects a failing colour in a test.

**G2 (pilot-ready)**
- Pilot Blueprint goes through the human gate, sandbox build and a simulation of the pilot's real month with reconciliation reports.
- At least one new component built through the factory (request to certification), with its evidence stored.
- Autonomy rate and reuse ratio are computed for the pilot and recorded.
