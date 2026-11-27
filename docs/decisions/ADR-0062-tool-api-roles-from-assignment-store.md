# ADR-0062: Tool API loads the caller's roles from the regional assignment store

Status: Accepted
Owner: eldon
Approved by: Eldon's decision, 2026-11-22 (relayed by the orchestrator session), with the conditions of the security review folded in below. Security review by a different model (Claude Fable 5.2): ACCEPT WITH CONDITIONS, recorded as a comment on PR #276; condition C1 and Lows L1-L5 are applied in this ADR and Tool API 0.3.2. The partner's review of PR #276 is the second founder's record (ADR-0032 item 2; ADR-0035 Tier 3).

Plan ID: GOV-065. Number note: ADR-0061 is left for SEC-024 (the store's design ADR), which another session may be writing in parallel; this ADR takes 0062.

## Context
- [ADR-0007](ADR-0007-identity.md) item 9 said Tool API section 4 step 2 ("load the caller's roles from identity") is read as "from the tenant's assignment store" and that "the wording is fixed in the next Tool API ADR".
- [ADR-0060](ADR-0060-role-assignments-in-regional-store.md) (Accepted with security conditions, GOV-066) supersedes ADR-0007 item 9: assignments live in a regional store outside the tenant site. Its item 3 reads step 2 as "from the regional assignment store" and leaves the contract edit to this ADR. Its item 9 (deny on outage) and item 10 (no stale reads, maximum cache age 0) bind every reader. The security review's finding L2 ([adr-0060-security-review.md](../security/adr-0060-security-review.md)) notes that until this lands the contract still tells an implementer to read roles from identity.
- `contracts/README.md` rule 2: any contract change needs an ADR.

## Decision
1. **Step 2 wording.** `contracts/tool-api.md` section 4 step 2 now says the gateway loads the caller's roles for the tenant from the regional assignment store (ADR-0060), on every call and again when a parked call executes after approval (section 5; ADR-0060 item 10), keyed by the tenant from step 1 (the verified session, never the request; ADR-0060 item 7). Client-supplied roles stay ignored. The step covers member callers only; ADR-0060 item 15 moved member-to-role assignments only. Step 2 links this ADR and says the store is not built and no code reads it before its design ADR is Accepted (ADR-0060 item 15), so the contract alone is never read as permission to build.
2. **Fail closed, stated in the step.** An unreachable store, a timeout, or a partial, malformed, other-tenant, integrity-failing or empty role set denies the call. There is no fallback to the engine copy, a cached set or a default role, and no switch that enables one (ADR-0060 item 9). A read that may lag a committed write (for example an asynchronous replica) counts as a cached set and is not allowed (ADR-0060 item 10, maximum age 0). A role id not in the applied Blueprint revision grants nothing; a set with only such ids is empty and denies (ADR-0039 item 7). Step 3's existing "failure to load roles = deny" stays.
3. **Version.** Tool API 0.3.1 to 0.3.2, a patch: no tool, request, response or error shape changes, and the step only states what ADR-0007 item 9 and ADR-0060 items 3, 9 and 10 already require. `contracts/README.md` now lists 0.3.2 (it still showed 0.3.0). No code pins the Tool API document version; `toolApiVersion` (the stored set format, `0.2.0`) is unchanged.
4. **Not decided here.** The store's technology, schema, API and integrity mechanism (SEC-024 design ADR, ADR-0060 item 15); the error code a store outage returns to the caller (it is a deny; mapping it to `permission_denied` or `engine_error` is left to the gateway ADR, tracked as Q-584); where agent grants and support grants are loaded from (agent-least-privilege.md, PLT-019; ADR-0060 item 15). No code may read roles from the store until this ADR and the store's design ADR are Accepted (ADR-0060 item 15).

Diff: `contracts/tool-api.md` line 3 (`Version: 0.3.1` to `0.3.2`) and section 4 step 2 (line 100); `contracts/README.md` table row 3; `docs/security/threat-model-contracts.md` trust table row "Roles loaded from ... at call time" aligned to the new source.

## Alternatives rejected
- **Leave the wording and rely on ADR-0060 item 3's reading.** An implementer reading only the contract would build against identity; review finding L2 asks for the fix.
- **Minor bump (0.4.0).** Nothing in the wire format or tool definitions changes; the requirement was already binding through accepted ADRs, so this is a clarification by the README's rule 1.
- **Name the store's API or error code in the contract now.** The store is not designed yet (SEC-024); naming it early would lock a design that has not had its security review.

## Consequences
- Easier: the contract, ADR-0007 item 9 (as superseded) and ADR-0060 now say the same thing; SEC-024 and the gateway work have one source to cite.
- Harder: nothing new; the store on the authorisation path was already accepted in ADR-0060.
- Done: security review by a different model (Fable 5.2, PR #276), conditions applied.
- Must be done: the partner's review of PR #276; Q-584 (outage error code); SEC-024 store design ADR; gateway implementation only after both are Accepted.

## Supersedes
none. (ADR-0007 item 9 is already superseded by ADR-0060; this ADR carries out ADR-0060 item 3.)
