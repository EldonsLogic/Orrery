# Session log: opr-followups

Date: 2026-11-20
Author: eldon
Tool and model: claude / sonnet-5.5
Plan IDs: OPR-002,OPR-009,OPR-010

## Summary
Tier 3 (agent authority) follow-up hardening of merged OPR-002, OPR-009 and OPR-010: the router's confirmation binding (action id, args hash, risk, expiry) now travels through the chat service into `ChangeService.confirm`, the pending is set only after the preview was shown (Q-265 in part, Q-282), and the LOW findings of the PR #194 and PR #199 re-reviews are fixed, tests first. Open: Q-320 to Q-323.

## Files touched
- services/operate/chat/ (models, router, service, store, __init__): `RouteResult`, `PendingBinding`, `IntentRouterAdapter`, `MemoryPendingStore`, change-by-chat turn handling
- services/operate/router/ (models, router, rules): N1 to N5 (role reads, finite clock and expiry, Arabic grants, slash ambiguity)
- services/operate/change/ (errors, policy, service): `change_superseded`, flattened tax ids, maxLength lowering needs review
- services/operate/tests/{chat,router,change}/: new test files for each fix
- docs/architecture/{chat-service,intent-router,change-by-chat}.md, docs/open-questions.md (Q-265, Q-282 resolutions; Q-320 to Q-323)

## Decisions
- None new. Applies Q-265 and Q-282 of the existing change-by-chat design.

## Tokens or cost
Unknown.

## Next step
Q-320 (act confirmation through the Tool API), Q-321 (shared pending store). Cross-model review of this Tier 3 PR.

## Review round (PR #205)
Fixed H1 (pending only if the preview passed the output gate, else `change_preview_failed`), M1 (any turn that does not answer the pending clears it and cancels the proposal), M2 (proposal capped at the previewed op count, preview lists every op), L1 to L5 (joined tax ids, maxLength add, Arabic grant forms, punctuated yes, expired cancels).
