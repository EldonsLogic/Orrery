# Session log: adapter-contracts

Date: 2026-11-07
Author: eldon
Tool and model: claude-code; contracts drafted by an Opus-tier sub-agent from an Opus-written brief, verified by the orchestrator (schemas valid, samples valid, hygiene)
Plan IDs: BPL-025,BPL-026,GOV-033

## Summary
Drafted the engine adapter contract (10 operations, 26 error codes, 70 conformance behaviours ADP-C-001..070) and the compiled-artifact contract with 3 samples, plus a contracts check script and CI job. DRAFT PR: not merged. Still needed before merge: independent security review (a reviewer run was stopped when the usage limit hit), an ADR for the contracts (contracts rule 2), and partner read. BPL-025 also still needs the in-memory fake adapter and conformance suite (brief written, not run).

## Files touched
- contracts/engine-adapter.md and contracts/engine-adapter/*.schema.json, contracts/compiled-artifact.schema.json, contracts/examples/compiled-artifact-*.json, contracts/README.md; scripts/check_contracts.py; .github/workflows/ci.yml (contracts job); docs/PLAN.md.

## Decisions
- None yet. Agent raised 12 open questions (section 16 of the adapter contract) and notes that the existing change engine applies one field per deployment, so whole change-set apply with compensation is new partner work in BPL-007.

## Tokens or cost
Unknown or approximate, if known.

## Next step
1) Independent security review of the contracts and fix findings. 2) ADR for the contracts, then merge. 3) Fake adapter and conformance suite (BPL-025). 4) Then BPL-026 and BPL-025 done, so the partner's BPL-012 and BPL-007 can build against them.
