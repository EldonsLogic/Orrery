# Session log: cmp-035-pack-certification-rule

Date: 2026-11-22
Author: partner
Tool and model: codex (GPT-6.1 Sol, high reasoning)
Plan IDs: CMP-035

## Summary
Implemented the Q-560 production certification record checks. Signed secondary evidence is accepted only with a named market accountant, sign-off reference, one founder approval and a matching manifest naming its reviewer. CMP-035 stays doing pending Tier 3 review. No tax figures, statutory maths or shipped pack evidence changed.

## Files touched
- `components/compliance/country_pack/certification.py`: companion JSON record checks, pack/version binding, accountant, founder and reviewer requirements; returns clear refusal reasons.
- `components/compliance/country_pack/loader.py`: production invokes record validation and permits signed secondary evidence; sandbox/test skip companion reads.
- `components/compliance/country_pack/tests/test_country_pack_go_live_gate.py`: four additional test methods with synthetic records, positive combinations and mutations for every refusal reason; existing fixtures now supply production records.
- `docs/compliance/country-pack-framework.md`: record format and production trust boundary; caller's synthetic-data responsibility under ADR-0059.
- `docs/decisions/ADR-0063-country-pack-certification-record.md` and `INDEX.md`: Proposed decision.
- `docs/PLAN.md`: CMP-035 status cell only, todo to doing.
- This session log.

## Evidence
- Initial system Python discovery failed because jsonschema was absent. Installed the existing pinned dependencies and pre-commit in a temporary environment outside the repo; no dependency changes.
- Tests first: `python3 -m unittest components.compliance.country_pack.tests.test_country_pack_go_live_gate -v`: 18 methods, 96 failing subtests and 4 errors before implementation. The errors were the expected refusal of correctly signed secondary packs.
- After implementation: CI command `python3 -m unittest discover -s components/compliance/country_pack/tests -t . -v`: 103 passed, no skips.
- Shared pack evidence: `python3 -m unittest components.compliance.country_pack.tests.test_country_packs -v`: 27 passed, including pinned SOURCED_LABELS. No source label, locked value or existing pack status changed.
- `python3 scripts/check_docs.py`: 0 errors, 0 warnings; `check_repo_hygiene.py`: pass; `check_plan_independence.py`: pass; `scan_secrets.py`: 0 hits. Git diff whitespace check passed.
- Existing CI discovery includes the extended module, so no workflow edit is needed. No UI added; error strings are internal diagnostics following the existing loader exception interface.

## Decisions
- [ADR-0063](../decisions/ADR-0063-country-pack-certification-record.md), Proposed: approval metadata in evidence.json, reviewer in manifest.json; no pack or component schema change.
- Main's highest ADR was 0060. Checked open PR files with `gh pr list`: 0061 and 0062 were reserved; selected 0063. The T3 PR-list tool could not read the repository; GitHub CLI succeeded on retry.
- Only trusted, reviewed deployment bundles supply these records. Credential verification, approval authenticity and actual accountant sign-off remain UNVERIFIED by this loader; founder publication review checks them. No real names, approvals or personal data used.

## Tokens or cost
Unknown.

## Next step
Eldon's Tier 3 line-by-line and different-model security review of CMP-035 and Proposed ADR-0063 before merge. This implementation sub-agent is not authorized to merge. No phase or gate exit claimed.
