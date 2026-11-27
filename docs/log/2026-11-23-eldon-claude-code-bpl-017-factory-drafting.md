# Session log: bpl-017-factory-drafting

Date: 2026-11-23
Author: eldon
Tool and model: claude-code (Opus 5.5, subagent)
Plan IDs: BPL-017

## Summary
First slice of BPL-017 (Eldon approved starting the row on 2026-11-23): a deterministic drafter that turns a schema-checked component request into an AI-drafted candidate component (manifest, code, tests) in the BPL-015 sandbox, through the PLT-026 model-call port (fake port only, no live model). Stacked on PR #244 (PLT-026). Row stays `doing`.

## Files touched
- services/blueprint/factory/drafting.py: request checks (schema, injection, rigid zone, proven plain), one port call (tier mid, purpose build, reserved minimum output), draft checks (closed shape, path check, rigid zone, fixed fields, registry admission), sandbox write outside the repo, BPL-015 check, draft record and one audit record per outcome.
- services/blueprint/factory/request.schema.json: closed request shape (internal input, not a contract).
- services/blueprint/tests/factory/test_drafting.py: 24 tests (injection, ledger, VAT, Arabic tax, payroll, tenant login, unproven need, model refusal, budget exhaustion, writes outside the sandbox, failing draft tests, tests not run without the flag, manifest failing the schema, rigid or malformed drafts, sandbox root in the repo).
- services/blueprint/README.md: short section.
- docs/decisions/ADR-0065 (Proposed) and INDEX; docs/PLAN.md: BPL-017 `doing`.

## Decisions
- [ADR-0065](../decisions/ADR-0065-ai-drafted-components-enter-factory-as-drafts.md) Proposed. ADR-0064 left free for OPR-013, which builds on the same base.

## Checks
- `pytest services/blueprint/tests`: 2105 passed. New file: 24 passed.
- Not checked: a real gateway (none yet); running candidate tests under an OS sandbox (INF-014 does not exist, so the flag stays off for customer-influenced requests).
- CI path filter: the blueprint tests now import `services/operate/runtime/model_call_fake.py`; a change only under services/operate will not re-run them.

## Tokens or cost
Unknown.

## Next step
BPL-017 next slices: the promotion step with a reviewer-not-requester check (ADR-0034), input from an approved BPL-016 record, a real gateway adapter once PLT-009 lands, i18n labels if the codes reach a UI. Real routing of refused requests to a human queue (today only a reason code).

## Review fixes (Fable 5.2 security review of PR 287 at 24b63ce: CHANGES, 4 High, 5 Medium, 6 Low)
- H1: the draft's `provides` must be exactly the requested need (capability = component id, entity `riskClass: plain` required), `classify` re-run on the ref, parameters through `policy.field_verdict` (no money types, no `affectsLedgerOrTax`), JSON declared fields through `field_verdict`, script-like keys refused, money words (BPL-016 restricted and financial tokens plus invoice, debit, credit, posting, levy) on manifest and file contents.
- H2: `component_request/text.py`: Arabic prefixes و ف ب ك ل and ال/لل removed (the old لل slice kept one ل), spaced single Arabic letters joined, `ٹ` folded, adjacent-token pairs ("ta x"), new English and Arabic scope words. invoice, debit and credit stay out of the shared list (BPL-016 allows a link to a sales invoice; its tests rely on that) and live in the drafter's list. Auth list extended (admin, sign-in, log in, RBAC, access control, privilege, تسجيل دخول, أذونات, كلمة السر). BPL-016 tests: 438 passed.
- H3: the record is built inside the try; any exception is `FDR-010` with an audit record; temp folder then atomic rename, removed on any failure; paths compared after normpath, NFC and casefold, `.` and file/folder clashes refused before writing; audit written before the rename, so a failing sink leaves no draft.
- H4: `run_candidate_tests` removed; candidate code never runs in this slice (FAC-012 expected).
- M1 forced `dataHandling`, `blocking: true`, reserved and existing ids refused. M2 richer audit, refused records carry their own status, meter event id and `mid` tier required. M3 per-client and personal-data checks. M4 a HIGH static finding or level `none` refuses and removes the draft. M5 ADR-0065 items 2, 3, 5, 6, 7 reworded; L2 and L6 as ADR notes.
- L1 filter also on folded text, described as a backstop. L3 CI blueprint filter now covers `services/operate/runtime/` and `contracts/model-call*`. L4 `draft_exists` before the model call. L5 no requester role exists: Q-600 added (renumbered from Q-599, which #286 took).
- Tests: `test_drafting.py` 84 passed; `services/blueprint/tests` 2165 passed.
- Lanes: own lane only (`.github/` and `docs/open-questions.md` are shared paths and need the partner's review).
