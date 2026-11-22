# Chat rate limits and budget guard (SEC-009, chat side)

Status: draft
Owner: eldon
Approved by: pending (partner review with a different model)

Plan ID: SEC-009. Threats: T9 (cost abuse) and T16 (denial of service) in [threat-model.md](threat-model.md). Code: `services/operate/runtime/ratelimit.py`, wired in `services/operate/chat/service.py` and `chat/runner.py`. Budget source: the model-call contract [model-call.md](../../contracts/model-call.md) section 6 (PLT-026). The gateway side of SEC-009 (edge rate limits, WAF, per-tenant HTTP quotas) is not here; see section 5.

## 1. Rules
1. Keys are (tenant, user) and (tenant) from the verified principal (`Principal.tenant_id`, `Principal.subject`; for tools the `ToolRequest` the loop builds from the verified `Caller`). Nothing in a request body or model output selects a key.
2. Fail closed: a missing tenant or user id (`identity_missing`), a kind with no rule or an invalid rule (`policy_missing`) and a clock or store error (`store_error`) refuse. Over a limit is `user_limit` or `tenant_limit` (retryable, with `retry_after_s`).
3. A refused event is not recorded, so hammering does not extend the lock-out; every rule is checked before any is recorded.
4. Refusals use the model-call contract's refusal shape (`code`, `reason`, `retryable`) with the Tool API code `rate_limited` (the model-call contract has no rate code).
5. The clock is injected (monotonic seconds); tests use `TickClock`.

## 2. Where the checks sit
| Check | Where | Counts | Refusal seen by |
|---|---|---|---|
| Chat turn | `ChatService._send`, after message validation, before the one-run check | Each new message; a replay of a finished message id is free | Client: `RUN_ERROR` code `chat_rate_limited`, text from the bilingual table (`errors.chat_rate_limited`) |
| Tool call | `RateLimitedTools` around the Tool API port (`loop_runtime_factory(limiter=...)`) | Each dispatched call, proposals included | Model: Tool API error `rate_limited`; the call is never sent |
| Budget | `BudgetGuard` around a model-call contract port | The port's reserve-then-commit check | Loop: `BudgetStop`, the run ends with `budget_exceeded` |

The chat service turns the limiter on by default. Pass the same `RateLimiter` to `ChatService` and `loop_runtime_factory` so one instance holds both counters.

## 3. Proposed defaults (not facts)
`DEFAULT_RULES` in `ratelimit.py`. These are proposed starting values chosen to sit well above one person typing and well below scripted flooding; they are UNVERIFIED and not measured on real traffic. Tune them from PLT-025 metering (Q-561).

| Kind | Scope | Window | Limit |
|---|---|---|---|
| turn | user | 60 s | 20 |
| turn | user | 3600 s | 300 |
| turn | tenant | 60 s | 200 |
| tool | user | 60 s | 60 |
| tool | tenant | 60 s | 600 |

Per-run caps (`runtime.Limits`: steps, tool calls, tokens, cost) stay as they are; these limits bound how many runs and calls a user or tenant starts across runs.

## 4. Budget guard
The model-call port reserves the worst-case cost against every budget layer before dispatch and refuses with `budget_refused` when any layer would cross its cap, has no policy, has no id, or the meter store is unreachable (contract section 6, ALP-032). `BudgetGuard` turns every `budget_refused` reason into `BudgetStop(reason)`, re-raises every other refusal (the loop maps it to `internal_error`) and fails closed on a result that is neither a reply nor a refusal. It is tested against the PLT-026 fake port; nothing in production builds a contract port yet, so the guard is wired when the gateway client exists (PLT-009).

## 5. Not covered here
1. State is per process. A host with more than one instance needs a shared counter store (Q-562); until then the effective limit is per instance.
2. Gateway side (partner lane, `services/gateway/`): edge and per-IP limits, WAF and CDN, per-tenant HTTP quotas, OTP limits (T12), and the budget layers and reservation of the real model-call implementation (PLT-009, PLT-021).
3. Per-tool limits and external-send limits (prompt-injection-defence section 5.5) stay with SEC-020 and OPR-004.
4. Pre-run refusals render in the service's default locale, as other pre-run chat errors do.
