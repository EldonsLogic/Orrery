# ADR-0072: Derived reorder step in the compiled artifact

Status: Proposed
Owner: eldon
Approved by: pending (Eldon decided the direction in Q-627 on 2026-11-25, in chat; partner review of this ADR and the contract patch pending)

## Context
BPL-039 (#321) compiles a base-to-target artifact with an embedded inverse. A `*.add` step carries no position, and every diff op must sit in exactly one step's `sourceOps` (at least one each) or in `skippedOps`. Without a `reorder` op in the diff, the adapter appends a new field or option, and puts a single restored one back at its former index. So a prepend, a rename in the middle of a list, or two removals (whose rollback restores two elements) cannot reach the target order. #321 refuses them with CMP-ART-001.

Eldon decided Q-627: the compiler may emit a derived reorder step that is not tied to one diff op, and the contract names the add or remove ops it reconciles. Giving `*.add` a position was rejected because it changes the bpdiff diff format that several readers use.

A partner review (Gemini) of #326 pointed out two things. The schema sets `additionalProperties: false` on `step` and `minItems: 1` on `sourceOps`, so this needs a contract change with an ADR (contracts README rule 2, ADR-0058). And engine-adapter.md 9.3 defines `impact` only over `sourceOps`.

## Decision
1. **The step.** A derived reorder is a `field.reorder` or `option.reorder` with `sourceOps: []` and a new field, `derivedFrom`. `derivedFrom` is a sorted, non-empty list of the pointers of the `add` and `remove` ops on direct children of the step's list whose position it reconciles. Only these two kinds may carry `derivedFrom`. A step may have an empty `sourceOps` only when it has `derivedFrom`, and then it must be empty. The schema enforces this with an `if`/`then`/`else` on `step`.
2. **Exactly once stays true for `sourceOps`.** Each `derivedFrom` op is also in the `sourceOps` of the step that implements it (`field.add`, `field.quarantine`, `option.add`, `option.quarantine`). `derivedFrom` does not count toward the rule. That each `derivedFrom` pointer exists and is implemented by another step is an `x-validator-rule`, checked by the compiler (`CMP-ART-004`), because JSON Schema cannot see other steps.
3. **Impact.** The step's `impact` is the highest impact (bpdiff order) of its `derivedFrom` ops. `ddlImpact` is `none` and `reversible` is true: a reorder changes metadata only. `risk` stays copied from the diff, so nothing is counted twice.
4. **Place in the 9.4 order.** The step is in phase 6 like any reorder: after the phase 5 additions, before the phase 15 quarantines. Its `order` therefore lists exactly the keys active when it runs: the target keys in target order, then the removed keys. `previousOrder` is the base keys, then the added keys. There is at most one reorder per list, so (kind, pointer) stays unique.
5. **When it is emitted.** Only when the diff has no `reorder` op for that list and the adapter's default placement misses the target in at least one direction. In that case it is emitted in both the forward artifact and the inverse. Every other artifact keeps the steps it had before, byte for byte. A list whose order changes with no `reorder` op and no membership op is still refused (CMP-ART-001), since there is nothing to derive from.
6. **Inverse.** The inverse is compiled from `invert(diff)` by the same rule, so its `derivedFrom` names the inverted ops (a forward add becomes an inverse remove). Because the step is emitted for a list in both directions or neither, compensation (5.6) always finds the inverse step at the same pointer. The inverse has the same `artifactSchema` as its forward artifact.
7. **Versions.** Compiled-artifact schema 0.2.0 (minor, additive). `artifactSchema` may be `0.1.0` or `0.2.0`, and must be `0.2.0` when any step has `derivedFrom`. The compiler writes 0.2.0 only then, so every artifact without a derived step is unchanged and an adapter that supports only 0.1.0 refuses a derived one with `unsupported_contract_version` (4.3), never misreads it. The schema `$id` and the four engine-adapter request schemas that reference it move to `compiled-artifact:0.2.0`. engine-adapter.md goes to 0.1.4 (0.1.3 is #324). Its operations and `contractVersion` are unchanged.
8. **What the adapter must do.** List `0.2.0` in `artifactSchemaVersions` only once it handles derived steps. Execute a derived reorder like any reorder. At plan time, check that `order` lists exactly the active keys of the list when the step runs, each once. If not, the plan gives `blocked` with `definition_conflict`. The fake adapter (`services/blueprint/adapter/fake.py`) does this by running the steps on a trial copy of the site.

## Alternatives rejected
- A position on `*.add` (`after` or `index`): changes the diff format and every reader of it (Q-627).
- A new step kind (`field.reorder_derived`): the adapter would need a second mapping for the same engine change. Using the existing kinds plus `derivedFrom` keeps one execution path.
- Putting the reconciled ops in the reorder's `sourceOps`: breaks the exactly-once rule that Studio and the validator rely on.
- Always emitting a reorder when membership changes: it would change every existing artifact and its hash for no gain.
- Bumping `artifactSchema` to 0.2.0 for every artifact: it would break the partner adapter (`ARTIFACT_SCHEMA_VERSIONS = ["0.1.0"]`) for changes it already handles.

## Consequences
- Prepend, rename in the middle and several removals of fields or options now compile, apply and roll back (BPL-045 tests on the fake adapter).
- Partner follow-up for the real adapter (`apps/engine`): add `0.2.0` to `ARTIFACT_SCHEMA_VERSIONS` and the active-key check of point 8, then run the conformance suite. Until then it refuses derived artifacts with `unsupported_contract_version`, and all others work as before.
- Readers that list a step's ops (Studio plan view) should show `derivedFrom` as "follows from" rather than as ops the step implements. Studio does not read `sourceOps` today.

## Supersedes
None. It amends compiled-artifact schema 0.1.0 and engine-adapter.md 9.3, 9.4 and 9.6, through the versions in point 7.
