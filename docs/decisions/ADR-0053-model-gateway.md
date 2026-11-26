# ADR-0053: Model gateway home, routing, budgets, caching and residency

Status: Proposed
Owner: partner
Original author: Eldon (#232); carried into PLT-009 by the partner with review fixes (see "Partner revision" at the end).
Approved by: pending (security review by a different model, then both founders; touches tenancy and compliance)

## Context
PLT-009 asks for the AI model gateway: routing, budgets, caching and logs. ADR-0010 already says every model call goes through our gateway. PLT-025 (partner) built tier routing, integer cost metering, fail-closed budget prechecks and `meter.ai_usage` events in `services/gateway/`, which `scripts/lanes.json` gives to the partner. Q-127 was decided as option A (GOV-058, #241): PLT-009, PLT-010, PLT-011 and PLT-021 are partner rows, and callers build against the PLT-026 contract [contracts/model-call.md](../../contracts/model-call.md) 0.2.1 (ADR-0054), which binds this design. ADR-0069 and the founders' #316 decisions set audit ownership (SEC-008), audit identity and the platform security stream. SEC-003 makes the gateway the single prompt-assembly point; ADR-0038 gives provider keys (S01) to the gateway only; SEC-020 requires no silent downgrade (ALP-034) and refusal when metering is down (ALP-032). QA-003 shows Sonnet and Opus classes clear the 0.85 Arabic gate and Haiku class does not on dates and numbers (single run, unreviewed). Design: [model-gateway](../architecture/model-gateway.md).

## Decision
1. The model gateway is `services/gateway/`, extending PLT-025; no second gateway or meter in another service. It is partner-lane work under Q-127 option A; this ADR does not move a lane or a plan row.
2. Callers ask for a tier and a purpose, never a model. A versioned routing table per tier and market lists an ordered chain of eval-admitted entries.
3. Fallback happens only on transport failure, only to a same-or-stronger, eval-admitted, region-allowed entry, and is logged; an exhausted chain fails closed.
4. Budgets nest platform >= tenant >= session >= agent grant >= run, reserved atomically. The precheck becomes a hold as in contract §6: the input is bounded by bytes, the output limit may drop but never below `min_output_tokens` (below it the call is refused), and the hold has a TTL of at least 3 times the largest per-entry `attempt_timeout` plus a margin, so no hold is released while its call can run. A reply after a TTL release leaves the hold released and is committed as a contract §6.4 overrun with an alert (reading, Q-679). Cost is committed and metered once dispatch began. PLT-009 defines a `BudgetStore` port with a local implementation; PLT-011 and PLT-021 wire the regional store and entitlements. Any missing policy, unreachable meter, failed commit, stale secret feed or unreachable kill flag refuses the call.
5. Prompt caching uses the contract §3 prefix order: L0 platform blocks (C0/C1, by reference, shared), then L1 tenant configuration behind a per-tenant marker, then conversation items. Memory is L3 and sits in that last part inside per-call delimiters. Our own response cache is platform-scoped and accepts only calls whose blocks are all L0 C0/C1; L1 is tenant configuration and never enters it. Its key is the hash of the exact bytes sent plus the decoding settings and the output limit, with the routing-table version, model id and `prompt_version` kept for invalidation. Nothing is cached across tenants.
6. Provider adapters plug in as the PLT-025 transport. Provider keys are S01 in the secret store, one per provider per market, read only by the gateway. No tenant-supplied keys in v1.
7. A region policy per market sets allowed endpoints, the highest data class and whether PD-tagged content may leave the country. Items carry `data_class` and a PD status; a missing policy refuses the call. Until a PDPC licence exists, Egypt refuses C3 and unredacted PD blocks for any endpoint outside Egypt, and C2 without PD may pass. Under contract 0.2.1, PD status cannot be read and unreadable counts as PD, so all tenant content stays in Egypt until the contract carries PD (design section 9.2). The same rule makes each other market's "PD may leave" value decide whether it gets model calls on tenant content; KSA, UAE and Qatar allow it only once that market's safeguard files are on file (design section 6). All legal readings are UNVERIFIED until LEG-012, and the per-market values await a founder decision (Q-680).
8. Logs are the existing `meter.ai_usage` event plus a content-free trace. The trace has a per-country retention period and is purged at tenant offboarding. Content capture is off by default and needs a time-limited support-access grant (PLT-019).
9. The caller interface is contract 0.2.1 as written: its seven refusal codes and closed reasons, a missing trust label refused (`invalid_request`, `missing_trust_label`, never treated as L3), L0, L1 and tools by reference only, 24 h scoped idempotency, a sticky taint record per thread, session and run, and replies stamped `trust: "untrusted"` and `tainted` with no model id. Gaps are named in the design, section 9.2, for a later contract version.
10. Audit and security events follow the #316 decisions. The gateway writes through SEC-008's `AuditStore` port and platform security stream and defines no record format. A human actor is the per-tenant `memberRef` plus `token_id`, and one audit id runs end to end, read here as `caller.correlation_id` (to be confirmed in the contract). Content-capture start is write-through.

## Alternatives rejected
- Gateway in `services/operate/` (Eldon lane): Discovery and the factory also call models; it would become a hidden second gateway with its own keys and meter.
- Gateway in `services/control-plane/`: off the hot path and widens who reads provider keys.
- New `services/model-gateway/`: duplicates or forks PLT-025 metering to avoid a lane, which is designing around the lane rule.
- Fallback to any available model: breaks evals and ALP-034.
- Tenant-supplied provider keys: breaks evals, budgets and hidden models (ADR-0010).
- Caching by tenant-unaware prompt hash: risks cross-tenant leakage (ALP-014).

## Consequences
- Easier: one place for keys, filters, budgets and the meter; the Operate port already fits.
- Founder decision needed (Q-680), for a phase-1 market: no endpoint inside Egypt is verified, so Egypt tenants get no model call on any tenant content until the contract carries PD. That means no agents and no chat on their own data, only platform (L0) content. After that change only C2 without PD may pass; C3 and PD wait for a PDPC licence. KSA, UAE and Qatar tenants likewise get none until each market's safeguard files (SCCs and transfer risk assessment for KSA and UAE, plus the records-of-processing entry for UAE; a DPIA for Qatar) are on file, because PD cannot yet be read or redaction checked.
- Harder: the durable meter and the reservation step are new work; the routing table must be re-admitted from a gateway-run bake-off (Q-123) before G2 exit.
- Needed: the contract gaps (Q-671, Q-672) and the #316 decision 5 scope (Q-673) answered by Eldon; LEG-012 counsel opinion for the region policy and Q-674 on PD redaction; provider terms checked in writing; PLT-011 and PLT-021 for the regional store and entitlement-driven tenant caps; PLT-010 for regional endpoint routing at G3; SEC-008's port and security stream, and PLT-019 support access, before content capture goes live; Q-679 on a reply after a TTL release. Security review required (touches tenancy and compliance).

## Supersedes
none

## Partner revision (PLT-009, carrying #232 at 6271f62e)
Fixes from the sayegh9 reads of #232 (2026-11-21 review, 2026-11-22 design-input read) and the re-check against main:
| Fix | Where |
|---|---|
| High: a missing trust label is refused (`invalid_request`, `missing_trust_label`), never L3 (contract §3) | design §2, MG-013; Decision 9 |
| Medium, caching: platform response cache holds L0 C0/C1 only; L1 is tenant config; memory is L3 in block 3 with per-call delimiters; L0, L1 and tools by reference (contract §3) | design §4, MG-008, MG-009; Decision 5 |
| Medium, caller interface: seven refusal codes, `min_output_tokens` refusal, cost after dispatch, 24 h idempotency, sticky taint, no model id (contract §1, §2, §2.1, §4 to §6); the 2026-11-21 interface gaps each aligned or named | design §2, §3.3, §9.1, §9.2, MG-001, MG-005, MG-006, MG-018 to MG-020; Decision 9 |
| Medium, Egypt (partial): the rule is now C3 and unredacted PD blocks, not all C2, but it takes effect only when the contract carries PD (gap, Q-671; redaction Q-674). Until then all tenant content stays in Egypt | design §6, §9.2, MG-014; Decision 7 |
| Low: S23 fingerprints cite ADR-0038 item 8 | design §2, MG-011 |
| Re-check, contract §6.1: input bound is the UTF-8 byte bound, not the 3 chars/token estimate; overruns per §6.4 | design §3.3 |
| Re-check, contract §7: at most 3 attempts (was "2 retries"); fallback ends or commits the previous hold | design §3.2 |
| Re-check, contract §5: old codes `budget_exceeded` and `policy_refused` replaced by the contract set | design §9.1 |
| Re-check, contract §8: a response-cache hit is not metered as if dispatched; cache waits on the gap | design §4, §9.2 |
| Re-check, PLT-025 as built: `GatewayContext` lacks run-token fields; `gateway_port.py` hard-codes `actor_kind` (Eldon lane, Q-672) | design §8 |
| Re-check, #241: Q-127 decided as option A; lane text no longer waits on it | design §1, §11; Context, Decision 1 |
| Re-check, #316 decisions 1 to 4 and 6: SEC-008 port; identity events to the platform security stream, tainted-content events per SEC-003 section 8; `memberRef` + `token_id`; one audit id (reading, Q-672); buffered emission (reading, Q-673); write-through capture start | design §7, §9.2, MG-012, MG-021; Decision 10 |
| Re-check, PLT-025 as built: `ProviderResponse` has no tool calls or stop reason; `precheck_budget` replaced, not reused | design §3.3, §5 |
| Re-check, #316 decisions 5 and 7: model-call idempotency kept (scope in Q-673); `payload_too_large`, `unauthenticated` and `audit_unavailable` stay Tool API codes | design §9.2 |
| Re-check, 2026-11-21 Lows: `BudgetStore` port with hold TTL and fail-closed commit; trace identity fields; C3 masked, DEK-encrypted and TTL-purged capture | design §3.3, §7 |
| Eldon's review of #355 at 66ba1f9e (Claude Opus 5.5): M1 question IDs renumbered to Q-671 to Q-674 (the earlier IDs collide with #277 and #286); L1 hold TTL at least 3 times `attempt_timeout` plus a margin, late reply as overrun (Q-679); L2 trace retention per country, purge at offboarding; L3 response-cache key over the exact bytes sent; L4 PD-may-leave per market and the Egypt consequence stated (Q-680); N2 PLT-019 named; N3 `pd_not_allowed` proposed; N1 stale Q-127 note removed | design §1, §3.3, §4, §6, §7, §9.2, §11, MG-005, MG-012, MG-014; Decisions 4, 5, 7, 8; Consequences |
Kept unchanged from #232: single gateway in `services/gateway/` on PLT-025, tier and purpose routing with per-market eval admission, transport-only fallback with circuit breakers, nested atomic budget reservations, S01 per-provider per-market keys, per-market region policy, content-free traces.
