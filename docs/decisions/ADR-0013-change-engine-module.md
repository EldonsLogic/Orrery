# ADR-0013: The prototype change engine becomes a module of Part 2

Status: Accepted
Owner: eldon
Approved by: Eldon and partner

## Context
A prototype (written earlier by the partner) implements guarded configuration changes on Frappe: preview, a pre-execution DDL plan gate, an audited six-stage deploy, soft-quarantine rollback, declarative workflows and reports, and runtime policy enforcement. This is the apply, preview, rollback, audit and policy layer that Part 2 needs.

## Decision
Import it as a module called the change engine into `apps/engine/`, owned by Part 2. It is not a separate project and its old name is not used in new docs. Known security issues must be fixed before any real use: caller-supplied roles accepted from request kwargs on whitelisted endpoints; role lookup falls back to System Manager on error (fail-open); runtime-policy registration has no permission check and policies live in process memory (not persisted, per process, not per site); the LLM test-connection endpoint accepts a client-supplied API key and base URL; CI runs mocks, not a real Frappe bench; no LICENSE file. These are tracked as CE-SEC-001 to CE-SEC-005 and LEG-002.

## Alternatives rejected
- Rewrite from scratch: wastes working code.
- Keep as a separate product: splits focus; contradicts ADR-0003.

## Consequences
- Import (BPL-001) needs the founders' agreement to assign IP (LEG-001).
- G0 requires CE-SEC-001 to CE-SEC-004 done.
- Treat the module as untrusted until the fixes and real-bench CI land.

## Supersedes
none
