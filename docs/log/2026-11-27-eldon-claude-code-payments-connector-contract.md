# Session log: payments-connector-contract

Date: 2026-11-27
Author: eldon
Tool and model: claude-code / opus-5.5
Plan IDs: DSC-021

## Summary
Payments connector contract 0.1.0 and ADR-0077 (Proposed): bring your own gateway, hosted checkout or tokens only, no card data, per-tenant credentials, verified, replay-protected and idempotent webhooks, refunds and voids R4. Contract 4 gains proposed `payment.*` event types (events 0.2.0). Branch stacked on `gov-078-module-scope` (PR #392, which adds the DSC-021 row and ADR-0076). Worker subagent session dispatched by Eldon's orchestrator; allowed paths: contracts, the ADR, PLAN row, open questions, this log, `scripts/check_contracts.py` (two example globs).

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
