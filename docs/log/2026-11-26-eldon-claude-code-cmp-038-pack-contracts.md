# Session log: cmp-038-pack-contracts

Date: 2026-11-26
Author: eldon
Tool and model: claude-code / opus-5.5
Plan IDs: CMP-038

## Summary
CMP-038 slice 1: draft (0.1.0) JSON Schemas for the country pack publish record, signed country index and tenant pin, shared by CMP-038 (publisher) and CMP-039 (loader), per ADR-0071 revision 2 (Proposed, #344) and Eldon's answers to Q-652 to Q-657 (Q-656 moved these formats into `contracts/`).

## Files touched
- contracts/country-pack-common.schema.json, country-pack-record.schema.json, country-pack-index.schema.json, country-pack-pin.schema.json: new draft schemas.
- contracts/country-pack-store.md: contract note with assumptions and changelog; contracts/README.md: table row.
- contracts/examples/country-pack-*.json (7 valid), contracts/examples/invalid/country-pack-*.json (28 negative).
- contracts/tests/test_country_pack_contracts.py: schema tests plus a reference check of record-local validator rules (distinct signers, assertion refs, statement and content digests, time order).
- scripts/check_contracts.py: registers the three schemas and checks that negative examples fail.
- docs/PLAN.md: CMP-038 set to doing (eldon).

## Decisions
- No new ADR: the contract follows ADR-0071 (Proposed). Deviations and assumptions are listed in contracts/country-pack-store.md (role names, `predecessorDigest` on the index, structured pin `approval`, `auditId`, per-signer WebAuthn `signerSignature` required in production).

## Checks
- check_contracts OK (21 schemas); contracts/tests 55 passed; check_docs, check_repo_hygiene, check_plan_independence OK.
- Not run in CI: contracts/tests (no CI step yet; .github is shared). The negative examples are covered in CI by check_contracts.

## Tokens or cost
Unknown.

## Next step
- Partner confirms CMP-039 (CMP-042 to CMP-044) can consume these schemas; fold any change into ADR-0071 revision 3.
- CMP-038 next slice: change record body for withdrawals, floor raises and follow-up closures; the publish service and staff screen.

## Review fix (round 2)
- Patterns in `country-pack-common`, `-record`, `-pin` schemas now end with `(?![\s\S])` instead of `$`: Python `re` let `$` match before a trailing newline. Same pattern works in ECMA-262.
- `contracts/tests/test_country_pack_contracts.py`: test that a trailing `\n` is refused for `contentDigest` and `packId`.
- `contracts/country-pack-store.md` assumption 5: `memberRef` is out of scope for pin approvals.
- Checks: check_contracts OK (21 schemas); contracts/tests 56 passed; check_docs and check_repo_hygiene OK.
