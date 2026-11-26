# Model gateway

Status: draft (design only, no code). Decision record: [ADR-0053](../decisions/ADR-0053-model-gateway.md) (Proposed).
Owner: eldon

Plan row PLT-009 (G2). Builds on: [ai-layer](ai-layer.md), [ADR-0010](../decisions/ADR-0010-model-strategy.md), [ADR-0038](../decisions/ADR-0038-secrets-management.md), [agent-runtime](agent-runtime.md), the PLT-025 code in `services/gateway/` ([README](../../services/gateway/README.md)), [prompt-injection-defence](../security/prompt-injection-defence.md) (SEC-003), [agent-least-privilege](../security/agent-least-privilege.md) (SEC-020), [secrets-management](../security/secrets-management.md) (SEC-002), [data-protection-and-residency](../compliance/data-protection-and-residency.md), the QA-003 bake-off ([qa-003-arabic-bakeoff](../research/qa-003-arabic-bakeoff.md)). It tightens those documents and loosens nothing.

## 1. Where it lives (lane finding)
**The only sensible home is `services/gateway/`, which is the partner's lane** (`scripts/lanes.json`). Reasons:
1. PLT-025 already put the model router, the meter, the price book and `meter.ai_usage` emission there (`router.py`, `metering.py`, `pricing.py`). Its README already lists live provider adapters, fallback and the cache as PLT-009 work.
2. Eldon-lane code already calls it: `services/operate/runtime/gateway_port.py` imports `gateway.MeteredGatewayRouter` and `BudgetExceededError`.
3. SEC-003 requires one prompt-assembly point ("a service that builds a prompt by string concatenation outside the gateway is a defect"); ADR-0038 gives provider keys (S01) and the fingerprint feed (S23) to "model gateway only". Splitting routing, budgets, keys and filters across two services and two lanes would create two security boundaries for one job.

Homes considered and rejected, so nobody designs around the lane:
| Home (lane) | Why not |
|---|---|
| `services/operate/` (eldon) | Discovery (DSC interview), the factory (BPL-017) and evals also call models; Operate would become a second, hidden gateway with its own keys and meter |
| `services/control-plane/` (eldon) | Holds the tenant registry and identity, not the hot path; putting S01 there widens who reads provider keys |
| New `services/model-gateway/` (needs a `lanes.json` entry) | Forks or duplicates PLT-025 metering, breaks "one meter", and is the "design around it" the brief forbids |
| `contracts/` (eldon) | Right place for the *interface* (section 9), not the runtime |

This is open question Q-127 (lane mismatch on the gateway), still undecided. Until founders decide, nothing in this design is built; this file and the ADR sit in shared paths. Eldon's lane keeps: the routing table inputs (evals, `agents/model-registry.md`), the caller ports in `services/operate`, and any contract in `contracts/`.

## 2. Request path
```
caller port (operate / discovery / blueprint factory)
  -> GatewayContext from verified principal (PLT-025, tenant never from payload)
  -> kill-switch check (ALP-036, unreachable = engaged)
  -> region policy: allowed (provider, endpoint) set and allowed data classes for the tenant's market (section 6)
  -> context assembly: trust envelopes, ordering, delimiters (SEC-003 3.2), data-class strip (ALP-016), redaction
  -> secret filter on prompt (ADR-0038 item 6, S23 fingerprints; feed stale = refuse)
  -> cache lookup (section 4)
  -> budget reservation (section 3) -> route + fallback chain (section 3) -> provider adapter (section 5)
  -> output filter (SEC-003 5.3) -> meter commit + meter.ai_usage + trace (section 7) -> caller
```
Every step fails closed: an error returns our error model (no provider text, no model id to customers, ADR-0016 style) and the deterministic paths keep working (spec 05).

## 3. Routing by tier, fallback, budgets
### 3.1 Tiers and the routing table
- Callers ask for a logical tier (`frontier`, `mid`, `small`; `code` is never a model) and a `purpose` (`chat`, `agent`, `build`, `simulation`, as in PLT-025). They never name a model or provider.
- The routing table is config, versioned in the repo, one row per `(tier, market)`: an ordered chain of `(provider, model_id, endpoint_region)`. Each entry carries the eval evidence that admits it (eval set, score, date). QA-003 evidence today: Sonnet and Opus classes clear 0.85 on `arabic_core`, Haiku class does not on dates and numbers. So the `small` tier may serve routing and classification only where code resolves numbers and dates; Arabic run-time chat starts on `mid`. These are single-run, unreviewed numbers (Q-123): the table must be re-admitted from a gateway-run bake-off (controlled decoding, non-Claude models, cost and latency) before G2 exit.
- A prompt or model change that regresses a blocking eval suite cannot enter the table (ai-layer, Evals).

