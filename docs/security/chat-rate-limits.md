# Chat rate limits and budget guard (SEC-009, chat side)

Status: draft
Owner: eldon
Approved by: pending (partner review with a different model)

Plan ID: SEC-009. Threats: T9 (cost abuse) and T16 (denial of service) in [threat-model.md](threat-model.md). Code: `services/operate/runtime/ratelimit.py`, wired in `services/operate/chat/service.py` and `chat/runner.py`. Budget source: the model-call contract [model-call.md](../../contracts/model-call.md) section 6 (PLT-026). The gateway side of SEC-009 (edge rate limits, WAF, per-tenant HTTP quotas) is not here; see section 6.

## 1. Rules
1. Keys are (tenant, user) and (tenant) from the verified principal (`Principal.tenant_id`, `Principal.subject`; for tools the `ToolRequest` the loop builds from the verified `Caller`). No session id, login token, message id, tool argument or model output selects a key, so a new session or a second login does not reset a user's quota.
2. Fail closed. Not retryable, never shown as "too quick": a missing or blank tenant or user id (`identity_missing`); a kind with no rule, or a rule set with any invalid rule (`policy_missing`: limit must be an `int` from 1 to 1,000,000, window a finite number from 1 s to 7 days, scope `user` or `tenant`, no duplicate kind, scope and window); a clock value that is not a finite number from 0 to 1e10 s, or any store error (`store_error`). Retryable: over a limit (`user_limit`, `tenant_limit`) with `retry_after_s`.
3. A refused event is not recorded, and every rule is checked before any is recorded. A bad clock value records nothing, so the limiter recovers when the clock does.
4. The clock must be monotonic seconds (`time.monotonic` in a host, `TickClock` in tests). A value that goes backwards is clamped to the last good one.
5. Over a limit uses the Tool API code `rate_limited` (contracts/tool-api.md section 7); the model-call contract has no rate code and none is added.
6. Every refusal is logged (logger `ratelimit`: kind, tenant, user, reason, `retry_after_s`; no message text). Chat refusals are also audited as `chat.rate_limited` with kind, reason and `retry_after_s`, through the same audit port as `chat.message_received` (not yet a registered event type, like the other `chat.message_*` events). Tool refusals are in the run trace (span `error_code: rate_limited`).
7. Memory: every 1,024 admits, keys whose newest hit is outside their window are dropped.

## 2. Where the checks sit
| Check | Where | Counts | Refusal seen by |
|---|---|---|---|
| Chat turn | `ChatService._send`, after message validation and after the one-run check accepted the run (a refusal releases the run in the same lock) | Each accepted new message. A send refused as `chat_run_in_progress` costs nothing | Client: `RUN_ERROR` `chat_rate_limited` with the wait in minutes (`errors.chat_rate_limited`, en and ar), or `chat_limit_unavailable` for a fault (`errors.chat_limit_unavailable`, not retryable) |
| New session | `ChatService.open_session`, only when it creates a session | Each created session; resuming one is free | Caller: `ChatFailure` with the same two codes |
| Tool call | `RateLimitedTools` around the Tool API port; `loop_runtime_factory` always wraps (its `limiter`, else defaults on its clock) | Each dispatched call, proposals included | Model: Tool API error `rate_limited` (with `retry_after_s` when retryable); the call is never sent and the run stops (`stop_reason: rate_limited`, code `budget_exceeded`) instead of spending model steps |
| Budget | `BudgetGuard` around a model-call contract port | The port's reserve-then-commit check | Loop: `BudgetStop(reason)`, the run ends with `budget_exceeded` |

The chat service and the runtime factory turn limits on by default. Pass the same `RateLimiter` to both so one instance holds every counter.

Replays of a finished message id are free on purpose: they start no run, no model call and no tool call, and the client retries them after a dropped connection. They are bounded by the gateway-side request limits (section 6).

## 3. Proposed defaults (not facts)
`DEFAULT_RULES` in `ratelimit.py`. These are proposed starting values chosen to sit well above one person typing and well below scripted flooding; they are UNVERIFIED and not measured on real traffic. Tune them from PLT-025 metering (Q-561).

| Kind | Scope | Window | Limit |
|---|---|---|---|
| turn | user | 60 s | 20 |
| turn | user | 3600 s | 300 |
| turn | tenant | 60 s | 200 |
| session | user | 3600 s | 30 |
| tool | user | 60 s | 60 |
| tool | tenant | 60 s | 600 |

Per-run caps (`runtime.Limits`: steps, tool calls, tokens, cost) stay as they are; these limits bound how many runs and calls a user or tenant starts across runs. Test and eval harnesses that run more than 20 turns for one user on a frozen clock must pass their own rules.

## 4. Budget guard
The model-call port reserves the worst-case cost against every budget layer before dispatch and refuses with `budget_refused` when any layer would cross its cap, has no policy, has no id, or the meter store is unreachable (contract section 6, ALP-032). `BudgetGuard` turns every `budget_refused` refusal, raised or returned, into `BudgetStop(reason)` with the reason limited to the contract's set (`exceeded`, `policy_missing`, `meter_unavailable`, `layer_unbound`; anything else is `unknown`). Another raised refusal is re-raised; another returned result that is not a reply raises `RuntimeError`; the loop maps both to `internal_error`. It is tested against the PLT-026 fake port; nothing in production builds a contract port yet, so the guard is wired when the gateway client exists (PLT-009).

## 5. Client text
Pre-run refusals render in the service's default locale, as other pre-run chat errors do. `web/app` maps no `chat_*` code yet and shows its generic error; that mapping moves with the other chat codes (Q-261).

## 6. Not covered here
1. State is per process. A host with more than one instance needs a shared counter store (Q-562); until then the effective limit is per instance.
2. Gateway side (partner lane, `services/gateway/`): edge and per-IP limits, WAF and CDN, per-tenant HTTP quotas covering the free paths here (replays, validation failures, history reads), OTP limits (T12), and the budget layers and reservation of the real model-call implementation (PLT-009, PLT-021).
3. Per-tool limits and external-send limits (prompt-injection-defence section 5.5) stay with SEC-020 and OPR-004.
