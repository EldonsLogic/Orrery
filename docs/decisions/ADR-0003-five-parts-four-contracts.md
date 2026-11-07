# ADR-0003: Five parts and four contracts

Status: Accepted
Owner: eldon
Approved by: Eldon and partner

## Context
Two founders on different AI tools need a shared map so work can run in parallel without collisions. The product is a pipeline (discover, blueprint, build, run) on a multi-tenant platform.

## Decision
The system has five parts: 1 Discovery, 2 Blueprint and Library (the spine), 3 ERP Runtime, 4 Operate, 5 Platform. Four versioned contracts hold the interfaces and live in `/contracts`: (1) Blueprint schema, (2) Component manifest, (3) Tool API, (4) Event stream. A Connector interface is separate. Contract changes need a decision record. Client build states: draft, owner_approved, team_reviewed (human gate), built_in_sandbox, simulated, live.

## Alternatives rejected
- One monolith: couples AI experiments to ledger code.
- Per-client codebases: violates ADR-0008.

## Consequences
- Parts can be built and tested against the contracts independently.
- Schema work is on the critical path (BPL-002, BPL-009).
- Every cross-part change is a contract change and needs an ADR.

## Supersedes
none
