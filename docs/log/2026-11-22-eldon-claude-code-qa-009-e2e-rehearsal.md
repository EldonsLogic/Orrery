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
- The simulated month runs on the QA-011 eval fixture's tool set and mapping, not on one derived from this Blueprint (only revision, id and digest are stamped), so the "simulated Blueprint" leg is a stand-in. The month has no sales-order step (the simulator has none), and the golden sale is in the simulated month, before go-live.
- Open questions Q-53 and Q-77: compiler output targets `change_engine`, the adapter fake accepts only `frappe` and lacks the `attachment` field type the trading template uses; the test patches both on the fake (contract 16.12, compiler open question 4). Real fix belongs to the adapter fake or the template.
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

## Review fixes (partner review at 51a36b8d, main merged in)
- High: both sandbox and live builds now use `evals/tests/fixtures/engine-mapping-interview-template.json` (the shared golden-path mapping minus the three ZATCA invoice fields the interview Blueprint lacks; contracts/ untouched). The happy path reaches `live`.
- Medium: the simulated month now uses the Tool API generated from the sandbox Blueprint and a replay mapping read off it. The R3 invoice post is asserted held (nothing posted, receivable `blocked_by_approval`) before the approval stand-in releases it and the posted totals are checked against the spec.
- Medium: the build state machine runs the real Blueprint validator (fixture registry); new test: an invalid draft stays in `draft` (BS-006, no engine call).
- Low: `FakeHarness()` directly, not `make_harness()`; new test sets a bogus `ADAPTER_HARNESS`.
- Replaces the earlier gap "month runs on the QA-011 tool set and mapping" and narrows it: the generated Tool API cannot carry the stock legs (a purchase receipt has no unit cost, a delivery note needs a sales order), so the month replays the sale only and the 900.00 stock value is no longer asserted (opening stock is a cutover opening balance). The generated invoice has `payment_terms_days`, not a due date, so the simulated port ages the 150.00 receivable from the invoice date (bucket 0_30, not "not due"); the test sums the buckets. The approval release is a test stand-in: the simulated port parks R3 and has no approval queue.
