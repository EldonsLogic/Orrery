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
