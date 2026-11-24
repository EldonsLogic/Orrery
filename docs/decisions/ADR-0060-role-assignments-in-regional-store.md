# ADR-0060: Role assignments live in a regional store outside the tenant site

Status: Proposed. Decided by Eldon 2026-11-22; becomes Accepted after the security review.
Owner: eldon
Approved by: pending. Decided by Eldon, answering for both founders, 2026-11-22 (Q-292), recorded in docs/log/2026-11-22-eldon-claude-code-founder-answers.md (PR #264). Q-292 and ADR-0039 line 36 need both founders: the partner's review of this PR is the second record (ADR-0032 item 2). Acceptance also needs the security review below.

Plan ID: GOV-063 (part 1). This touches auth and tenancy, so it needs a security review by a different model or founder before it is Accepted (AGENTS.md Security rules; RULES 42; Tier 3 in ADR-0035). The review should cover at least: who may write to the store; how `syncVersion` integrity is protected; per-tenant keying, so ADR-0007 item 2 ("authorisation stays in the tenant") still holds; and deny on outage.

## Context
- [ADR-0007](ADR-0007-identity.md) item 9 (line 26) stores which member holds which role "per tenant (in the tenant's site)".
- [ADR-0039](ADR-0039-role-and-permission-mapping.md) (Proposed, ERP-008) item 7 (line 36) instead puts authoritative member-to-role and agent-grant assignments in one platform store outside the engine site (the regional provisioning assignment store, versioned by a monotonic `syncVersion`), so drift checks never compare the engine with itself. It proposed superseding only ADR-0007 item 9's location wording and left ADR-0007 authoritative until both founders approved (ADR-0039 lines 36 and 77).
- [ADR-0040](ADR-0040-tenant-provisioning-service.md) (Proposed) line 26 depends on that move for `sync_members` and the drift baseline.
- Eldon answered Q-292 on 2026-11-22 for both founders ([open-questions.md](../open-questions.md) Q-292): supersede ADR-0007 item 9 so role assignments live in a regional store outside the tenant site, and the PR #129 items listed in the row are confirmed. PR #129 (ERP-008, merged 2026-11-21) carried:
  - [agent-least-privilege.md](../security/agent-least-privilege.md) section 3.1 item 2 (line 29): a separate draft-only agent engine user per agent;
  - ALP-001 (line 193): an agent never uses a human session, token or shadow engine user;
  - OQ-2 (line 277): one grant-intersected managed role per agent grant;
  - the apply/sync boundary in ADR-0039 item 8 (lines 44-48): role-touching `apply` runs `sync_members` with a new store-issued `syncVersion` under a reconciliation fence, and contract changes for that orchestration are accepted before implementation (line 46).

## Decision
1. **Location.** The authoritative record of which member holds which Blueprint role in a tenant lives in a regional assignment store outside the tenant's engine site, run by the platform in the tenant's region (customer data stays in-country, ADR-0006). The engine site holds only the copy that `sync_members` writes onto shadow users.
2. **Unchanged from item 9.** The Blueprint defines roles. Assignments are written only by the membership screens or an approved chat action by a role with invite permission. The gateway reads assignments per request from this store. The shadow engine user is re-synced on every assignment change, not only on apply. A failed lookup denies (ADR-0007 item 2, ADR-0039 item 7).
3. **Tool API reading.** Tool API section 4 step 2 ("Load the caller's roles for that tenant from identity", `contracts/tool-api.md` line 100) is read as "from the regional assignment store". This ADR does not edit the contract; the wording is fixed in the next Tool API ADR, as item 9 already required; plan row GOV-065 tracks it.
4. **PR #129 items confirmed.** The ALP section 3.1, ALP-001 and OQ-2 text in point 4 of Context, and the apply/sync boundary in ADR-0039 item 8, are confirmed as the founders' position. Contract changes they need (`sync_members` / `sync_principals`, `engine.permission_drift`) still need their own contract ADRs before implementation (ADR-0039 line 56 and line 71). This item records a confirmed position only; it accepts no part of ADR-0039, which stays Proposed.
5. **Not decided here.** The store's technology, schema and deployment; how it relates to the central identity store across four markets (Q-14 stays open); whether ADR-0039 and ADR-0040 are accepted (they stay Proposed and follow their own review).

## Alternatives rejected
- **Keep assignments in the tenant site (ADR-0007 item 9 as written).** The drift check would compare the engine with data in the same site, so a compromise or bug in the site could rewrite both sides (ADR-0039 item 7).
- **Keep them in the central identity store.** ADR-0007 item 1 keeps that store free of tenant authorisation data, and its location across markets is still open (Q-14).

## Consequences
- Easier: drift baselines are independent of the engine site; ERP-008 and PLT-003 can implement the external store once their ADRs are accepted and reviewed.
- Harder: one more regional service on the authorisation path; its outage must deny, not fall back (ADR-0039 item 7).
- Must be done: a security review of this ADR by a different model or founder, recorded on the PR, before it is Accepted and before any implementation (RULES 42); the Tool API ADR fixing section 4 step 2 wording (GOV-065); contract ADRs for the `sync_members` extension. Q-292 is marked applied once this ADR is Accepted.
- No contract file changes in this ADR.

## Supersedes
[ADR-0007](ADR-0007-identity.md) item 9 only (line 26), "Where the person-to-role assignment lives": the location "in the tenant's site" is replaced by the regional assignment store above. Items 1 to 8 and 10 to 13 of ADR-0007 stand unchanged. Effective once this ADR is Accepted; until then ADR-0007 item 9 stays authoritative.
