# ADR-0075: Compiler orders entity steps by Link target

Status: Accepted
Owner: eldon
Approved by: the partner proposed it in Q-691 (PR #389, merged); Eldon agreed in his review of #389 and asked for BPL-051

## Context
The partner's real-bench run (#381, BPL-046) failed at step 57: contract 9.4 sorted steps by (phase, pointer, kind), so `entity.add /entities/sales_order`, which has a Link field to `sales_quote`, ran before `entity.add /entities/sales_quote`, and the engine refuses a Link to a document type that does not exist yet (Q-691).

## Decision
- Within phase 4 the compiler orders `entity.add` steps so that every Link target added in the same phase comes first: Kahn's algorithm, smallest ready pointer first. A Link is a field or relation with a `target` (the adapter creates both as Links).
- A self-link adds no order and is not a cycle. A Link to an entity that already exists or is added in an earlier phase adds no order.
- A Link cycle among entities added in phase 4 refuses the compile with `CMP-ART-007`, one issue per entity on the cycle. If a real Blueprint needs one, a row will split the closing Link into a later `field.add`.
- Within phase 16 `entity.quarantine` runs in the reverse order (dependants first), so a rollback removes dependants first. A quarantine cycle (possible only when an earlier revision closed it with a later `field.add`) is broken at the smallest remaining pointer, because quarantine keeps the storage.
- Every other step keeps the 9.4 sort; steps with no Links among new entities keep today's order and content hashes. The contract version stays 0.1.0: the change only reorders steps that the engine could not apply before.
- The adapter-side stable refusal for a missing Link target at execute stays with the partner (BPL-033).

## Alternatives rejected
- Add every new entity before any of its fields: it splits each `entity.add` into two steps, so a step is no longer atomic and every step shape changes.
- Keep pointer order and let the adapter defer Links: it hides the dependency inside the engine and makes the plan view wrong.

## Consequences
The golden fixture's phase 4 steps move (24 steps; same set, new seq numbers), so its artifact hash changes. BPL-051 implements this in `services/blueprint/compiler/steps.py`; contract text in `contracts/engine-adapter.md` 9.4 and `contracts/compiled-artifact.schema.json`.

## Supersedes
none (amends the 9.4 sort order recorded with ADR-0057 Q-51)
