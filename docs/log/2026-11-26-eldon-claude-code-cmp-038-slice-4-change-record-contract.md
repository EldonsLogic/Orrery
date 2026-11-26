# Session log: cmp-038-slice-4-change-record-contract

Date: 2026-11-26
Author: eldon
Tool and model: claude-code
Plan IDs: CMP-038

## Summary
Slice 4 of CMP-038 (stacked on #360): documented the change record body in the store contract (0.2.0, assumption 5 replaced), added its JSON Schema, and made packpublish validate each change record (schema plus built-in two-person rules) before commit, refusal PP-062. Tests first; 482 control-plane tests pass.

## Files touched
- contracts/country-pack-store.md, contracts/README.md: version 0.2.0, change record documented
- contracts/country-pack-change-record.schema.json: new
- services/control-plane/packpublish/{changerecord,workflow,errors}.py: validation before commit, PP-062
- services/control-plane/tests/packpublish/test_change_record_schema.py: new tests

## Decisions
- None. Follows ADR-0071 and the store contract. The CI step has only pytest, so there only the built-in rules run; the schema runs where jsonschema is installed.

## Tokens or cost
Unknown or approximate, if known.

## Next step
CMP-039 (partner, #344) reads the change record. CMP-038: upgrade scheduling, real ports, staff screen. Tier 3: needs a different-model review.

- Follow-up (Eldon's #344 answer): adopted ADR-0071's domain-separated WebAuthn challenge in the store contract (now 0.3.0) and the record schema; `canon.signoff_challenge` and the fake verifier use it; `predecessorDigest` already chained the index and is documented for the loader walk-back.
