# Session log: bpl-045-derived-reorder

Date: 2026-11-26
Author: eldon
Tool and model: claude-code / opus-5.5
Plan IDs: BPL-045

## Summary
Built BPL-045, stacked on #321 (BPL-039): a derived reorder step (ADR-0072, Q-627) lets a prepend, a rename in the middle and several removals of fields or options compile, apply and roll back on the fake adapter, where #321 refused them with CMP-ART-001.

## Files touched
- docs/decisions/ADR-0072-derived-reorder-step.md, docs/decisions/INDEX.md: new ADR (Proposed). ADR-0070 and ADR-0071 are reserved on open PRs; 0072 was free on main and on every open branch.
- contracts/compiled-artifact.schema.json: 0.2.0. Optional `step.derivedFrom`; empty `sourceOps` only with it, and only on `field.reorder` or `option.reorder`; `artifactSchema` 0.1.0 or 0.2.0 (0.2.0 required with a derived step); new x-validator-rules. `$id` moved to 0.2.0.
- contracts/engine-adapter/{apply,plan,preview,rollback}.schema.json: the `$ref` to the compiled artifact moved to 0.2.0 (the request schemas' own versions are unchanged).
- contracts/engine-adapter.md 0.1.4: 9.3 (derived step, impact), 9.4 (phase 6, active keys, adapter check), 9.6 (both directions), 5.4 `definition_conflict` text, changelog. contracts/README.md version table.
- services/blueprint/compiler/incremental.py: `_reaches` predicts the adapter's placement; `_reconcile_order` emits the derived reorder instead of refusing, in both directions or neither. A list order change with no membership op is still refused.
- services/blueprint/compiler/artifact.py: `artifactSchema` 0.2.0 only with a derived step; check of the derivedFrom and inverse-schema x-validator-rules (CMP-ART-004).
- services/blueprint/adapter/fake.py: accepts artifact schema 0.2.0; at plan time a reorder whose `order` is not exactly the active keys is `blocked` with `definition_conflict` (trial run of the steps).
- services/blueprint/tests/compiler/test_cmp_derived_reorder.py (new, 14 tests); test_cmp_incremental.py (the refusal test that this row replaces is removed); tests/adapter/test_fake_selfcheck.py (the schema URN).
- docs/PLAN.md: BPL-045 row added as `doing` (the row is on main, but this branch is cut from #321, which predates it).

## Decisions
- ADR-0072 (Proposed). Choices made here are inside Eldon's Q-627 answer. The existing reorder kinds are reused, not a new kind. `artifactSchema` is 0.2.0 only for artifacts that use the step, so the partner adapter stays compatible and fails closed on derived ones. engine-adapter.md is a patch (0.1.4), so `contractVersion` negotiation is unchanged.

## Checks
- services/blueprint/tests: 2169 passed. services/studio/tests: 70 passed. apps/engine adapter tests (BPL-012, BPL-027, read only): 17 passed, 10 skipped.
- check_contracts: OK (17 schemas). check_docs, check_repo_hygiene, check_plan_independence: see the PR.

## Tokens or cost
Unknown.

## Next step
- Partner follow-up (apps/engine): add `0.2.0` to `ARTIFACT_SCHEMA_VERSIONS`, add the active-key check for reorder (ADR-0072 point 8), and run the conformance suite.
- Merge order: #321, then this PR. #324 (engine-adapter 0.1.3) touches the same 9.3, 9.4 and changelog lines, so whichever merges second resolves them. The BPL-045 PLAN row conflicts with main's `todo` row when #321 merges main; keep `doing`.

## Review follow-up (BPL-045)
- Merged origin/main (#321 base, #324 BPL-037) into the branch. Conflicts resolved: engine-adapter 0.1.4 (changelog kept in order after 0.1.3; the 9.4 paragraph keeps the 0.1.3 uniqueness key and the derived-reorder phase text); fake.py advertises contract 0.1.4 and artifact schema 0.1.0 and 0.2.0; PLAN.md takes main's rows, BPL-045 stays `doing`.
- compiled-artifact schema: `derivedFrom` is `uniqueItems`. New schema test rejects a duplicate pointer.
- New compiler test: an inverse with two restores in one list (remove supplier_code and vat_number) carries a derived reorder whose `order` is the base order. The same edit joins the parametrized compile and fake apply/rollback tests.
- Mutation check: the multi-restore branch of `_reaches` removed, 3 tests fail (the new inverse test, the new fake round-trip and the position-change test). Reverted.
- Checks: check_contracts OK; blueprint 2447 passed; studio 70 passed; check_docs, check_repo_hygiene, check_plan_independence OK.
