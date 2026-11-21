# ADR-0053: Model gateway home, routing, budgets, caching and residency

Status: Proposed
Owner: eldon
Approved by: pending

## Context
PLT-009 asks for the AI model gateway: routing, budgets, caching and logs. ADR-0010 already says every model call goes through our gateway. PLT-025 (partner) built tier routing, integer cost metering, fail-closed budget prechecks and `meter.ai_usage` events in `services/gateway/`, which `scripts/lanes.json` gives to the partner, while PLT-009 is an Eldon row (open question Q-127). SEC-003 makes the gateway the single prompt-assembly point; ADR-0038 gives provider keys (S01) to the gateway only; SEC-020 requires no silent downgrade (ALP-034) and refusal when metering is down (ALP-032). QA-003 shows Sonnet and Opus classes clear the 0.85 Arabic gate and Haiku class does not on dates and numbers (single run, unreviewed). Design: [model-gateway](../architecture/model-gateway.md).

## Decision
1. The model gateway is `services/gateway/`, extending PLT-025; no second gateway or meter in another service. Because that path is the partner's lane, building PLT-009 waits for the founders' Q-127 decision; this ADR does not move a lane or a plan row.
2. Callers ask for a tier and a purpose, never a model. A versioned routing table per tier and market lists an ordered chain of eval-admitted entries.
3. Fallback happens only on transport failure, only to a same-or-stronger, eval-admitted, region-allowed entry, and is logged; an exhausted chain fails closed.
4. Budgets nest platform >= tenant >= session >= agent grant >= run. The precheck becomes a reservation that also sets the provider output limit; the meter gets a durable store; any missing policy, unreachable meter, stale secret feed or unreachable kill flag refuses the call.
5. Prompt caching uses a fixed prefix order (platform block, tenant block with a per-tenant marker, then conversation). Our own response cache holds only platform-level content. Nothing is cached across tenants.
6. Provider adapters plug in as the PLT-025 transport. Provider keys are S01 in the secret store, one per provider per market, read only by the gateway. No tenant-supplied keys in v1.
7. A region policy per market sets allowed endpoints and the highest data class that may leave the country; a missing policy refuses the call. Egypt defaults to no personal data outside Egypt until a PDPC licence exists. All legal readings are UNVERIFIED until LEG-012.
8. Logs are the existing `meter.ai_usage` event plus a content-free trace; content capture is off by default and needs a time-limited support-access grant.

## Alternatives rejected
- Gateway in `services/operate/` (Eldon lane): Discovery and the factory also call models; it would become a hidden second gateway with its own keys and meter.
- Gateway in `services/control-plane/`: off the hot path and widens who reads provider keys.
- New `services/model-gateway/`: duplicates or forks PLT-025 metering to avoid a lane, which is designing around the lane rule.
- Fallback to any available model: breaks evals and ALP-034.
- Tenant-supplied provider keys: breaks evals, budgets and hidden models (ADR-0010).
- Caching by tenant-unaware prompt hash: risks cross-tenant leakage (ALP-014).

## Consequences
- Easier: one place for keys, filters, budgets and the meter; the Operate port already fits.
- Harder: the durable meter and the reservation step are new work; the routing table must be re-admitted from a gateway-run bake-off (Q-123) before G2 exit.
- Needed: Q-127 decision (founders), LEG-012 counsel opinion for the region policy, provider terms checked in writing, PLT-011 and PLT-021 for entitlement-driven tenant caps, PLT-010 for regional endpoint routing at G3. Security review required (touches tenancy and compliance).

## Supersedes
none
