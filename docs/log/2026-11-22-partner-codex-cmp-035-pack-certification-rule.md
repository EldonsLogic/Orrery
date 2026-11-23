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

## Review fixes
- Addressed PR #282 findings 1–6. Production validates the entire companion manifest contract, refuses owner self-review case-insensitively and fails closed when the contract or validation dependency is unavailable. Synthetic fixtures now satisfy the contract. Timestamp format validation uses a deterministic check because the pinned jsonschema install lacks its optional date-time format dependency.
- Moved the minimal evidence labels, traversal and path-coverage helpers from test support into `evidence.py`; shared tests still pin the same `SOURCED_LABELS`. Production refuses unusable fact records and any UNVERIFIED fact overlapping a locked path, including tax, e-invoicing and payroll. No shipped fact label changed.
- Accountant names, sign-off references and reviewer entries need a letter or digit after NFKC normalization and removing Cf characters. Evidence certification and nested accountant records have closed key sets. Secondary sign-off diagnostics use an explicit validity flag, independent of other message text.
- Proposed ADR-0063 explicitly amends ADR-0059 Decision 2's official-only production requirement; ADR-0059 is untouched. Updated the framework with the manifest, locked-fact and closed-key rules. Sandbox/test companion-read behaviour is unchanged, including draft packs without manifests.
- Tests first: the go-live module ran 28 methods with 44 failing subtests before implementation. After fixes, `python3 -m unittest discover -s components/compliance/country_pack/tests -t . -v` (the CI command) passed all 113 methods, no skips. Separately, `python3 -m unittest components.compliance.country_pack.tests.test_country_packs -v` passed all 27 methods.
- `python3 scripts/check_docs.py`: 0 errors, 0 warnings; `check_repo_hygiene.py`: pass; `check_plan_independence.py`: pass; `scan_secrets.py`: 0 hits. `git diff --check` passed. Used the existing pinned dependencies in an external temporary environment.
- Finding 7 remains out of scope: companion symlink handling is pre-existing behaviour and is unchanged. Residual: trusted bundle publication must account for those symlinks. No real accountant details, sign-offs or personal data were added. CMP-035 remains doing pending Tier 3 founder and cross-model re-review; no merge or phase exit claimed.

## Review fixes, round 2
- Production evidence locks now union `tax`, `eInvoicing` and `payrollHooks` with the declared policy. Every present locked leaf needs a known non-UNVERIFIED fact on that leaf or an ancestor. Objects are traversed; lists (including empty lists), scalars and nulls are whole leaves, matching shipped evidence. Any UNVERIFIED overlap still refuses, including an ancestor of a locked path, regardless of accepted coverage elsewhere.
- All fact paths must exist in the pack; policy locale paths remain relative to localeDefaults, but evidence paths use full pack-root paths. Locked SECONDARY facts require a read source and pass the same source checks as shipped-pack tests. Moved leaf traversal, path resolution and source validation into `evidence.py`; `pack_checks.py` re-exports them and the shared tests call the same read-source helper. No duplicated source rule, pack data changes or SOURCED_LABELS changes.
- Tests first: `python3 -m unittest components.compliance.country_pack.tests.test_country_pack_go_live_gate -v` ran 36 methods with 20 failing subtests before implementation. Added eight methods covering repros 1–3, sibling/minimum coverage, unknown paths, SECONDARY sources, the UNVERIFIED ancestor and accepted leaf/list/null coverage. The ancestor method fails when the reverse-overlap condition is removed in memory, killing that mutation without editing production files.
- With the pinned `services/blueprint/requirements.txt` dependencies in an external environment: CI command `python3 -m unittest discover -s components/compliance/country_pack/tests -t . -v` passed 121 methods, no skips; `python3 -m unittest components.compliance.country_pack.tests.test_country_packs -v` passed all 27 methods. Required docs, hygiene, independence and secret checks passed (0 docs errors/warnings, 0 secret hits); `git diff --check` passed.
- Direct production-load audit: SA, AE, EG and QA are all refused. Each remains `tested`/`unverified`, lacks certification approvals and a named reviewer, contains UNVERIFIED locked facts and lacks accepted coverage for locked leaves. SA examples: tax filing/number patterns, invoice retention and payroll; AE/EG/QA also lack accepted tax and e-invoicing coverage. Total refusal diagnostics: SA 41, AE 59, EG 67, QA 63. Their SECONDARY source records add no refusals; sandbox/test behaviour and all shipped facts/values remain unchanged.
- Updated Proposed ADR-0063 and the framework with the minimum lock set, exact leaf granularity, overlap, unknown-path and shared SECONDARY source rules. Open founder decision: `goLiveBlockers` handling remains unchanged and is not enforced by this new production fact check. CMP-035 stays doing for Tier 3 founder and cross-model re-review; no merge or phase exit claimed.

