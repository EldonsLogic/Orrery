# ADR-0062: Tool API loads the caller's roles from the regional role-assignment store

Status: Proposed
Owner: eldon
Approved by: pending. This touches auth and tenancy (Tool API section 4), so it needs a security review by a different model or founder and the partner's review before it is Accepted (AGENTS.md Security rules; ADR-0035 Tier 3).

Plan ID: GOV-065. Number note: ADR-0061 is left for SEC-024 (the store's design ADR), which another session may be writing in parallel; this ADR takes 0062.

## Context
- [ADR-0007](ADR-0007-identity.md) item 9 said Tool API section 4 step 2 ("load the caller's roles from identity") is read as "from the tenant's assignment store" and that "the wording is fixed in the next Tool API ADR".
- [ADR-0060](ADR-0060-role-assignments-in-regional-store.md) (Accepted with security conditions, GOV-066) supersedes ADR-0007 item 9: assignments live in a regional store outside the tenant site. Its item 3 reads step 2 as "from the regional assignment store" and leaves the contract edit to this ADR. Its item 9 (deny on outage) and item 10 (no stale reads, maximum cache age 0) bind every reader. The security review's finding L2 ([adr-0060-security-review.md](../security/adr-0060-security-review.md)) notes that until this lands the contract still tells an implementer to read roles from identity.
- `contracts/README.md` rule 2: any contract change needs an ADR.

## Decision
1. **Step 2 wording.** `contracts/tool-api.md` section 4 step 2 now says the gateway loads the caller's roles for the tenant from the regional role-assignment store (ADR-0060), on every call, keyed by the tenant from step 1 (the verified session, never the request; ADR-0060 item 7). Client-supplied roles stay ignored.
2. **Fail closed, stated in the step.** An unreachable store, a timeout, or a partial, malformed, other-tenant, integrity-failing or empty role set denies the call. There is no fallback to the engine copy, a cached set or a default role (ADR-0060 items 9 and 10). Step 3's existing "failure to load roles = deny" stays.
3. **Version.** Tool API 0.3.1 to 0.3.2, a patch: no tool, request, response or error shape changes, and the step only states what ADR-0007 item 9 and ADR-0060 items 3, 9 and 10 already require. `contracts/README.md` now lists 0.3.2 (it still showed 0.3.0). No code pins the Tool API document version; `toolApiVersion` (the stored set format, `0.2.0`) is unchanged.
4. **Not decided here.** The store's technology, schema, API and integrity mechanism (SEC-024 design ADR, ADR-0060 item 15); the error code a store outage returns to the caller (it is a deny; mapping it to `permission_denied` or `engine_error` is left to the gateway ADR so outages are not shown as missing permission without review). No code may read roles from the store until this ADR and the store's design ADR are Accepted (ADR-0060 item 15).

Diff: `contracts/tool-api.md` line 3 (`Version: 0.3.1` to `0.3.2`) and section 4 step 2 (line 100); `contracts/README.md` table row 3; `docs/security/threat-model-contracts.md` trust table row "Roles loaded from ... at call time" aligned to the new source.

## Alternatives rejected
- **Leave the wording and rely on ADR-0060 item 3's reading.** An implementer reading only the contract would build against identity; review finding L2 asks for the fix.
- **Minor bump (0.4.0).** Nothing in the wire format or tool definitions changes; the requirement was already binding through accepted ADRs, so this is a clarification by the README's rule 1.
- **Name the store's API or error code in the contract now.** The store is not designed yet (SEC-024); naming it early would lock a design that has not had its security review.

## Consequences
- Easier: the contract, ADR-0007 item 9 (as superseded) and ADR-0060 now say the same thing; SEC-024 and the gateway work have one source to cite.
- Harder: nothing new; the store on the authorisation path was already accepted in ADR-0060.
- Must be done: security review of this ADR by a different model and the partner's review; SEC-024 store design ADR; gateway implementation only after both are Accepted.

## Supersedes
none. (ADR-0007 item 9 is already superseded by ADR-0060; this ADR carries out ADR-0060 item 3.)
