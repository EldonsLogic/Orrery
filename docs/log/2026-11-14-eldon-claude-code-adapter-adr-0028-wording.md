# Session log: adapter-adr-0028-wording

Date: 2026-11-14
Author: eldon
Tool and model: claude-code / sonnet-5-5
Plan IDs: BPL-025,BPL-026

## Summary
Reworded the draft adapter and build-states contracts from "atomic apply and inverse for every change" to the journaled, recoverable apply of ADR-0028 (Proposed). Wording only: no schema, step or test id changed.

## Files touched
- `contracts/engine-adapter.md`: principle 6 and the recovery paragraph reworded; added the four change classes (this contract covers classes 1 and 2 only); version 0.1.1.
- `contracts/build-states.md`: rollback rules 2 and 4 reworded (compensate where an inverse exists, otherwise `recovery_required`).
- `contracts/README.md`: adapter version 0.1.1.

## Decisions
- None new; follows ADR-0028, which is still Proposed. `check_contracts.py` passes (15 schemas); docs gate 0 errors. Not changed: the fake adapter and conformance suite do not exist yet.

## Tokens or cost
Unknown.

## Next step
BPL-025: build the in-memory fake adapter and the conformance suite (`services/blueprint/adapter`). Classes 3 and 4 need their own durable-operation contract. PR 40 stays a draft until an independent security review.