### 3.2 Fallback
- Fallback only on transport failure: timeout, connection error, provider 5xx, 429 or overload. Never on a refusal, a filter block or a schema failure (that is a result, not an outage).
- The next entry must be the same tier or stronger, admitted by evals, and allowed by the tenant's region policy. **No silent downgrade** to a weaker tier, shorter context or skipped filter (ALP-034).
- Each fallback re-runs the budget reservation against the new entry's price, is logged (`fallback_from`, reason class) and counts toward a per-call attempt cap (default 2 retries total).
- Chain exhausted: return `model_unavailable`, no partial answer. Per-provider circuit breaker (open after N consecutive failures, half-open probe) so one outage does not burn every tenant's latency budget.
- PLT-010 (G3) later adds regional endpoint selection and licence-checked proxy evaluation on top of this chain; nothing here pre-builds it.

### 3.3 Budgets and hard caps (fail closed)
Reuse PLT-025 `BudgetPolicy`, `GatewayMeter.precheck_budget` and `BudgetExceededError` as they are. PLT-009 adds:
1. **Nesting** (ALP-031): platform >= tenant (monthly, from plan entitlement, PLT-011/PLT-021) >= session (build session, chat session) >= agent grant >= run. A lower layer only tightens. Missing policy at any configured layer = refuse, not unlimited.
2. **Reservation, not just a check.** Today `execute` prechecks on an estimate, then commits actual spend with `enforce_budget=False`, so a call can overshoot the cap. PLT-009 turns the precheck into a reservation: reserve `estimated_input + max_output` at the route's price, pass `max_output` to the provider as its output limit (derived from remaining budget), commit actual, release the rest. Overshoot is then bounded by the input estimate error only; the estimator stays conservative (3 chars/token, `gateway_port.py`).
3. **Durable meter.** The PLT-025 meter is in-process. Caps are only real across workers and restarts with a durable, atomic counter store per tenant (control-plane database, region of the tenant). Store unreachable = refuse model calls (ALP-032).
4. **Exhaustion**: refuse the call, raise `BudgetStop` in the runtime, emit `agent.budget_exceeded` (agents) or a budget alert (others), notify the owner at threshold and at cap (PLT-025 `alert_threshold_pct`). Customers see "AI actions", never tokens (ADR-0010).
5. A per-call ceiling exists independent of budgets (max input tokens, max output tokens, max attempts) so one malformed request cannot spend a month.

## 4. Prompt caching and response caching
- **Provider prompt cache** (prefix caching where the provider supports it; behaviour and prices per provider UNVERIFIED, the PLT-025 10 percent cached-input rate is an assumption). Context is assembled in a fixed order so prefixes are stable: (1) platform block: system rules, tool schemas, glossary, no tenant data, shared across tenants; (2) tenant block: tenant config and memory, starting with a per-tenant marker so no prefix containing tenant data can match another tenant; (3) the conversation and untrusted items. Cache breakpoints sit at the end of blocks 1 and 2.
- `cached_tokens` comes from the provider's usage report only and flows into PLT-025 `CallUsage.cached_tokens`; the gateway never computes a discount itself.
- **Response cache** (our own): only for calls whose whole context is platform-level L1 content and whose purpose is marked cacheable (for example a glossary translation). Key = hash of (routing-table version, model id, prompt version, full context, decoding settings). Never for anything with tenant data, personal data, untrusted content or tool results. Scope = platform; TTL bounded; invalidated on prompt or table change. A hit is still metered (zero provider tokens, `cache_hit` in the trace) and still passes the output filter.
- No cross-tenant cache of any kind (ALP-014). Per-tenant response caching is out of scope for PLT-009.

