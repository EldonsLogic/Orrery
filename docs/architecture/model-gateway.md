# Model gateway

Status: draft (design only, no code). Decision record: [ADR-0053](../decisions/ADR-0053-model-gateway.md) (Proposed).
Owner: partner
Original author: Eldon (#232); carried into PLT-009 by the partner with review fixes (revision note at the end of ADR-0053).

Plan row PLT-009 (G2). **Binding interface: [contracts/model-call.md](../../contracts/model-call.md) 0.2.1 (PLT-026).** Where this design and the contract differ, the contract wins and the difference is a defect here; "contract §n" below means a section of that file. Gaps the contract does not cover are named in section 9.2. Builds on: [ai-layer](ai-layer.md), [ADR-0010](../decisions/ADR-0010-model-strategy.md), [ADR-0038](../decisions/ADR-0038-secrets-management.md), [agent-runtime](agent-runtime.md), the PLT-025 code in `services/gateway/` ([README](../../services/gateway/README.md)), [prompt-injection-defence](../security/prompt-injection-defence.md) (SEC-003), [agent-least-privilege](../security/agent-least-privilege.md) (SEC-020), [secrets-management](../security/secrets-management.md) (SEC-002), [data-protection-and-residency](../compliance/data-protection-and-residency.md), the QA-003 bake-off ([qa-003-arabic-bakeoff](../research/qa-003-arabic-bakeoff.md)). It tightens those documents and loosens nothing.

## 1. Where it lives
**The home is `services/gateway/`, the partner's lane** (`scripts/lanes.json`). Reasons:
1. PLT-025 already put the model router, the meter, the price book and `meter.ai_usage` emission there (`router.py`, `metering.py`, `pricing.py`). Its README already lists live provider adapters, fallback and the cache as PLT-009 work.
2. Eldon-lane code already calls it: `services/operate/runtime/gateway_port.py` imports `gateway.MeteredGatewayRouter` and `BudgetExceededError`.
3. SEC-003 requires one prompt-assembly point ("a service that builds a prompt by string concatenation outside the gateway is a defect"); ADR-0038 gives provider keys (S01) and the fingerprint feed (S23) to "model gateway only". Splitting routing, budgets, keys and filters across two services and two lanes would create two security boundaries for one job.

Homes considered and rejected, so nobody designs around the lane:
| Home (lane) | Why not |
|---|---|
| `services/operate/` (eldon) | Discovery (DSC interview), the factory (BPL-017) and evals also call models; Operate would become a second, hidden gateway with its own keys and meter |
| `services/control-plane/` (eldon) | Holds the tenant registry and identity, not the hot path; putting S01 there widens who reads provider keys |
| New `services/model-gateway/` (needs a `lanes.json` entry) | Forks or duplicates PLT-025 metering, breaks "one meter", and is the "design around it" the brief forbids |
| `contracts/` (eldon) | Holds the *interface* (`contracts/model-call.md`, PLT-026), not the runtime |

Lane: Q-127 was decided by Eldon on 2026-11-21 as option A (GOV-058, #241). PLT-009, PLT-010, PLT-011 and PLT-021 are partner rows, and Eldon's rows (SEC-009, BPL-017, OPR-013) build against the PLT-026 contract and its fake port (`services/operate/runtime/model_call_fake.py`). Eldon's lane keeps: the routing table inputs (evals, `agents/model-registry.md`), the caller ports in `services/operate`, and the contract in `contracts/`.

## 2. Request path
```
caller port (operate / discovery / blueprint factory), request per contract §2
  -> schema, 1 MiB bound, model_named, version (contract §1 rule 1, §2, §9)
  -> identity from the verified principal and the signed run token; body `caller` only compared (contract §1 rule 2)
  -> idempotency: scoped key, 24 h store, in-flight lock (contract §2.1)
  -> kill-switch check (ALP-036, unreachable = engaged; also on replay)
  -> trust labels and references: missing label refused, L0/L1/tools resolved by reference, order, grant (contract §3)
  -> region policy for the tenant's market: data_class and PD per block, allowed endpoints (section 6)
  -> accepts_untrusted and taint: own taint record per thread, session and run (contract §2, §3)
  -> context assembly: SEC-003 3.2 order, per-call random delimiters around every L3 item
  -> secret filter on everything sent (ADR-0038 item 8, S23 fingerprints; feed stale = refuse)
  -> response-cache lookup, L0-only calls (section 4)
  -> budget reservation (contract §6) -> route + fallback chain (contract §7) -> provider adapter (section 5)
  -> output filter (SEC-003 5.3, secret filter on text and tool-call arguments)
  -> commit or release (contract §6.3) -> meter.ai_usage (contract §8) + trace (section 7)
  -> reply (contract §4: trust "untrusted", tainted, no model id) or refusal (contract §5)
```
Every step fails closed with one of the contract's seven refusal codes and its closed reasons (contract §5); refusals carry no provider text, model id or prompt content (ADR-0016 style), and the deterministic paths keep working (spec 05).

## 3. Routing by tier, fallback, budgets
### 3.1 Tiers and the routing table
- Callers ask for a logical tier (`frontier`, `mid`, `small`; `code` is never a model) and a `purpose` (`chat`, `agent`, `build`, `simulation`, as in PLT-025). They never name a model or provider.
- The routing table is config, versioned in the repo, one row per `(tier, market)`: an ordered chain of `(provider, model_id, endpoint_region)`. Each entry carries the eval evidence that admits it (eval set, score, date). QA-003 evidence today: Sonnet and Opus classes clear 0.85 on `arabic_core`, Haiku class does not on dates and numbers. So the `small` tier may serve routing and classification only where code resolves numbers and dates; Arabic run-time chat starts on `mid`. These are single-run, unreviewed numbers (Q-123): the table must be re-admitted from a gateway-run bake-off (controlled decoding, non-Claude models, cost and latency) before G2 exit.
- A prompt or model change that regresses a blocking eval suite cannot enter the table (ai-layer, Evals).

### 3.2 Fallback
- Fallback only on transport failure: timeout, connection error, provider 5xx, 429 or overload. Never on a refusal, a filter block or a schema failure (that is a result, not an outage).
- The next entry must be the same tier or stronger, admitted by evals, and allowed by the tenant's region policy. **No silent downgrade** to a weaker tier, shorter context or skipped filter (ALP-034).
- Each fallback ends the previous hold as contract §6.3 says (committed if the provider may have billed, released if it received nothing), reserves again at the new entry's price (contract §6.5), is logged (`fallback_from`, reason class), sets `fallback_used` and counts toward the cap of at most 3 attempts per call (contract §7).
- Chain exhausted: return `model_unavailable` (`chain_exhausted`), no partial answer; `reservation_released: false` if any attempt was charged. Per-provider circuit breaker (open after N consecutive failures, half-open probe) so one outage does not burn every tenant's latency budget.
- PLT-010 (G3) later adds regional endpoint selection and licence-checked proxy evaluation on top of this chain; nothing here pre-builds it.

### 3.3 Budgets and hard caps (fail closed)
Reuse PLT-025 `BudgetPolicy`, `compute_call_cost` and the meter's per-scope counters; `precheck_budget` and the `enforce_budget=False` commit are replaced by the hold of item 2, and `BudgetExceededError` maps to `budget_refused`. PLT-009 adds:
1. **Nesting** (ALP-031, contract §6.1): platform >= tenant (monthly, from plan entitlement, PLT-011/PLT-021) >= session (build session, chat session) >= agent grant >= run. A lower layer only tightens. Layer ids come from the principal and run token, never the body. Missing policy at a configured layer is `budget_refused` (`policy_missing`); a configured layer with no id is `layer_unbound`. All layers are reserved atomically or none.
2. **Reservation, not just a check** (contract §6). Today `execute` prechecks on an estimate, then commits actual spend with `enforce_budget=False`, so a call can overshoot the cap. PLT-009 replaces the precheck with a hold:
   - The input bound is the UTF-8 byte count of everything sent (resolved blocks, data wrappers and delimiters, tool specs) plus a fixed framing allowance per block and per tool, or the provider's own token count when it has one (contract §6.1). It is not a chars-per-token estimate. The 3 chars/token in `gateway_port.py` stays a caller-side guess only. Byte-level tokenization is checked per entry at admission (UNVERIFIED for every provider today).
   - `output_limit` starts at `max_output_tokens` and may drop to the largest affordable value. If that is below `min_output_tokens` (default `max_output_tokens`), the call is refused (`budget_refused`, `exceeded`) with nothing reserved. The gateway never clamps silently to a tiny output (contract §6.2, ALP-034).
   - Each hold has a TTL and ends exactly once, `committed` or `released`. A hold still open at its TTL is released by the gateway (contract §6.3).
   - **TTL versus an in-flight call.** Each routing entry carries an `attempt_timeout` (routing-table config; the value is set at admission, none is chosen here). The gateway cancels the provider call at that timeout. The hold TTL is at least 3 times the largest `attempt_timeout` in the chain plus a fixed margin, so no hold is released while its call can still be running and concurrent calls cannot cross a cap through an early release. Holds are per attempt (contract §6.5), so this bound is conservative.
   - **A reply after a TTL release** (sweeper, restart or clock skew) does not reopen the hold: it stays `released`, so it still ends exactly once. The late actual cost is committed as an overrun under contract §6.4 on the same layers, with one `meter.ai_usage` event, an overrun alert, and later reservations on those layers refused until the window resets. The call was already cancelled at its timeout and the caller already has its reply or refusal, so the late content is discarded, never returned or cached. This is a reading: contract §6.3 and §8 do not cover it (section 9.2 item 10, Q-679).
   - Once dispatch has begun, the actual cost is committed and metered whatever the result: a reply, withheld output (`filter_blocked`) or a timeout after send. Only the content is withheld (contract §1 rule 4, §6.3).
   - An actual cost above the hold is still committed and raises an overrun alert. Later reservations on that layer are refused until the window resets (contract §6.4).
   - Concurrent calls count each other's holds (contract §6.6).
3. **Durable meter.** The PLT-025 meter is in-process, and caps only hold across workers and restarts with a durable, atomic counter store per tenant, in the tenant's region. PLT-009 defines the `BudgetStore` port (reserve, commit, release, TTL sweep) with a local in-process implementation for tests. PLT-011 wires the regional store and per-agent and per-grant attribution; PLT-021 wires plan entitlements into the tenant layer. If the store is unreachable or a commit fails, model calls are refused (`budget_refused`, `meter_unavailable`, ALP-032).
4. **Exhaustion**: refuse the call, raise `BudgetStop` in the runtime, emit `agent.budget_exceeded` (agents) or a budget alert (others), and notify the owner at threshold and at cap (PLT-025 `alert_threshold_pct`). Customers see "AI actions", never tokens (ADR-0010).
5. A per-call ceiling exists independent of budgets (1 MiB request, `max_output_tokens` at most 32000, at most 3 attempts; contract §2, §7), so one malformed request cannot spend a month.

## 4. Prompt caching and response caching
- **Provider prompt cache** (prefix caching where the provider supports it; behaviour and prices per provider UNVERIFIED, the PLT-025 10 percent cached-input rate is an assumption). Context is assembled in the contract §3 order, which is also the prefix order:
  1. **Block 1, L0 platform.** System rules, the tool specs offered and the platform glossary. These are resolved by reference in the release manifest of `prompt_version` (contract §3), hold no tenant data, are C0 or C1 only, and are shared across tenants.
  2. **Block 2, L1 tenant configuration only.** Resolved by reference in the tenant's applied Blueprint revision. It starts with a per-tenant marker the gateway adds, so no prefix containing tenant data can match another tenant.
  3. **Block 3, L2 and L3 conversation items** in `turn` order. Every L3 item, including **memory** (always L3: SEC-003 section 2.1 "all memory entries", section 6, PI-029; `transform: memory_read`), is wrapped in a quoted data section with a per-call random delimiter (SEC-003 3.2, PI-011). Memory is never in block 2. Because the delimiter changes per call, block 3 is never a stable cache prefix.

  Cache breakpoints sit at the end of blocks 1 and 2. L0, L1 and tool specs travel by reference only: inline trusted text or an inline tool spec is `invalid_request` (`ref_required`), so no caller can place its own text in the shared L0 prefix (contract §3).
- `cached_tokens` comes from the provider's usage report only and flows into PLT-025 `CallUsage.cached_tokens`; the gateway never computes a discount itself.
- **Response cache** (our own, platform-scoped): only for a call in which **every block is L0** (`trust: platform`, C0 or C1), no tool is offered, the thread is not tainted and the purpose is marked cacheable (for example a translation of a platform glossary entry). L1 is tenant configuration (C2 under SEC-003, `tenant_config`), so a call with any L1 block never enters or reads this cache; neither does one with L2 or L3 content, PD or tool results. Key = hash of the exact bytes sent: the assembled prompt as it goes to the provider (after resolution, assembly and filtering, so `locale` and anything else that changes those bytes is covered), plus the decoding settings and the output limit. An L0-only call has no L3 item, so it has no per-call random delimiter and its bytes are stable. The routing-table version, model id and `prompt_version` stay in the key as well, so a table, model or prompt change invalidates the entry. TTL bounded; invalidated on a prompt or table change. A hit still passes the output and secret filters. A hit is not a dispatch, so under contract §8 it has no reservation and no meter event; the reply's `usage` and `meter_event_id` for a hit are a contract gap (section 9.2). The cache is not built until that gap is closed.
- The idempotency store (contract §2.1) is not a cache: it is scoped to (service, tenant, actor), holds a stored reply 24 h encrypted under the tenant key and re-checks the kill switch, secret feed and output filter on replay.
- No cross-tenant cache of any kind (ALP-014). Per-tenant response caching is out of scope for PLT-009.

## 5. Provider abstraction and key handling
- One adapter per provider behind the PLT-025 `transport` callable: input is the assembled, filtered context plus decoding settings; output is the PLT-025 `ProviderResponse` (output, input/output/cached tokens, served model id). As built, its `output` is untyped and it has no `stop_reason` or tool calls, so PLT-009 extends it with typed text, tool calls and stop reason, which contract §4 needs. Adapters do no assembly, no budgeting and no logging of content. Provider-specific error text never leaves the adapter; it maps to a fixed error class.
- **Keys**: provider keys are S01 in the secret store (ADR-0038), read only by the gateway's runtime identity, 90-day rotation, never in the repo, env files, logs, traces, prompts or errors. One key per provider per market account, so a market can be cut off or rotated alone and spend is attributable per region.
- **Per-tenant isolation**: tenants share platform provider accounts; isolation is ours: tenant from the verified principal only (contract §1 rule 2; a tenant key elsewhere is `tenant_in_payload`), tenant-tagged meter rows, no cross-tenant cache, output filter checks other tenants' identifiers, S23 checks are tenant + platform scoped with uniform refusals (ADR-0038). Tenant-supplied keys (bring your own key) are rejected for v1: it breaks evals, budgets and the hidden-model rule (ADR-0010).
- Egress: the gateway is the only model egress path, to an allow-list of provider hosts (prompt-injection-defence section 5, hosting-rules).
- Provider terms (no training, minimal retention, region) are checked per provider in writing before an entry enters the routing table (hosting-rules; UNVERIFIED for every provider today).

## 6. Data residency per market
The tenant's country (tenant registry, ADR-0024; never from the request body) selects a **region policy**: allowed `(provider, endpoint_region)` pairs, the highest `data_class` that may leave the country, and whether PD-tagged content may leave. Class and PD are separate labels (data-classification, "Personal-data tag"). Every tenant item is at least C2, and business contact details are C2 + PD. A policy written only as a class ceiling would therefore either block all tenant content or let PD through. The gateway checks every block's `data_class` and PD status against the policy. A forbidden block is `region_policy_refused` (`data_class_not_allowed`); no admitted endpoint left for the tier is `no_allowed_endpoint`; an unknown market or missing policy is `policy_missing` (contract §5). Where the PD status comes from is a contract gap (section 9.2). Whether a model API call is a cross-border transfer at all is counsel question 10 / LEG-012 (UNVERIFIED). Sources below were located on official sites on 2026-11-21 through search results; full texts were not read end to end, so every legal reading here is UNVERIFIED until LEG-012.

| Market | What the official source says (summary) | Interim gateway default |
|---|---|---|
| KSA | PDPL (Royal Decree M/19, amended M/148 of 2023) and SDAIA's Regulation on Personal Data Transfer outside the Kingdom: transfer allowed if it does not affect national security or vital interests, limited to the minimum necessary, with a risk assessment for some transfers; safeguards are adequacy, SDAIA standard contractual clauses (four templates) or binding common rules. https://sdaia.gov.sa/Documents/RegulationonPersonalDataEN.pdf ; https://dgp.sdaia.gov.sa (SCC and BCR guidelines), accessed 2026-11-21. Which version is in force: UNVERIFIED | Redact personal data where the task allows; only approved endpoints; SCCs with each provider; transfer risk assessment on file before go-live |
| UAE | Federal Decree-Law 45/2021, in force 2022-01-02: Art. 22 transfer to adequate jurisdictions or under an agreement; Art. 23 otherwise by contract, explicit consent or listed grounds, with controls in Executive Regulations. https://uaelegislation.gov.ae/en/legislations/1972 ; https://u.ae/en/about-the-uae/digital-uae/data/data-protection-laws , accessed 2026-11-21. Executive Regulations issued: UNVERIFIED. Free zones (DIFC, ADGM) not covered | Same as KSA; record cross-border processing in the records of processing |
| Egypt | Law 151/2020; the PDPC FAQ says transfer abroad needs a prior cross-border licence or permit from the PDPC plus a legal basis; PDPC guidance cites Executive Regulations by Decision 816 of 2025. https://portal.pdpc.gov.eg ; https://pdpc.gov.eg/home , accessed 2026-11-21. Exact article text and licence process: UNVERIFIED | **Strictest default** until a PDPC licence exists, for any endpoint outside Egypt: refuse every C3 block and every PD-tagged block not yet redacted. C2 without PD (for example a supplier invoice with no named person) may pass. **Under contract 0.2.1 this narrower rule cannot take effect yet:** PD status is not readable (no field; section 9.2 item 1), and unreadable counts as PD, so all tenant content stays inside Egypt until the contract change. Whether a deterministic redaction step may clear the PD tag is UNVERIFIED (data-classification rule 3 says derived data inherits it; Q-674) |
| Qatar | Law 13/2016 (PDPPL), NCSA is the competent authority: Art. 15 says a controller must not restrict cross-border flows except under stated conditions (text not read); NCSA guidance treats cross-border transfer as possibly serious-damage processing that needs safeguards and a DPIA. https://ncsa.gov.qa/en/pages/personal-data-privacy-personal-data-privacy-protection-law , accessed 2026-11-21 | Redact; DPIA on file before go-live; approved endpoints only |

**What each policy allows today, under contract 0.2.1.** Unreadable PD counts as PD in every market, so each policy's "PD may leave" value decides whether that market gets any model call on tenant content. "Redact where the task allows" cannot be checked by the gateway today: PD cannot be read (section 9.2 item 1) and redaction is not marked (item 2), so it is a caller duty, not a gateway check. The values below are what the interim defaults above imply. They are UNVERIFIED (LEG-012) and await a founder decision (Q-680):
| Market | PD may leave the country today | Effect on tenant content |
|---|---|---|
| KSA | Yes, to approved endpoints only, once SCCs with that provider and the transfer risk assessment are on file; `false` until then | Model calls on tenant content only after those files exist |
| UAE | Yes, to approved endpoints only, once SCCs with that provider, the transfer risk assessment and the records-of-processing entry are on file; `false` until then | Same as KSA |
| Qatar | Yes, to approved endpoints only, once the DPIA is on file; `false` until then | Same as KSA |
| Egypt | No, until a PDPC licence exists | Two stages. Until the contract carries PD: no model call on any tenant content, so no agents and no chat on the tenant's own data, only L0 platform content. After that change: C2 without PD may pass; C3 and PD wait for the licence. This is a founder decision for a phase-1 market (Q-680) |

- In-region inference (a model endpoint inside KSA, UAE, Egypt or Qatar) for any provider: UNVERIFIED. If counsel restricts transfers, the strategy/06 self-hosting trigger moves forward; the policy table changes, the code does not.
- The policy table is config owned by the founders, changed by PR with a log entry; the gateway enforces it, it does not interpret law.

## 7. Logs and traces without customer secrets
- **Meter**: exactly the PLT-025 `meter.ai_usage` event (Contract 4, `data_class: operational`), one per committed reservation, none for a refusal before dispatch or a replay (contract §8). No new usage event type.
- **One audit id end to end** (#316 decision 6). Reading (the contract only says `correlation_id` comes from the body; section 9.2 item 6, Q-672): `caller.correlation_id` carries the audit id of the request that started the work, which is the API edge request, the agent run or the build step. PLT-025's `ModelCallRequest.audit_id` already has a slot for it. The trace, the meter event's `correlation_id` and every security event reuse it; the gateway mints no second id. `gateway_port.py` sets it to the run id today.
- **Trace record per call** (gateway operational log in the tenant's region; not the tenant audit), content-free:
  - Identity, from the principal and run token: tenant, actor kind, `actor_id`, `on_behalf_of`, `agent_id`, grant id and version, `run_id`, `session_id`, `thread_id` (ALP-040, PI-032). A human actor is recorded as the per-tenant `memberRef` plus `token_id`, never a global user id (#316 decision 2).
  - Call: call id, purpose, tier requested and served, served model id, `prompt_version`, routing-table version, region-policy id, attempts and fallback reason classes, cache hit, replayed, token counts, cost, latency, refusal code and reason.
  - Envelope metadata, counts only: blocks per trust level, data class and PD, `transform` kinds, and `tainted`.
  - Filter outcomes: rule id only, never the matched text.
  - Retention: the trace holds identity fields (`memberRef`, `token_id`, agent and run ids), so it has a retention period set per country in config, like other records (data-protection-and-residency, "Retention"; the periods are research needed, UNVERIFIED). Traces past it are purged, legal hold excepted, and all of a tenant's traces are purged at tenant offboarding with its other data, as the idempotency store is (contract §2.1 item 6).
- **Security events.** The gateway defines no audit or security-record format of its own; it writes through SEC-008's `AuditStore` port and stream (#316 decision 1). Every event carries the audit id, the refusal code and reason, and no content.
  - Forged or cross-tenant identity (`caller_mismatch`, `tenant_in_payload`) goes to SEC-008's in-country platform security stream, kept out of the tenant audit (#316 decision 3, ADR-0069 5.4).
  - Tainted-content and filter events follow SEC-003 section 8. `filter_blocked` and `injection_tainted` get the section 8.1 record and the section 8.2 events (`agent.output_flagged`, proposed `injection.suspected` and `egress.blocked`, through the events contract change, PI-032). A missing trust label is a defect alert (section 8.3).
  - Kill-switch refusals and overrun alerts go to platform operations alerting. Whether these and the section 8 events also enter the platform security stream is SEC-008's call (Q-673).
  - Reading, not yet decided: model calls are ordinary routes, not admin or money routes, so this emission is buffered and crash loss is accepted (#316 decision 4, Q-673).
- **No content by default**: prompts, outputs and tool results are not logged for tenant data (ai-layer). Content capture for debugging works as follows:
  - It needs a tenant support-access grant with a TTL (PLT-019, audited just-in-time support access) and stays in the tenant's region.
  - C3 stays masked. The capture is encrypted under the tenant DEK and purged at the grant's TTL.
  - Starting and ending a capture are admin actions. Their audit entries go through SEC-008's port and are stored before the capture starts (write-through, #316 decision 4); if audit is unavailable, no capture starts.
  - Secrets never: the S23 filter runs on any captured content too.
- Provider request ids are kept (to match provider-side records) but never shown to customers.

## 8. Reuse of PLT-025 (no duplication)
| PLT-025 piece | PLT-009 use |
|---|---|
| `GatewayContext`, tenant validation, spoof-key refusal | Kept as the tenant and actor source. As built it has no `agent_id`, `run_id`, `thread_id` or grant id and version; PLT-009 extends it from the signed run token (contract §1 rule 2, SEC-020 section 2 item 3) |
| `PriceBook`, `compute_call_cost` (integer micro-USD) | Prices every reservation and fallback; rates become verified rate cards (still UNVERIFIED) |
| `GatewayMeter`, `BudgetPolicy`, `precheck_budget`, `record_call` | Kept; gains the `BudgetStore` port (section 3.3) and a reserve/commit/release step that replaces `precheck_budget` plus `enforce_budget=False` |
| `MeteredGatewayRouter`, `ModelRoute`, `transport` | `ModelRoute` becomes a chain; provider adapters plug in as `transport`; `ModelCallResult` loses the model id on the caller side (contract §4) |
| `build_ai_usage_event` | The only usage event emitter |
| `services/operate/runtime/gateway_port.py` (eldon) | Eldon's lane, not changed here. It moves to the contract client (`model_call_fake.py` shape). It must take `actor_kind` from the principal: it hard-codes `"user"` at line 64 today, which is wrong for agent runs (Q-672) |

## 9. Interface for callers
The interface is [contracts/model-call.md](../../contracts/model-call.md) 0.2.1 (PLT-026, ADR-0054). Callers depend on it, never on gateway internals, and the gateway implements it unchanged. This design adds no field, code or reason; any change goes through a contract version with its ADR in Eldon's lane.

### 9.1 How the contract covers the 2026-11-21 interface gaps
| Item | Contract answer |
|---|---|
| Refusals | Exactly seven codes with closed reasons per code: `budget_refused`, `kill_switch_engaged`, `region_policy_refused`, `model_unavailable`, `invalid_request`, `injection_tainted`, `filter_blocked` (contract §5). Callers map every code; an unknown code is non-retryable |
| Output limit | `min_output_tokens` refusal, never a silent clamp (contract §2, §6.2) |
| Cost after dispatch | Committed and metered once dispatch began, whatever the result (contract §1 rule 4, §6.3) |
| Idempotency | Scoped key, 24 h, replay re-checks kill switch, secret feed and output filter (contract §2.1) |
| Taint | `thread_tainted` input; the gateway's own sticky record per (tenant, thread), (tenant, session) and (tenant, run); it only raises taint (contract §2, SEC-003 2.4 rule 4, PI-009) |
| Model id | Not in the reply; trace and meter event only (contract §4) |
| `run_id` vs `session_id` | Separate fields, both from the principal or run token (contract §1 rule 2, §2) |
| Agent and grant ids | `agent_id`, `run_id`, `thread_id` and the tool grant come from the signed run token; the grant id and version go to the trace (section 7). Not in the body |
| `market` | From the tenant registry, never the body (section 6) |
| `allowed_data_classes` | Not a request field: the region policy (section 6) and the run grant set them. Gap for the grant part, section 9.2 |
| `actor_kind` | `user`, `agent`, `system`, `support` from the principal (contract §2). `gateway_port.py` hard-codes `user` (section 8) |
| Tools | By reference, intersected with the run-token grant (contract §2, §3) |
| `output_schema` | Missing. Gap, section 9.2 |
| Item envelope | `data_class`, `parents`, `transform`, `source`, `flags`, `content_hash` on conversation items; `tenant_id` is stamped from the principal, never sent (contract §3). `pd` is a gap, section 9.2 |
| Reply stamp | `trust: "untrusted"` and `tainted` on every reply (contract §4, PI-008) |

### 9.2 Contract gaps (named so neither PLT-009 nor PLT-026 is blocked; Q-671, Q-672, Q-679)
1. **PD tag.** There is no `pd` field. A conversation item can only carry it as an undefined `flags` entry, and an L1 block (strict schema) cannot carry it at all. Proposal: a reserved flag `pd` on conversation items, with L1 PD status taken from the resolved Blueprint entry's field classes. The same change needs a closed reason for a PD refusal, for example `pd_not_allowed` under `region_policy_refused`; reasons are closed (contract §5), so until it exists a PD refusal uses `data_class_not_allowed`. Until it is defined, an item whose PD status cannot be read counts as PD (fail closed, like "unknown is C3"). For Egypt that means the narrower section 6 rule takes effect only with this contract change; before it, tenant content stays inside Egypt.
2. **Redaction marker.** The `transform` enum has no redaction value, so a redacted item cannot be told apart (Q-674).
3. **Grant data-class ceiling (ALP-016).** The contract has no reason for a block above the run grant's data class. Field stripping belongs to OPR-004 at the Tool API; the gateway needs a block-level refusal reason.
4. **`output_schema`** for structured output (SEC-003 3.2 item 3) is absent.
5. **Response-cache hits**: the reply's `usage` and required `meter_event_id` for a hit with no dispatch are undefined (section 4).
6. **Actor id and audit id form.** For a human, `actor_id` should be the per-tenant `memberRef`, with `token_id` from the claims (#316 decision 2). The contract does not say. `gateway_port.py:64` passes `actor_id=principal.subject`, which reaches the `meter.ai_usage` actor. That is a global id if the subject is the central person id. Also, `caller.correlation_id` is not defined as the audit id (section 7).
7. **No verified principal.** The contract has no case for it. Reading here: the service listener rejects the call before the body is parsed, and nothing reaches contract §5.
8. **#316 error codes.** `payload_too_large`, `unauthenticated` and `audit_unavailable` are Tool API codes (#316 decision 7) and stay out of the model-call set. An oversize request is already `invalid_request` (`schema`, contract §2). A model call writes no write-through audit, so `audit_unavailable` does not apply; only content capture waits on audit (section 7).
9. **#316 decision 5** ("the gateway does no second dedupe") is read as the Tool API write path through the API edge; the model-call 24 h idempotency of contract §2.1 stays. Q-673 asks Eldon to confirm this reading. It also asks him to confirm the reading that model calls are ordinary routes under decision 4, and which gateway events SEC-008's platform security stream takes (section 7).
10. **Reply after a TTL release.** Contract §6.3 releases a hold at its TTL, and §8 meters committed reservations, but neither says what happens to a provider reply that arrives after that release, nor sets a floor for the TTL against the attempt timeout. Reading in section 3.3: TTL at least 3 times the largest `attempt_timeout` plus a margin; a late reply leaves the hold `released`, its cost is committed as a §6.4 overrun with one meter event and an alert, and its content is discarded (Q-679).

## 10. Test plan and acceptance checks
All tests offline with fake transports and synthetic tenants; one opt-in live smoke per provider in a dev environment with dev keys (S20), never in CI.
| ID | Check | Ref |
|---|---|---|
| MG-001 | A call with no verified principal is rejected before parsing; a body `caller` that differs from the principal is `caller_mismatch`; a tenant key in `metadata` or a block is `tenant_in_payload`; nothing reaches a transport | contract §1 rule 2, SEC-020 |
| MG-002 | Each tier routes to the first admitted entry for the tenant's market; any `model`, `model_id`, `provider` or `endpoint` field (also in `metadata`) is `model_named` | 3.1, contract §1 rule 1 |
| MG-003 | Transport failure falls back to the next same-or-stronger entry, at most 3 attempts; refusal, filter block and schema failure do not fall back | 3.2, contract §7, ALP-034 |
| MG-004 | No chain ever selects a weaker tier or an endpoint outside the region policy; exhausted chain returns `model_unavailable` with the right `reservation_released` | 3.2, 6 |
| MG-005 | Platform, tenant, session, agent and run caps: the call that would cross any cap is refused; all layers reserve atomically; concurrent calls cannot jointly exceed a cap (threads); an unended hold is released at its TTL; the hold TTL is at least 3 times the largest `attempt_timeout` plus the margin, so no hold is released while its call can run; a fake reply delivered after a TTL release leaves the hold `released`, is committed as an overrun with one meter event and an alert, blocks later reservations on that layer and is never returned; a failed meter commit refuses later calls | 3.3, contract §6 |
| MG-006 | Output limit drops to what the budget affords, never below `min_output_tokens`; below it the call is `budget_refused` (`exceeded`) with nothing held; the input bound is the byte bound of contract §6.1; an overrun is committed, alerted and blocks the layer | 3.3, contract §6.1, §6.2, §6.4 |
| MG-007 | Meter store unavailable, kill flag unreachable, S23 feed stale, or region policy missing: every model call is refused with the matching contract code and reason | 3.3, contract §5, ALP-032, ALP-036, ADR-0038 |
| MG-008 | Two tenants with identical messages share only the L0 prefix; L1 starts with the tenant marker; memory items sit in block 3 inside per-call delimiters; no tenant block or response-cache entry is reusable across tenants | 4, ALP-014 |
| MG-009 | The response cache stores and serves only calls in which every block is L0 C0/C1 with no tools; any L1, L2, L3, PD or tool-result content bypasses it; inline L0/L1 text or tool specs are `ref_required` | 4, contract §3 |
| MG-010 | `cached_tokens` equals the provider-reported value and the cost matches `compute_call_cost` | 4, PLT-025 |
| MG-011 | Seeded secrets, API keys and other tenants' ids in any request string, resolved block, tool spec, assembled prompt, items joined without separators, output text or tool-call arguments are `filter_blocked` (`flagged`); logs, traces, security events and errors contain none of them (scan the captured output) | 7, contract §3, ADR-0038 item 8 |
| MG-012 | Trace and `meter.ai_usage` validate against Contract 4, carry no prompt or output text with capture off, and carry the section 7 identity fields; one audit id joins trace, meter event and security events; traces past the configured per-country retention are purged, and a tenant offboarding purges all its traces | 7, PI-032, ALP-040 |
| MG-013 | A block with a missing or unknown `trust` is refused (`invalid_request`, `missing_trust_label`) and never treated as L3 or any other level; prompts are assembled only by the gateway in SEC-003 3.2 order with per-call delimiters | contract §3, SEC-003 2.3, PI-001, PI-011 |
| MG-014 | Egypt tenant, non-Egypt endpoint. Today (contract 0.2.1): any tenant block (C2 or above, PD unreadable) is `region_policy_refused` (`data_class_not_allowed`, the only closed reason that fits until the contract adds a PD reason such as `pd_not_allowed`); L0 C0/C1 passes. After the PD contract change: a C3 block or an unredacted PD block is refused, and a C2 block without PD passes | 6, 9.2 |
| MG-015 | Provider error text and model ids never reach a reply, refusal or customer-facing error | 5, contract §4, §5, ADR-0016 |
| MG-016 | Re-run of `arabic_core` through the gateway (QA-003 rerun, Q-123) produces scores, cost and latency per routing entry; table entries below 0.85 are rejected | 3.1 |
| MG-017 | Repo hygiene and secret scan pass; no key, endpoint credential or `.env` file in the change | ADR-0038 |
| MG-018 | Same scoped key and body within 24 h replays with `replayed: true`, no dispatch or meter event; a different body is `idempotency_conflict`; an in-flight key is `idempotency_in_flight`; a replay re-checks kill switch, secret feed and output filter | contract §2.1 |
| MG-019 | After one tainted reply, a later call on the same thread, session or run is `tainted: true` even with `thread_tainted: false`; `accepts_untrusted: false` with an untrusted block is `injection_tainted`; every reply carries `trust: "untrusted"` | contract §2, §3, §4, PI-008, PI-009 |
| MG-020 | Dispatch then output filter hit, and dispatch then timeout: cost committed and metered, refusal has `reservation_released: false`; a provider that received nothing releases the hold | contract §1 rule 4, §6.3 |
| MG-021 | A human actor appears in traces and security events as `memberRef` plus `token_id`, never a global user id; security events go to the SEC-008 stream, not the tenant audit; a capture start with audit unavailable is refused | 7, #316 decisions 2 to 4 |

## 11. Open items
1. Contract gaps in section 9.2 (Q-671, Q-672) and the #316 decision 5 scope (Q-673). 2. LEG-012 counsel opinion decides section 6 defaults; whether redaction may clear PD is Q-674. 3. Provider shortlist, terms and in-region endpoints: UNVERIFIED. 4. Gateway build versus adopt (for example a proxy library), licence check pending (ai-layer open question 1). 5. Regional `BudgetStore` placement (PLT-011) and entitlement wiring (PLT-021) behind the PLT-009 port. 6. SEC-008's `AuditStore` port and platform security stream must exist before content capture or security events go live, and PLT-019 (audited just-in-time support access) must exist before content capture goes live. 7. A reply after a TTL release (section 9.2 item 10, Q-679). 8. Founder decision on what each region policy lets leave the country today, including that Egypt tenants get no model call on tenant content (section 6, Q-680).
