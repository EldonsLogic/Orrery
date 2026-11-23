# Chat rate limits and budget guard (SEC-009, chat side)

Status: draft
Owner: eldon
Approved by: pending (partner review with a different model)

Plan ID: SEC-009. Threats: T9 (cost abuse) and T16 (denial of service) in [threat-model.md](threat-model.md). Code: `services/operate/runtime/ratelimit.py`, wired in `services/operate/chat/service.py` and `chat/runner.py`. Budget source: the model-call contract [model-call.md](../../contracts/model-call.md) section 6 (PLT-026). The gateway side of SEC-009 (edge rate limits, WAF, per-tenant HTTP quotas) is not here; see section 7.

## 1. Rules
1. Keys are (tenant, user) and (tenant) from the verified principal (`Principal.tenant_id`, `Principal.subject`; for tools the `ToolRequest` the loop builds from the verified `Caller`). No session id, login token, message id, tool argument or model output selects a key, so a new session or a second login does not reset a user's quota.
2. Fail closed. Not retryable, never shown as "too quick": a missing or blank tenant or user id (`identity_missing`); a kind with no rule, or a rule set with any invalid rule (`policy_missing`: limit must be an `int` from 1 to 1,000,000, window a finite number from 1 s to 7 days, scope `user` or `tenant`, no duplicate kind, scope and window); a clock value that is not a finite number from 0 to 1e10 s, or any store error (`store_error`). Retryable: over a limit (`user_limit`, `tenant_limit`) with `retry_after_s`.
3. A refused event is not recorded, and every rule is checked before any is recorded. A bad clock value records nothing, so the limiter recovers when the clock does.
4. The clock must be monotonic seconds (`time.monotonic` in a host, `TickClock` in tests). A backwards step of up to 5 s is clamped to the last good value. A larger one is treated as a clock reset: hits stamped after the new value are moved to it (counts kept, windows restart), so one spurious high reading cannot freeze the limiter. The cost: a spurious forward jump expires the windows that were open before it, once.
5. Over a limit uses the Tool API code `rate_limited` (contracts/tool-api.md section 7); the model-call contract has no rate code and none is added.
6. Refusals are logged (logger `ratelimit`: kind, tenant, user, reason, `retry_after_s`; no message text) once per key and reason until that key is admitted again; the repeats are counted and logged as one line then, so a flood cannot multiply log lines. Chat refusals are audited as `chat.rate_limited` (kind, reason, `retry_after_s`) on the same first-refusal rule, after the chat lock is released, through the same audit port as `chat.message_received`. The type is not registered yet (Q-262). Tool refusals are in the run trace (span `error_code: rate_limited`).
7. Memory: every 1,024 admits (`sweep_every`, a positive `int`, else every check is `policy_missing`), keys whose newest hit is outside their window are dropped; the log-suppression table is cleared at 10,000 entries.

## 2. Where the checks sit
| Check | Where | Counts | Refusal seen by |
|---|---|---|---|
| Chat turn | `ChatService._send`, after message validation and after the one-run check accepted the run (a refusal releases the run in the same lock) | Each accepted new message. A send refused as `chat_run_in_progress` costs nothing | Client: `RUN_ERROR` `chat_rate_limited` with the wait in minutes (`errors.chat_rate_limited`, en and ar), or `chat_limit_unavailable` for a fault (`errors.chat_limit_unavailable`, not retryable) |
| New session | `ChatService.open_session`, only when it creates a session | Each created session; resuming one is free | Caller: `ChatFailure` with the same two codes |
| Tool call | `RateLimitedTools` around the Tool API port; `loop_runtime_factory` always wraps (its `limiter`, else defaults on its clock) | Each dispatched call, proposals included | Model: Tool API error `rate_limited` (with `retry_after_s` when retryable); the call is never sent and the run stops (`stop_reason: rate_limited`, code `budget_exceeded`) instead of spending model steps |
| Budget | `BudgetGuard` around a model-call contract port | The port's reserve-then-commit check | Loop: `BudgetStop(reason)`, the run ends with `budget_exceeded` |

The chat service and the runtime factory turn limits on by default. Pass the same `RateLimiter` to both so one instance holds every counter.

Replays of a finished message id are free on purpose: they start no run, no model call and no tool call, and the client retries them after a dropped connection. They are bounded by the gateway-side request limits (section 7).

## 3. Proposed defaults (not facts)
`DEFAULT_RULES` in `ratelimit.py`. These are proposed starting values chosen to sit well above one person typing and well below scripted flooding; they are not measured on real traffic. Eldon accepted them as the starting values on 2026-11-22 (Q-561): the same on every plan, changed per tenant only by the platform team, and revisited with pilot metering (PLT-025).

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

## 6. Known behaviour (accepted for now)
1. A tool `rate_limited`, including a limiter fault, ends the run as `budget_exceeded` with `budget_kind: rate_limited`, so the user reads the budget text for a rate limit.
2. A host that passes custom rules without a `session` rule gets `chat_limit_unavailable` on every new session (fail closed).
3. If `end_run` raises while releasing a refused turn, the user gets `internal_error` and the session stays blocked until the run TTL.

## 7. Not covered here
1. State is per process. A host with more than one instance needs a shared counter store; until then the effective limit is per instance. Decided (Q-562, both founders, 2026-11-23): counters go in the platform's shared cache, and if that cache is down each server counts on its own with every limit divided by the number of servers during the outage, so the effective limit does not multiply and chat keeps working instead of refusing everyone. Not built yet: it needs the shared cache. The fail-closed `store_error` here covers the in-process store only.
2. Gateway side (partner lane, `services/gateway/`): edge and per-IP limits, WAF and CDN, per-tenant HTTP quotas covering the free paths here (replays, validation failures, history reads), OTP limits (T12), and the budget layers and reservation of the real model-call implementation (PLT-009, PLT-021).
3. Per-tool limits and external-send limits (prompt-injection-defence section 5.5) stay with SEC-020 and OPR-004.