## 5. Provider abstraction and key handling
- One adapter per provider behind the PLT-025 `transport` callable: input is the assembled, filtered context plus decoding settings; output is the existing `ProviderResponse` (output, input/output/cached tokens, served model id). Adapters do no assembly, no budgeting and no logging of content. Provider-specific error text never leaves the adapter; it maps to a fixed error class.
- **Keys**: provider keys are S01 in the secret store (ADR-0038), read only by the gateway's runtime identity, 90-day rotation, never in the repo, env files, logs, traces, prompts or errors. One key per provider per market account, so a market can be cut off or rotated alone and spend is attributable per region.
- **Per-tenant isolation**: tenants share platform provider accounts; isolation is ours: tenant from `GatewayContext` only, tenant-tagged meter rows, no cross-tenant cache, output filter checks other tenants' identifiers, S23 checks are tenant + platform scoped with uniform refusals (ADR-0038). Tenant-supplied keys (bring your own key) are rejected for v1: it breaks evals, budgets and the hidden-model rule (ADR-0010).
- Egress: the gateway is the only model egress path, to an allow-list of provider hosts (prompt-injection-defence section 5, hosting-rules).
- Provider terms (no training, minimal retention, region) are checked per provider in writing before an entry enters the routing table (hosting-rules; UNVERIFIED for every provider today).

## 6. Data residency per market
The tenant's country (tenant registry, ADR-0024) selects a **region policy**: allowed `(provider, endpoint_region)` pairs and the highest data class that may leave the country. Unknown market or missing policy = refuse. Whether a model API call is a cross-border transfer at all is counsel question 10 / LEG-012 (UNVERIFIED). Sources below were located on official sites on 2026-11-21 through search results; full texts were not read end to end, so every legal reading here is UNVERIFIED until LEG-012.

| Market | What the official source says (summary) | Interim gateway default |
|---|---|---|
| KSA | PDPL (Royal Decree M/19, amended M/148 of 2023) and SDAIA's Regulation on Personal Data Transfer outside the Kingdom: transfer allowed if it does not affect national security or vital interests, limited to the minimum necessary, with a risk assessment for some transfers; safeguards are adequacy, SDAIA standard contractual clauses (four templates) or binding common rules. https://sdaia.gov.sa/Documents/RegulationonPersonalDataEN.pdf ; https://dgp.sdaia.gov.sa (SCC and BCR guidelines), accessed 2026-11-21. Which version is in force: UNVERIFIED | Redact personal data where the task allows; only approved endpoints; SCCs with each provider; transfer risk assessment on file before go-live |
| UAE | Federal Decree-Law 45/2021, in force 2022-01-02: Art. 22 transfer to adequate jurisdictions or under an agreement; Art. 23 otherwise by contract, explicit consent or listed grounds, with controls in Executive Regulations. https://uaelegislation.gov.ae/en/legislations/1972 ; https://u.ae/en/about-the-uae/digital-uae/data/data-protection-laws , accessed 2026-11-21. Executive Regulations issued: UNVERIFIED. Free zones (DIFC, ADGM) not covered | Same as KSA; record cross-border processing in the records of processing |
| Egypt | Law 151/2020; the PDPC FAQ says transfer abroad needs a prior cross-border licence or permit from the PDPC plus a legal basis; PDPC guidance cites Executive Regulations by Decision 816 of 2025. https://portal.pdpc.gov.eg ; https://pdpc.gov.eg/home , accessed 2026-11-21. Exact article text and licence process: UNVERIFIED | **Strictest default**: no personal data (C2 or above, data-classification) to any endpoint outside Egypt until a PDPC licence exists; non-personal and fully redacted content only |
| Qatar | Law 13/2016 (PDPPL), NCSA is the competent authority: Art. 15 says a controller must not restrict cross-border flows except under stated conditions (text not read); NCSA guidance treats cross-border transfer as possibly serious-damage processing that needs safeguards and a DPIA. https://ncsa.gov.qa/en/pages/personal-data-privacy-personal-data-privacy-protection-law , accessed 2026-11-21 | Redact; DPIA on file before go-live; approved endpoints only |

- In-region inference (a model endpoint inside KSA, UAE, Egypt or Qatar) for any provider: UNVERIFIED. If counsel restricts transfers, the strategy/06 self-hosting trigger moves forward; the policy table changes, the code does not.
- The policy table is config owned by the founders, changed by PR with a log entry; the gateway enforces it, it does not interpret law.

