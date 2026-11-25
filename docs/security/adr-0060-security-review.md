# Security review: ADR-0060 (role assignments in a regional store)

Status: final
Owner: eldon
Reviewer: Claude Fable 5.2 (a different model from the author, Claude Opus), 2026-11-22

Plan ID: GOV-066. Security review required by RULES 42 and [ADR-0035](../decisions/ADR-0035-risk-tiered-review.md) Tier 3 for [ADR-0060](../decisions/ADR-0060-role-assignments-in-regional-store.md), which supersedes [ADR-0007](../decisions/ADR-0007-identity.md) item 9. Line numbers below refer to ADR-0060 as it stood at commit `1299717` (the Proposed text, before the conditions were added).

## Verdict
**ACCEPT WITH CONDITIONS.** 3 High, 7 Medium, 4 Low.

The direction is sound: a drift baseline held inside the site it checks is no baseline (ADR-0060 line 27), and the central identity store is the wrong home (line 28). No finding argues for keeping assignments in the tenant site. But the Proposed text moves authorisation data from a per-tenant store to a shared regional one and says almost nothing about how that store is protected. Every High finding is closed by a requirement, not by a change of direction, so the conditions are written into ADR-0060 as Decision items 6 to 15. They bind the store's design ADR (still to be written, ADR-0060 item 5) and every implementation. No store may hold a real assignment until that design ADR has had its own security review.

## Scope and method
Read: ADR-0060, ADR-0007, ADR-0039 and ADR-0040 (both Proposed), ADR-0006, `contracts/tool-api.md` section 4, `contracts/engine-adapter.md` section 5.9 and `sync-members.schema.json`, [role-and-permission-mapping.md](../architecture/role-and-permission-mapping.md), and in this folder: threat-model, threat-model-contracts, agent-least-privilege, prompt-injection-defence, action-policy-table, access-policy, hosting-rules, secrets-management, data-classification.

