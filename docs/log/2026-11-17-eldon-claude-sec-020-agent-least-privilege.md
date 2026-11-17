# Session log: sec-020-agent-least-privilege

Date: 2026-11-17
Author: eldon
Tool and model: claude
Plan IDs: SEC-020

## Summary
SEC-020: drafted the agent least-privilege spec (295 lines): the agent as its own principal, effective permission as an intersection (grant, on-behalf-of user, mode, task, taint downgrade, policy row), grant record and scoping (no cross-tenant, never C4), allowlists with the prompt-injection taint downgrades, expiry with no silent renewal, revocation, owner change leading to suspension, audit identity, cost caps that fail closed, a three-level kill switch, separation of duties, delegation, break-glass, lifecycle. 44 requirements (ALP-001 to ALP-044) and 22 test and abuse cases. Eight decisions (D-1 to D-8) and five open questions are in the document. Interim rule until Q-42 is decided: an agent's owner may not approve that agent's R3 or R4 drafts.

Follow-up: adding grant id, owner id and the delegation chain to events and the Tool API is a contract change that needs an ADR (ALP-041). Evidence: one reference (the OWASP LLM "excessive agency" item) is UNVERIFIED; no numbers are given, caps and times are decisions.

Model and prompt: first run on Fable 5.2 failed (usage limit, no output); rerun by an Opus subagent from the same scoped brief (one allowed file). Orchestrator checked scope and the doc gate.

## Files touched
- docs/security/agent-least-privilege.md: new
- docs/PLAN.md: SEC-020 done

## Decisions
- Decisions D-1 to D-8 in the document; ADR needed for the event and Tool API fields (ALP-041).

## Tokens or cost
Unknown or approximate, if known.

## Next step
PLT-005, OPR-003, PLT-025 and DSC-010 must meet the ALP requirements; QA turns the abuse cases into tests.