## Review fixes, round 3
- Medium: production now applies the full shared source rule to every `VERIFIED-OFFICIAL` and `SECONDARY` fact, including unlocked facts. Both labels require a read source. The shared rule checks HTTPS URLs with a hostname and no whitespace, read/accessed exclusivity, unread notes, and valid calendar access dates no later than today. Both review repros (missing sources and HTTP/future access date) are refused; pinned source-label snapshots remain unchanged.
- Low 1: shared fact validation requires every `PLATFORM-DEFAULT` fact to name a `ref`, matching shipped-pack tests; production also validates any supplied sources. Open founder decision, recorded in Proposed ADR-0063: whether this label may cover statutory locked leaves at all. Existing eligibility with a reference is preserved pending that decision.
- Low 2: an unresolved locked policy path refuses production loading, including the review's `holiday.calendarRefx` typo.
- Low 3: added the public-loader regression with `week.weekendDays` locked, valid whole-array coverage and an `UNVERIFIED` fact on `localeDefaults.week.weekendDays[0]`. Removing the `p[` prefix coverage in memory makes this test fail with `PackValidationError not raised`; the mutation is caught without editing production files.
- Tests first: new module `python3 -m unittest components.compliance.country_pack.tests.test_certification_evidence -v` ran eight methods with 15 failing cases before implementation; afterward all eight passed. The indexed-array method already passed before implementation and independently caught the requested mutation. Fixtures contain synthetic approvals only and assert sandbox/test acceptance for each refusal.
- Used the pinned `services/blueprint/requirements.txt` dependencies, including jsonschema 4.26.0, in an external temporary environment. CI command `python3 -m unittest discover -s components/compliance/country_pack/tests -t . -v`: 129 passed, no skips. Separate `python3 -m unittest components.compliance.country_pack.tests.test_country_packs -v`: 27 passed, no skips.
- `python3 scripts/check_docs.py`: 0 errors, 0 warnings; `python3 scripts/check_repo_hygiene.py`: pass; `python3 scripts/check_plan_independence.py`: pass; `python3 scripts/scan_secrets.py`: 0 hits; `git diff --check`: pass.
- Updated Proposed ADR-0063 and the framework to match the code. Open founder decision: `goLiveBlockers` handling remains unchanged and is not enforced by the production fact check. No pack data, statutory maths, labels or sandbox/test rules changed. CMP-035 remains doing pending Tier 3 founder and different-model security re-review; no merge or phase exit claimed.

## Review fixes, round 4 (coordinator, Claude Opus 5.5)
The round 3 Claude Opus re-review approved, with one Low: a PLATFORM-DEFAULT `ref` only had to be truthy, so `" "`, `True` and `["x"]` passed, although the docs say "nonempty". It now has to be a string that is not blank after `strip()`. Tests first: 6 failing subtests before the change, none after. The Nits are left as is: the host-local date, no test for `accessed == today`, and an invalid port being accepted.

## Founder acceptance (2026-11-23)

Eldon approved the PR at `0d38f5a` (Tier 3, line-by-line read posted). The partner agreed Eldon's two answers (PLATFORM-DEFAULT only on a named per-market product-choice list; open `goLiveBlockers`, `pendingRefs` or UNVERIFIED locked `factsOutsideSchema` entries refuse production), which are built in CMP-036, and accepted ADR-0063. ADR-0063 status and its INDEX row are now Accepted. The merge with main in `1c9c370` was clean apart from PLAN rows.