This is a design review of a decision record. No store exists, so nothing was tested. Nothing here is a statement about running code. Legal points (PDPL and the other markets' data laws) are UNVERIFIED until counsel reviews them, as in [hosting-rules.md](hosting-rules.md) line 6. No external source was consulted.

## Findings

### High

**H1. The writers of the store are not bounded, and the stated rule is looser than the action policy.** (lines 20, 21)
- Line 21 keeps ADR-0007's wording: written "only by the membership screens or an approved chat action by a role with invite permission". [action-policy-table.md](action-policy-table.md) row AP-PERM-01 is stricter: a role change is R4, initiated by an Owner, approved by a second, different Owner or admin, never self-targeted, agents draft only, no break-glass. "Invite permission" is not that rule. A reader of ADR-0060 alone would build the weaker one.
- The store sits in the control plane's regional database (ADR-0039 line 36, ADR-0040 line 17), reached with credential S22, which is scoped per region and held by "control-plane and provisioning services" ([secrets-management.md](secrets-management.md) line 36). So the provisioning service, and anything that takes it over (T53, rated "gap"), can rewrite any tenant's roles in the region. In the tenant site the same attack needed per-site credentials. The blast radius grows from one tenant to one region and the ADR does not say so.
- There is an unlisted writer: the first owner assignment of a new tenant. No member with any permission exists yet, so provisioning must write it (ADR-0040 lines 25 and 26). Line 21 says "only" and is already false.
- A chat-initiated role change is the privilege-change goal G-C in [prompt-injection-defence.md](prompt-injection-defence.md) line 37. Nothing in the ADR says the write path refuses agent and model principals.
- Condition: Decision item 6.

**H2. Tenant isolation inside a shared store is not stated; "authorisation stays in the tenant" now rests on a key column.** (lines 7, 20)
- The ADR says "regional" and "in the tenant's region" and nothing about partitioning. Hosting rules give each tenant its own site, database, storage prefix and keys, and list the control plane as shared ([hosting-rules.md](hosting-rules.md) line 12). After this ADR the most sensitive authorisation fact sits in the shared part.
- Missing: every row keyed by the platform-generated `tenantId`; the tenant for every read taken only from the verified token (ADR-0007 item 3), never from a request; isolation enforced by the store itself, not only by application code (compare the residual risk recorded for application-only tenant guards in secrets-management line 84); cache and idempotency keys that include the tenant (T38, T54); cross-tenant negative tests (SEC-004, T50).
- A wrong-tenant read here is not a data leak. It is tenant A's role set applied to a call in tenant B.
- Condition: Decision item 7.

**H3. `syncVersion` protects against replay only while both ends keep their counters, and the ADR protects neither.** (lines 7, 11, 17)
- The contract rejects a version not above the last applied (`engine-adapter.md` ADP-C-063). That check is only as good as the two numbers behind it.
- Store side: a restore of the store from backup returns an older assignment set and an older counter. Revoked roles come back and the store then issues version numbers it has already issued, with different content. Daily backups are a hosting rule (line 15), so this is an expected event, not an attack.
- Site side: the last-applied version lives in the tenant database. A site restore lowers it, and an old snapshot, held or captured by anyone on the service channel, becomes acceptable again.
- Binding: nothing ties a snapshot to its tenant and version. "Authenticated service channel only" (mapping doc line 14) authenticates the sender, not the content. A snapshot for tenant A at version 9 must not be deliverable to tenant B, or be altered in transit by a compromised intermediary.
- Allocation: the version must be allocated by the store in the same transaction as the write it describes, per tenant, never reused, never chosen by the caller (ADR-0039 line 48 says the adapter never invents one; the store's side is unstated).
- Condition: Decision item 8.

### Medium

**M1. Deny on outage is stated for reads only.** (lines 21, 32)
- "A failed lookup denies" does not define failure. Timeout, partial or malformed answer, a version or integrity mismatch and an unreachable store must all deny. An empty role set is a valid answer and also denies (no default role).
- No fallback to the engine copy may ever exist, including as an "emergency" switch. Line 32 says so in Consequences; it belongs in the Decision.
- Outage also blocks writes, so a role cannot be revoked while the store is down. The kill path must not depend on the store: membership removal, suspension and the session-version bump live in identity (ADR-0007 items 10 and 13) and must keep working.
- A regional store outage locks out every tenant in the region. That is the correct failure, and it makes the store a denial-of-service target that needs an uptime target and a runbook, as ADR-0007 required of identity.
- Condition: Decision item 9.

**M2. Per-request read against a possible cache.** (line 21)
- Line 21 says the gateway reads "per request". ADR-0039 line 41 allows a "cached role set" up to "its maximum age", and that age is open decision D-2 (proposed 0). The two texts disagree and the accepted one should win explicitly.
- A read replica that lags is a cache by another name: a revocation must be visible to the next request.
- A role check done when an approval is requested is stale at execution; the action policy already voids on role loss (action-policy-table line 75) and the store read must happen again at execution.
- Condition: Decision item 10.

**M3. Drift: which side wins is implied, and the window between write and sync is undefined.** (lines 20, 21, 31)
- Line 20 calls the store authoritative and the engine a copy, but no line says the engine is never used to repair the store. A reconciliation that "heals" the store from the site would reintroduce the weakness this ADR removes.
- ADR-0007 item 9 said the shadow user is re-synced "immediately" so "the engine never enforces a stale copy". Line 21 dropped "immediately". Between a revocation in the store and a completed sync, the engine still holds the wider role. The gateway denies first, but any engine path not behind the gateway (background jobs, agent principals, a gateway defect: T36) sees the stale grant.
- A failed sync after a narrowing write has no stated outcome.
- Condition: Decision item 11.

**M4. No audit requirement for role changes.** (whole Decision)
- The ADR moves the record of who holds which role and does not say that changes to it are audited. AP-PERM-01 names binding fields (target user, roles before and after, scopes); T56 requires append-only, hash-chained audit.
- The store also needs its own history, so the assignment set at any `syncVersion` can be reconstructed for an investigation or a drift dispute.
- Condition: Decision item 12.

**M5. Staff and break-glass reach.** (line 20)
- In the tenant site, changing a role by hand needed that site's break-glass credentials (S06, S08: two founders, time box, tenant notified). In a control-plane database it needs S22 or database administration, which today carries none of those controls for this purpose.
- Platform break-glass "never ... changes permissions inside a tenant's books" (action-policy-table line 138). The ADR should say that holds for the store, and that support access is never granted by writing a member's role row.
- With two founders, requester and approver can be the same person (T52). A hand edit should at least be detectable.
- Condition: Decision item 13.

**M6. Residency: "regional" is weaker than "in-country", and the store holds personal data.** (line 20)
- Line 20 says "in the tenant's region" and cites ADR-0006, which says in-country. Hosting rules place only KSA and UAE tenants (line 11); nothing is written for Egypt and Qatar. Whether an in-country location exists for each of the four markets is UNVERIFIED, and a "region" that serves two countries would move one country's data abroad.
- Which member holds which role in which company is personal data about an identifiable person. `sync_members` also carries `displayName`, marked personal data in the schema. Backups, replicas and logs of the store follow the same placement.
- A person with memberships in two countries (the accountant case) has rows in two stores. They must never be joined or replicated across countries, and the store should hold opaque per-tenant member references only, so that it does not become a second copy of the identity store whose location is still open (Q-14).
- Legal conclusions are UNVERIFIED until counsel reviews them.
- Condition: Decision item 14.

**M7. Lifecycle and deletion do not mention the store.** (line 20; ADR-0007 item 13)
- ADR-0007 item 13 removes a member's access on removal. ADR-0040's deletion step lists what is destroyed with a tenant (line 47) and the assignment store is not in the list; the control-plane database is described as what survives (line 17).
- Assignment rows must go when a member is removed and when a tenant is deleted, with only the audit trail kept under the retention rules.
- Condition: Decision item 14.

### Low

**L1. Agent grants are in the store by ADR-0039 and out of scope by ADR-0060.** (lines 11, 20, 23) Line 11 quotes ADR-0039: "member-to-role and agent-grant assignments". Item 1 moves only member-to-role. If agent grants and support principals are later stored there, the same conditions must apply and their writers differ. Condition: Decision item 15.

**L2. The contract still says "from identity".** (line 22) Until GOV-065 lands, `contracts/tool-api.md` line 100 tells an implementer to read roles from identity. Item 3 handles the reading; the condition adds that no role-read code is built against the store before GOV-065. Condition: Decision item 15.

**L3. The store must validate what it accepts.** (line 21) ADR-0039 places `scope_conflict` rejection (line 32) and `unknown_role` (line 40) partly at the store. Those rules are in a Proposed ADR. A store that accepts a role id absent from the applied Blueprint revision, or a mixed-scope pair, fails open in the engine. Condition: Decision item 6.

**L4. Accepted before anything it relies on.** (lines 24, 37) The supersession takes effect on acceptance, while the store's design, ADR-0039 and ADR-0040 are all still Proposed or unwritten. Between now and then no accepted text says where assignments live in practice. This is safe only if nothing stores real assignments in that gap. Condition: Decision item 15.

## Points the review was asked to cover
| Point | Result | Finding |
|---|---|---|
| Who writes the store | Not bounded; looser than AP-PERM-01; unlisted bootstrap writer | H1, L3 |
| `syncVersion` integrity | Replay check exists in the contract; rollback and binding unprotected | H3 |
| Per-tenant keying (ADR-0007 item 2) | Not stated | H2 |
| Deny on outage | Stated for reads; failure not defined; revocation path and availability missing | M1 |
| Tenant isolation, cross-region residency | Isolation not stated; "region" weaker than "in-country"; UNVERIFIED legal points | H2, M6 |
| Drift between store and engine | Store wins by implication only; sync window undefined | M3 |
| Caching and staleness | Conflicts with ADR-0039 item 7 and open D-2 | M2 |
| Audit of role changes | Absent | M4 |
| Break-glass and support access | Absent; controls weaker than the tenant-site case | M5 |
| Failure modes | Backup restore, failed sync, lifecycle | H3, M3, M7 |

## Residual risk after the conditions
- The store is a regional high-value target, like the identity store. Compromise of the single write path, or of the store's own administration, changes roles for every tenant in that country. The conditions make this detectable and narrow the principals; they do not remove it. T53 (control-plane compromise) should be re-rated when the store is designed.
- With two founders, separation of duties for platform-side access stays weak (T52).
- The conditions are requirements on a design that does not exist. They are worth nothing until the design ADR shows how each is met and tests prove it.

## What this review does not cover
ADR-0039 and ADR-0040 themselves (they stay Proposed and need their own reviews); the store's technology and schema; the `sync_members` and `sync_principals` contract changes; any code.
