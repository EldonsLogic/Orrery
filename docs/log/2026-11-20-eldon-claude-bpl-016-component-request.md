# Session log: bpl-016-component-request

Date: 2026-11-20
Author: eldon
Tool and model: claude
Plan IDs: BPL-016

## Summary
Built the component request pipeline: a gap analysis request becomes a ComponentRequest with a model-drafted, validated spec and test plan, refusals for ledger, tax, e-invoicing, payroll and audit scope and for per-client needs, dedupe by stable key and against the library, and a human-only approval state machine. Tier 3 (decides what code the factory may be asked to write).

## Files touched
- services/blueprint/component_request/: codes, text, draft, pipeline, labels.json (ar, en), README
- services/blueprint/tests/component_request/: tests (hostile drafts, injection, duplicates, forbidden scopes, Arabic, tampering)
- docs/PLAN.md (BPL-016 done), docs/open-questions.md (Q-420 to Q-424)

## Review fixes (Opus review of PR 216)
Risk class now derived by policy.py from the Tool API tables (default deny, allow-list of artifact kinds and benign scopes); normalised scope scan as backstop; request key bound to the need; evidence per tenant with deterministic generalisation (tenant count or human attestation); stored records validated on read, optional HMAC digest; drafting_failed park and human reopen; clock bound; drafter cannot approve. Q-425 to Q-429 added.

## Decisions
- No new ADR. Follows ADR-0048 (propose, not act). AI drafts exclude stock, ledger, tax and permission risk classes (Q-421).

## Tokens or cost
Unknown or approximate, if known.

## Next step
BPL-017 (factory drafts code from an approved record), PLT-014 (review screens). Different-model security review of the scope and risk filters.