## 7. Logs and traces without customer secrets
- **Meter**: exactly the PLT-025 `meter.ai_usage` event (Contract 4, `data_class: operational`). No new usage event type.
- **Trace record per call** (gateway log, platform store in the tenant's region): call id, correlation and session id, tenant, actor kind, purpose, tier, served model id, prompt version, routing-table version, region-policy id, attempts and fallback reason classes, cache hit, token counts, cost, latency, redaction summary (counts per class, never values), filter outcomes (rule id, never the matched text), error class.
- **No content by default**: prompts, outputs and tool results are not logged for tenant data (ai-layer). Content capture for debugging needs a tenant support-access grant, a TTL, the same region and is itself audited. Secrets never: the S23 filter runs on any captured content too.
- Provider request ids are kept (to match provider-side records) but never shown to customers.

## 8. Reuse of PLT-025 (no duplication)
| PLT-025 piece | PLT-009 use |
|---|---|
| `GatewayContext`, tenant validation, spoof-key refusal | Unchanged, the only source of tenant and actor |
| `PriceBook`, `compute_call_cost` (integer micro-USD) | Prices every reservation and fallback; rates become verified rate cards (still UNVERIFIED) |
| `GatewayMeter`, `BudgetPolicy`, `precheck_budget`, `record_call` | Kept; gains a durable store behind the same interface and a reserve/commit/release step |
| `MeteredGatewayRouter`, `ModelRoute`, `transport` | `ModelRoute` becomes a chain; provider adapters plug in as `transport` |
| `build_ai_usage_event` | The only usage event emitter |
| `services/operate/runtime/gateway_port.py` (eldon) | The Operate client stays as is; Discovery and the factory get the same thin port |

## 9. Interface for callers
Callers in Eldon's lane depend on an interface, not on gateway internals: `complete(ctx, tier, purpose, items[], decoding, prompt_version) -> reply | error`, where `items` are trust-enveloped context items (SEC-003 2.2) and errors are a closed set (`budget_exceeded`, `model_unavailable`, `policy_refused`, `filter_blocked`, `invalid_request`). If founders want this frozen before the code, it is a contract change in `contracts/` with its own ADR; this design does not make it.

## 10. Test plan and acceptance checks
All tests offline with fake transports and synthetic tenants; one opt-in live smoke per provider in a dev environment with dev keys (S20), never in CI.
| ID | Check | Ref |
|---|---|---|
| MG-001 | A call without a valid `GatewayContext`, or with tenant in payload or metadata, is refused before any transport | PLT-025, SEC-020 |
| MG-002 | Each tier routes to the first admitted entry for the tenant's market; a caller cannot name a model | 3.1 |
| MG-003 | Transport failure falls back to the next same-or-stronger entry; refusal, filter block and schema failure do not fall back | 3.2, ALP-034 |
| MG-004 | No chain ever selects a weaker tier or an endpoint outside the region policy; exhausted chain returns `model_unavailable` | 3.2, 6 |
| MG-005 | Tenant, session, agent and run caps: the call that would cross any cap is refused; concurrent calls cannot jointly exceed a cap (reservation test with threads) | 3.3 |
| MG-006 | Provider output limit is set from remaining budget; actual spend never exceeds cap by more than the input estimate error | 3.3 |
| MG-007 | Meter store unavailable, kill flag unreachable, S23 feed stale, or region policy missing: every model call is refused | 3.3, ALP-032, ALP-036, ADR-0038 |
| MG-008 | Two tenants with identical messages share only the platform prefix; no tenant block or response-cache entry is reusable across tenants | 4, ALP-014 |
| MG-009 | Response cache never stores a call containing tenant, personal, untrusted or tool-result content | 4 |
| MG-010 | `cached_tokens` equals the provider-reported value and the cost matches `compute_call_cost` | 4, PLT-025 |
| MG-011 | Seeded secrets, API keys and other tenants' ids in prompt, tool result or output are blocked; logs, traces and errors contain none of them (scan the captured log) | 7, ADR-0038 |
| MG-012 | Trace and `meter.ai_usage` validate against Contract 4 and carry no prompt or output text with content capture off | 7 |
| MG-013 | Context missing a trust label is treated as L3 and alerted; prompts are assembled only by the gateway in SEC-003 order | PI-001, PI-011 |
| MG-014 | Egypt tenant: a context with C2+ personal data is refused for a non-Egypt endpoint; with redaction on, it passes | 6 |
| MG-015 | Provider error text and model ids never reach the caller's customer-facing error | 5, ADR-0016 |
| MG-016 | Re-run of `arabic_core` through the gateway (QA-003 rerun, Q-123) produces scores, cost and latency per routing entry; table entries below 0.85 are rejected | 3.1 |
| MG-017 | Repo hygiene and secret scan pass; no key, endpoint credential or `.env` file in the change | ADR-0038 |

## 11. Open items
1. Q-127 lane decision (section 1) blocks any build. 2. LEG-012 counsel opinion decides section 6 defaults. 3. Provider shortlist, terms and in-region endpoints: UNVERIFIED. 4. Gateway build versus adopt (for example a proxy library), licence check pending (ai-layer open question 1). 5. Durable meter store placement per region (with PLT-011/PLT-021).
