# Session log: bpl-025-fake-adapter

Date: 2026-11-14
Author: eldon
Tool and model: claude-code / sonnet-5.5
Plan IDs: BPL-025

## Summary
Built the in-memory fake of the engine adapter (all ten operations, journaled recoverable apply of ADR-0028, idempotency, per-site lock, tenant from context only, fail closed) and the conformance suite: one pytest test per ADP-C-001 to ADP-C-070, run through an `AdapterHarness` so the real adapter (BPL-012, ERP-012) can run the same tests via `ADAPTER_HARNESS=module:factory`. 193 adapter tests and the whole `services/blueprint/tests` suite pass (615). Nothing here is verified on an engine (UNVERIFIED). Branch `bpl-025-fake-adapter` is cut from `bpl-025-026-adapter-contracts` (PR 40, draft); not committed or pushed.

## Files touched
- `services/blueprint/adapter/`: `fake.py` (the fake), `contract.py` (canonical JSON, hashes, schema loading), `harness.py` (`AdapterHarness`, `FakeHarness`, `make_harness`), `testkit.py` (contexts, sealing, an initial-build stand-in for the compiler, derived artifacts), `README.md`.
- `services/blueprint/tests/adapter/`: `conftest.py` (wrapper that schema-checks, error-shape-checks and leak-scans every response of every test), six `test_adp_*.py` files, `test_fake_selfcheck.py`, `golden_export_hashes.json` (ADP-C-060).
- `docs/open-questions.md`: Q-32 to Q-35.
- `docs/PLAN.md`, `docs/STATUS.md`: BPL-025 stays `doing` (the contract is still a draft; see Next step); status regenerated.
- Checked the suite is not vacuous: four deliberate breaks of the fake (skipped compensation restore, no plan-token check, no lock, quarantine under the wrong key) each failed it.

## Decisions
- No ADR. Choices inside the fake, all open for review: snapshot-per-step journal for compensation (the real adapter cannot snapshot an engine); `role.*` kinds `gated` and `binding.*` `unsupported` so ADP-C-028 is exercised; a second version set so ADP-C-016 and ADP-C-021 have a supported-but-different target; a rollback "rolls back to" the previous applied record (history stack), so `site.applied` is again the artifact the site now matches.
- Contract ambiguities found while building (Q-32 to Q-35): events versus "no effect", the `exportedProperties` key pattern, the harness extensions, and where `idempotency_conflict` and `concurrent_change` sit.
- The suite needs about 2,700 lines in total, well over the 400-line PR guide. Suggested split: (1) `contract.py`, `fake.py`, `harness.py`, `testkit.py`, conftest, ADP-C-001 to 024; (2) plan, preview and apply (025 to 050); (3) rollback, export, members, events (051 to 070). The tests need the fake whole, so the first PR carries the fake.

## Tokens or cost
Unknown.

## Next step
- Review: another model or the partner reads `fake.py` against `contracts/engine-adapter.md` and answers Q-32 to Q-35; then the contract version moves to 0.1.2 if they change it.
- BPL-025 can be set `done` when PR 40 leaves draft (independent security review and an ADR, per the previous log).
- BPL-012 and ERP-012 (partner): write a harness subclass and run `ADAPTER_HARNESS=... python3 -m pytest services/blueprint/tests/adapter -q`; ADP-C-060 hashes depend on agreeing `exportedProperties` (contract 16.3).
- BPL-004 (compiler) can build against the fake now; BPL-027 joins it to the real adapter.
