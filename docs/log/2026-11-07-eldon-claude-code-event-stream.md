# Session log: event-stream

Date: 2026-11-07
Author: eldon
Tool and model: claude-code; built by a Sonnet-tier sub-agent from an Opus-written brief, verified by the orchestrator (453 tests, hygiene, no unsafe calls)
Plan IDs: BPL-011

## Summary
Built the reference implementation of contract 4 (event stream): envelope and per-family schemas, type registry (62 keys), ULID, tenant-safe builder, validator with size and minimisation rules, append-only per-tenant store with sequence, dedupe, gaps and causation, redaction for model consumers, tenant export and CLI.

## Files touched
- services/blueprint/events/ (evstream package, schemas, README); services/blueprint/tests/events/ (87 tests); services/blueprint/README.md section; docs/PLAN.md: BPL-011 done.

## Decisions
- Data shapes for most event types are ASSUMED (the contract names few fields); each is marked `assumed` in schemas/types.json and must be confirmed by the first producer. Extra build.* types come from build-states.md.
- Schemas stay in the service; promoting them to contracts/events/ needs a decision. Not built: hash chain, producer authentication and type allow-lists (T55), retention, real persistence.
- The tenant-id string heuristic can false-positive on values like t_shirt.

## Tokens or cost
Unknown or approximate, if known.

## Next step
First producers (engine adapter, Operate) confirm the assumed data shapes; BRD-004 after WEB-018 acceptance; OPR rows use the redaction helper.
