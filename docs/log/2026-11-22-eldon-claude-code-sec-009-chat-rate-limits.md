# Session log: sec-009-chat-rate-limits

Date: 2026-11-22
Author: eldon
Tool and model: claude-code / opus-5.5
Plan IDs: SEC-009

## Summary
Chat side of SEC-009 in `services/operate`: a per-tenant and per-user sliding-window limiter for chat turns and tool calls (fail closed, injected clock, identity from the verified principal only), wired at the chat entry point and around the Tool API port, plus a budget guard that turns a PLT-026 `budget_refused` reservation into the runtime's `BudgetStop`. Stacked on PR 244 (PLT-026). The gateway side stays open, so SEC-009 is `doing`.

## Files touched
- services/operate/runtime/ratelimit.py: `RateRule`, proposed `DEFAULT_RULES`, `RateLimited`, `RateLimiter`, `RateLimitedTools`, `BudgetGuard`; exported from `runtime/__init__.py`.
- services/operate/chat/service.py: `limiter=` (default on), new turns admitted before the one-run check; replays free. chat/errors.py: `chat_rate_limited` (en and unreviewed ar). chat/runner.py: `loop_runtime_factory(limiter=...)` wraps the tool port.
- services/operate/tests/runtime/test_ratelimit.py (17 tests, budget guard against the fake port), services/operate/tests/chat/test_chat_rate_limits.py (5 tests).
- services/operate/README.md: SEC-009 section.
- docs/security/chat-rate-limits.md: design note with proposed defaults.
- docs/open-questions.md: Q-561 (defaults), Q-562 (shared counter store). docs/PLAN.md: SEC-009 doing.

## Decisions
- None needing an ADR. Defaults are proposals (Q-561). Refusal shape mirrors the model-call contract with the Tool API code `rate_limited`; the chat wire code is `chat_rate_limited`.

## Tokens or cost
Unknown.

## Next step
- Partner (gateway lane, `services/gateway/`): edge and per-IP limits, WAF and CDN, per-tenant HTTP quotas and the real budget layers under PLT-009 and PLT-021; then SEC-009 can close.
- Wire `BudgetGuard` when a contract client replaces `gateway_port.py` (PLT-009). Founders: Q-561, Q-562.

## Review fixes (cross-model security review of PR 270, head 2738aa9)
Tests first; all four Medium and ten Low findings addressed. 20 targeted mutants of `ratelimit.py`, `chat/service.py`, `chat/runner.py` and `runtime/loop.py` are all killed, including the four that survived the review (lock removal, tool key on a request field, chat-session keying, BudgetGuard dict branch).
- M1: clock values must be finite numbers in 0..1e10 s, else `store_error` with nothing recorded; the key recovers with the clock. M2: the rule set is validated once (int limit 1..1e6, finite window 1 s..7 days, known scope, no duplicates); any junk makes every check `policy_missing`.
- M3: faults (`identity_missing`, `policy_missing`, `store_error`) reach the user as `chat_limit_unavailable` (not retryable, en and ar); over a limit is `chat_rate_limited` with the wait in minutes from `retry_after_s`. Every refusal is logged (`ratelimit`) and chat refusals are audited as `chat.rate_limited`.
- M4: a turn is counted only after `begin_run` accepted it; a refusal releases the run in the same lock.
- Lows: `loop_runtime_factory` always wraps tools; periodic sweep of stale keys; backwards clock clamped; tool `rate_limited` carries `retryable` and `retry_after_s` and stops the run (`stop_reason: rate_limited`, `runtime/loop.py`); `limiter is None`; BudgetGuard reasons closed to the contract set (else `unknown`); `RateLimited.as_dict` removed; new sessions metered per user (kind `session`), keyed on the subject; replays stay free (documented); Q-261 notes that `web/app` maps no `chat_*` code yet; `test_chat.py` error-table test fills the `{minutes}` template.

## Approval Lows (review of df69da2)
Tests first. N1: refusals logged once per key and reason until the key is admitted again (repeats counted, one summary line), chat audit only on the first refusal and emitted after `ChatService._lock` is released. N2: Q-262 notes `chat.rate_limited` needs registering. N3: backwards steps up to 5 s clamped; larger ones rebase later hits to the new value, so one spurious high reading cannot freeze the limiter. N4: `sweep_every` validated at construction (invalid is `policy_missing`, nothing recorded). N5: tests for live keys surviving a sweep, the refusal log line and tool keying on argument fields; 27 of 27 targeted mutants killed. N6: recorded in the design note section 6.
- Q-561 and Q-562 answered by Eldon in chat (2026-11-22): defaults accepted for every plan; shared cache with per-instance fallback on outage (not built yet). Design note, module docstring and open-questions updated.

## Review fixes (partner review of #270 at 7e8473c, 2026-11-23)
- Merged origin/main; only `docs/open-questions.md` conflicted, both sides kept (5 cells per row).
- Medium (atomic writes): `RateLimiter._admit` now rolls back counters already charged if a later append fails, so an errored event costs nothing. Fault-injection test `test_failed_append_rolls_back_counters_already_charged` (second counter's append fails: first unchanged, `store_error`); it failed before the fix.
- Low (ordering): `test_later_rule_refusal_leaves_earlier_counters_unchanged`. Confirmed by mutation (recording right after each check) that it fails.
- Q-562 wording (partner's "limits divided by the number of servers") is not changed yet: pending a founder decision.
- Checks: operate tests 705 passed, 1 skipped; check_docs, check_repo_hygiene and check_plan_independence pass.

## Correction (2026-11-23): Q-562 supersedes the statement at line 38
The line-38 statement ("shared cache with per-instance fallback on outage") is superseded, historical text kept. Decided by both founders (partner's answer on #270, accepted by Eldon): counters live in the platform's shared cache; on a cache outage each server counts on its own with every limit divided by the number of servers, so the effective limit does not multiply. Not built yet, pending the shared cache. Q-562, the design note and the `ratelimit.py` docstring now say this.
