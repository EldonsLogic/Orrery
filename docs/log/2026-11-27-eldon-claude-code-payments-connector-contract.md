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
