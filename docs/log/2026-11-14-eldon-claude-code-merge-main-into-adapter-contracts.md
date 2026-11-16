# Session log: merge-main-into-adapter-contracts

Date: 2026-11-14
Author: eldon
Tool and model: claude-code / sonnet-5-5
Plan IDs: BPL-025,BPL-026

## Summary
Merged `main` into the BPL-025/BPL-026 draft branch (PR 40) so it no longer conflicts. The draft contracts themselves are unchanged.

## Files touched
- `.github/workflows/ci.yml`: kept both sides; the `contracts` job now sits beside `script-tests` and `dev-bench-tests`.
- `contracts/README.md`: kept the engine-mapping row and the adapter and compiled-artifact rows with their examples.
- `docs/PLAN.md`: plan ID collision. This branch's row "Contracts check script" was GOV-033, which `main` now uses for the agent working principles. This branch's row is renumbered GOV-040. The older log `2026-11-07-eldon-claude-code-adapter-contracts.md` still says GOV-033 for it (logs are append-only); read it as GOV-040.
- `docs/STATUS.md`: regenerated.

## Decisions
- None. `python3 scripts/check_contracts.py` passes (15 schemas) in the scratch venv; docs gate 0 errors; plan independence OK.

## Tokens or cost
Unknown.

## Next step
BPL-025/BPL-026: reword the draft's atomic apply and inverse wording to the recoverable, journaled apply of ADR-0028, then add the in-memory fake adapter and the conformance tests. The PR stays a draft until an independent security review and an ADR.
