# ADR-0075: Compiler orders entity steps by Link target

Status: Accepted
Owner: eldon
Approved by: the partner proposed it in Q-691 (PR #389, merged); Eldon agreed in his review of #389 and asked for BPL-051

## Context
The partner's real-bench run (#381, BPL-046) failed at step 57: contract 9.4 sorted steps by (phase, pointer, kind), so `entity.add /entities/sales_order`, which has a Link field to `sales_quote`, ran before `entity.add /entities/sales_quote`, and the engine refuses a Link to a document type that does not exist yet (Q-691).

## Decision
- Within phase 4 the compiler orders `entity.add` steps so that every Link target added in the same phase comes first: Kahn's algorithm, smallest ready pointer first.
- **Hard edges** are fields of type `link`, by their `target`: the adapter creates them with the entity, so the target type must exist. No other field type is a Link, even with a `target`.
- **Soft edges** are relations (reference, child table, many-to-many), by their `target`. The adapter does not create inline relations on `entity.add` (only `relation.add` does; partner review of #391), so a relation is an ordering preference only. Soft edges are taken in pointer order, and one that would close a cycle is dropped. A relation never splits or refuses anything.
- **No edge** comes from a self-link, a link to an entity that already exists or is added in an earlier phase, or a link into a built-in type. A built-in type is an entity listed in `contracts/engine-builtin-entities.json` (0.1.0). The list is copied from the adapter's entity table (`ENTITY_TO_DOCTYPE`), because no compiler-side source covers every built-in type: one compile gets one engine mapping, and each mapping covers only part of them. That type exists before any step runs. Q-722 asks the partner to own the list or expose it in the mapping contract.
- **A hard cycle among new entities is split, not refused.** While a hard cycle remains, the Link field on a cycle with the smallest pointer leaves its `entity.add` definition and becomes a phase 5 `field.add`. When appending the moved fields would leave the entity's fields out of Blueprint order, a phase 6 `field.reorder` puts them back in order. The split always succeeds: each move removes one hard edge, and a graph with no hard edges has no cycle. So `CMP-ART-007` is removed. An initial compile without a base (Studio) succeeds, and so does a rebuild. The new steps implement the same diff op, so they repeat the `entity.add`'s `sourceOps`. This is the one exception to "every op exactly once" (contract 9.3).
- **Plan judges in order.** Contract 5.3 now says each step is judged against the site as the steps before it in the same artifact leave it. Without that rule, a `field.add` on an entity the artifact adds would be `subject_missing`. The fake adapter does this. The real adapter's plan (`engine.py` `_judge`) still judges against the live site and refuses a split cycle as `subject_missing`. That refusal fails closed and is stable. The partner's change is asked in Q-722.
- **Removal order.** Within phase 16, `entity.quarantine` uses the same edges reversed (dependants first). It is a reverse-edge sort with pointer ties, not a mirror of the add order. A quarantine cycle is broken at the smallest remaining pointer, because quarantine keeps the storage. The inverse of that removal restores the same entities with `entity.add`. Its cycle is broken by pointer too and is never split. The reason is that a restore re-activates a stored entity: the fake adapter reinserts the retained definition, and the real adapter keeps the custom type (for a built-in type it only unhides the fields). So every Link target already exists. Only an inverse counts as a restore.
- Every other step keeps the 9.4 sort. The order changes wherever a Link or relation joins two new custom entities, wherever a link into a built-in type used to add an order, and wherever a cycle is split. That includes artifacts the engine could apply before. The change is therefore versioned: engine adapter contract 0.1.4. `artifactSchema` stays 0.1.0, because no shape changes.
- The adapter-side stable refusal for a missing Link target at execute stays with the partner (BPL-033).

## Alternatives rejected
- Add every new entity before any of its fields: it splits each `entity.add` into two steps, so a step is no longer atomic and every step shape changes.
- Keep pointer order and let the adapter defer Links: it hides the dependency inside the engine and makes the plan view wrong.
- Refuse a hard cycle (`CMP-ART-007`) and ask for the closing Link in a later revision: a compile without a base refuses it again, so Studio cannot rebuild the revision (partner review of #391).
- Treat relations as hard edges: the adapter creates no Link for them on `entity.add`, so they refused Blueprints the engine can apply (a header with child lines whose line links back to the header).
- Read the built-in types from the compile's engine mapping: each mapping covers only part of the built-in types (golden path or purchasing), so a compile with one mapping would still order links into the other part's types.

## Consequences
The golden fixture's phase 4 steps move again: same 24 steps, new seq numbers. Its artifact hash is `sha256:e61c1586...` on main, `sha256:028eba82...` at #391 4fb365aa, and `sha256:e211deb7...` now. With relations made soft alone, the hash stays `028eba82` (pinned by a test). It moves because links into built-in types no longer add order. BPL-051 implements this in `services/blueprint/compiler/steps.py` and the fake adapter's plan (`services/blueprint/adapter/fake.py`). Contract text is in `contracts/engine-adapter.md` 5.3, 9.3 and 9.4, `contracts/compiled-artifact.schema.json` and `contracts/engine-builtin-entities.json`.

## Supersedes
none (amends the 9.4 sort order recorded with ADR-0057 Q-51)
