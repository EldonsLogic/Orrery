# Session log: payments-connector-contract

Date: 2026-11-27
Author: eldon
Tool and model: claude-code / opus-5.5
Plan IDs: DSC-021

## Summary
Payments connector contract 0.1.0 and ADR-0077 (Proposed): bring your own gateway, hosted redirect only in v1 (tokens and embedded hosted fields deferred; corrected in the partner-review round below), no card data, per-tenant credentials, verified, replay-protected and idempotent webhooks, refunds and voids R4. Contract 4 gains proposed `payment.*` event types (events 0.2.0). Branch stacked on `gov-078-module-scope` (PR #392, which adds the DSC-021 row and ADR-0076). Worker subagent session dispatched by Eldon's orchestrator; allowed paths: contracts, the ADR, PLAN row, open questions, this log, `scripts/check_contracts.py` (two example globs).

ADR-0077 was checked unused on main and on every open PR branch (2026-11-27) before use. Q-692 to Q-694 were the next free numbers on main and every open PR branch.

## Files touched
- `docs/decisions/ADR-0077-payments-connector-bring-your-own-gateway.md`, `docs/decisions/INDEX.md`: new ADR.
- `contracts/connector-payments.md`, `contracts/connector-payments.schema.json`: new contract and schema.
- `contracts/examples/payments-*.json` (4 valid), `contracts/examples/invalid/payments-*.json` (10 invalid), `contracts/tests/test_payments_contract.py`.
- `contracts/events.md` (0.2.0, payment events), `contracts/README.md`: index rows.
- `scripts/check_contracts.py`: payments example globs (valid and invalid).
- `docs/PLAN.md`: DSC-021 doing. `docs/open-questions.md`: Q-692 to Q-694.

## Decisions
- [ADR-0077](../decisions/ADR-0077-payments-connector-bring-your-own-gateway.md) (Proposed; partner pending). PCI DSS out-of-scope claim for Seshna is UNVERIFIED (Q-692); sourced from PCI SSC FAQ 1292, accessed 2026-11-27.

## Tokens or cost
Unknown.

## Next step
Partner review of PR (Tier 3: money and tenancy) and a security review by a different model. Then DSC-023 (first adapter, sandbox only) after Q-693.

## Tier 3 security review fixes (CHANGES, 9 Medium)
Worker subagent dispatched by Eldon's orchestrator; allowed paths: contracts, ADR-0077 and INDEX, the action-policy table, this log, `scripts/check_contracts.py`.
- M1 card guard: Seshna ids refuse 13+ digits even when separated; gateway ids are `<provider>:<id>` and may be numeric; code-side Luhn plus BIN-shaped check on every string (section 1.2 says what the schema cannot guarantee). Examples: dashed PAN refused, `examplepay:1234567890123` accepted.
- M2 `environment` removed from checkout (taken from the connection); new `connect_request` with a declared environment and `key_mode_check`; dev hosts sandbox only. M3 timestamp required for signed schemes, body-hash dedupe fallback. M4 re-read before every status change. M5 refund reservation, currency check, key forwarded, one open checkout per link, over-collection path. M6 approval hash binding. M8 token mode dropped for v1 (ADR-0077 item 2). M9 return page rule.
- M7: proposed rows AP-PAY-01 to AP-PAY-04 added to `docs/security/action-policy-table.md` (shared path, partner reviews on the PR).
- Lows: checkout links invoice or order only, refund links credit notes only; two event types added; `XXX` and metal or fund codes refused plus the ISO 4217 table in code; `minor` maximum 2^53-1; `10.0` refused (examples load non-integers as Decimal); unknown endpoint 404 with no tenant audit, body cap, rate limit; 90-day key rotation; void only from `authorised`; each invalid example asserts its keyword and path.
- Not done: Q-692 to Q-694 stay open. The PR now exceeds the ~450 changed-line budget (stated in the re-review comment).

## Partner Tier 3 review fixes (CHANGES at b3650cb6: 4 High, 11 Medium, 3 Low)
Worker subagent dispatched by Eldon's orchestrator; allowed paths: contracts, `services/blueprint/events/` and its tests, docs, this log. Failing tests were written first (events registry and contract tests), then fixed. Gateway docs fetched and confirmed 2026-11-27: Moyasar, HyperPay, Tap, Stripe, PCI SSC FAQ 1588, the SIX ISO 4217 list; the PayTabs support page did not describe callback signing, so PayTabs is listed as unsupported in v1.
- H1: 14 `payment.*` types registered in `services/blueprint/events/schemas/types.json` with `data.payment.schema.json` and samples; `payment` added to the reserved domains. H2: R4 refund basis `unallocated` and state `unallocated` (over-collection, mismatch, cancelled order); mismatch never `payment.failed`. H3: refunds keyed by gateway refund id and amount. H4: marker committed with the apply, re-read never skipped, dedupe by object id plus status plus amount, sweep, per-provider retention (HyperPay 30-day retries, so 35 days).
- M5 section 11 and AP-PAY-05 (R4, Q-695). M6 full section 5 set, SoD and step-up at execution. M7 staged write-once secrets, probe-derived account id. M8 and M9 per-gateway schemes, only a signed timestamp gets a window. M10 S11 and S13 split, revoke at once, the Owner rotates. M11 transitions table. M12 UUIDs accepted, 60,000 random keys tested. M13 `hosted_fields` deferred after v1 (FAQ 1588). M14 sources and the decimal-string rule (`PAY-AMT-003`). M15 DSC-023 acceptance list (the row is already `blocked` from GOV-078).
- Lows: stale token wording (PLAN, ADR-0076 item 10, this log), schema gaps, the agent may draft only a checkout.
- Merged `gov-078-module-scope` and kept its row statuses (DSC-023 and DSC-024 `blocked`).
- Not done: the different-vendor security review is still owed; the partner's personal acceptance items stay with the partner; Q-692 to Q-695 open. The PR remains over the ~400-line guide (the M5 and M11 material was kept here rather than split, see the PR comment).
