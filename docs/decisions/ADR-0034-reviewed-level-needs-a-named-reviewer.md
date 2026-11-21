# ADR-0034: a "reviewed" component names its reviewer

Status: Accepted
Owner: eldon
Approved by: partner (sayegh9, 2026-11-19; cross-model security review via Gemini 4 Neon high; follow-up in Q-297); Eldon recorded review on PR #183

## Context
Q-19 (answered by the founder on PR #48, 2026-11-14): a manifest must never say "reviewed" when nobody reviewed it. Today `contracts/component.manifest.schema.json` requires `reviewedBy` only from `certified`, and forces any component with `touchesLedgerOrTax: true` to be at least `reviewed`. A tax component waiting for its first review (the ZATCA Phase 1 component in #43) can therefore only be written as "reviewed" with an empty `reviewedBy`. ADR-0031 condition 2 needs a named human who read rigid-zone code line by line; the manifest should record that person.

## Decision
- `reviewedBy` must list at least one GitHub login at levels `reviewed`, `certified` and `regulated`.
- A component that touches the ledger or tax may be at `tested` while it waits for review (sandbox only, per the certification table). `draft` is still refused for it. No new level is added.
- Moving to `reviewed` is a recorded review (ADR-0032) by a founder who did not write or prompt the code; the login in `reviewedBy` is that reviewer.
- **Production boundary (fail closed):** only `certified` and `regulated` components are production eligible; `tested` and `reviewed` are sandbox only; `draft`, an unknown level and an unknown environment are never eligible. The registry enforces this in `Registry.eligible(environment)` and `is_eligible` (tested in `test_registry_admission.py`). The compiler and any tenant publish path (BPL-027, ERP-012) must call it; no production compiler exists yet, so that call is a requirement on those rows, not something already enforced end to end.
- The schema cannot check that the reviewer differs from the author. The registry or CI check for that is a follow-up.

## Alternatives rejected
- A new `awaiting_review` level: adds an ordering the registry and compiler would have to learn, for the same effect as `tested` plus "sandbox only".
- Leave the schema and rely on the log: the manifest is the record the compiler reads, so it must be correct itself.

## Consequences
- The manifest of any tax component currently written as `reviewed` with no reviewer (#43) moves to `tested` until it is reviewed. That manifest is in the partner's lane; the PR for ADR-0034 does not touch it.
- Existing registry fixtures already name reviewers; the Blueprint registry tests pass unchanged (plus two new tests).
- Follow-ups: author-not-reviewer check; reword the `rigid` description and the RULES 21 / AGENTS.md wording (ADR-0031 follow-ups).
- Plan: BPL-014.

## Supersedes
None. Amends the certification rule in `docs/architecture/component-library.md`.
