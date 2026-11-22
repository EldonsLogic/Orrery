# Session log: qa-009-e2e-rehearsal

Date: 2026-11-22
Author: eldon
Tool and model: claude-code / sonnet-5.5
Plan IDs: QA-009

## Summary
QA-009 `doing` (not `done`): an offline, deterministic rehearsal runs the real interview, template, gap analysis, quote, DSC-009 owner approval, BPL-020 build state machine, compiler, simulator and adapter fake end to end on synthetic data, with refusal paths (unapproved, wrong principal, changed content, rejection, failed sandbox apply). Stacked on PR #224.

Chain: interview fixture -> draft input -> Blueprint draft (template) -> gap report and quote -> sealed owner approval -> machine owner_approved (machine asks the real `OwnerApproval.verify`) -> team review -> compile and apply on a fake sandbox site -> simulated golden-path month (spec numbers: sales 150.00, stock value 900.00, receivables 150.00, no tax) -> owner sign-off -> cutover -> production compile and apply on a second fake site -> live.

Gaps (why the row stays `doing`; each is a stand-in, not hidden):
- No Operate chat in the chain (OPR-010 is a dependency, but G2-1 also needs the one chat); the owner screen is the DSC-009 service, not the web screen (WEB-027).
- The golden-path sale posts on the simulator's in-memory tenant (documents, totals), not on the adapter fake: the adapter fake models configuration only, so debit and credit postings (COGS, trial balance) are not asserted. They need the real bench (BPL-028, ERP-021).
- Review queue port is the build-state test fake, not the control-plane review queue (PLT-013); identity is a fake table.
- Compiler output targets `change_engine`, the adapter fake accepts only `frappe` and lacks the `attachment` field type the trading template uses; the test patches both on the fake (contract 16.12, compiler open question 4). Real fix belongs to the adapter fake or the template.
- Sandbox and live use the draft and the synthetic verified mapping; no real engine, no ZATCA or other compliance step.

## Files touched
- evals/tests/test_e2e_rehearsal.py: the rehearsal (9 tests; no new CI wiring, `evals/tests` is already mapped in tests.yml)
- docs/PLAN.md: QA-009 set `doing`

## Decisions
- None, or link to ADR / strategy decision.

## Tokens or cost
Not measured.

## Next step
QA-009: add the Operate chat leg and a real-bench golden-path sale (BPL-028) before `done`; fix the adapter fake target and `attachment` type gaps.
