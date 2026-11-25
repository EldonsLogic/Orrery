# Session log: partner-sprint

Date: 2026-11-25
Author: partner
Tool and model: claude-code (requested log label; coordinator is Codex GPT-6.1 Sol)
Plan IDs: SEC-004,CMP-023

## Summary
Live parallel-sprint coordination for the partner lane. Account verified as sayegh9; clean checkout cut from origin/main. The session-start checklist, standing rules, generated status and latest three logs were read. Current gate remains G0; later-gate work follows its plan rows.

## Decisions
- Partner confirmed in this session that CMP-010 follows the CMP-003/ERP-015 method: agent-drafted deterministic code, Tier 3 line-by-line human review, accountant review before production.
- Existing decisions preserved: keep all 41 old worktrees and rescue branches; #309 parked for Eldon after three review rounds; Gemini 4 Argon is the approved fallback while the other reviewer account is limited.

## Wave 0
- Started the approved GitHub watcher under a 7200-second timeout. Restart after events; ask before restarting at the time limit.
- Open PRs checked: no new Eldon review on #300, #306, #309, #310, #311 or #312. #296 remains open, so GOV-071 waits. Adapter lane waits for #310 and #312.
- Historical ERP-031 bench logs requested for runs 45623345992 and 45636525010; verdict pending.
- Triggered SEC-004 workflow_dispatch on main; result pending.

## Path-lock table
| Task | Branch | Allowed paths | State |
|---|---|---|---|
| Coordination | sec-004-cmp-023-partner-coordination-6 | docs/PLAN.md and this live log; coordinator-only shared-file assembly on task branches | held |
| CMP-010 design/build | pending claim | docs/compliance/ksa-vat-return.md; components/compliance/ksa_vat_return/** | reserved, no dispatch |
| PLT-027 | pending claim | docs/decisions/ADR-0069-gateway-live-binding-audit-spool.md | reserved, no dispatch |
| CE-SEC-008 part 1 | pending claim | api/endpoints.py; guarded_apply/schema_reconciler.py; guarded_apply/ddl_plan_gate.py; new test_ce_sec_008_deploy_path_durability.py, under the change-engine package | reserved, overlap check pending |
| PLT-024 regression | pending claim | services/gateway/tests/test_plt_024_request_headers.py | reserved, no dispatch |
| Adapter lane | existing #310 and #312 | adapter/frappe_backend.py; adapter/engine.py | blocked by open PRs |
| GOV-071 | pending #296 | recompute partner-lane rename paths after #296 merges | waiting |

## Reservations
- ADR-0069 for PLT-027, subject to open-PR number verification before dispatch.
- Q-609 is the next reserved question number; no child may allocate a number. Coordinator owns PLAN, open questions, ADR index, tests.yml, RULES and AGENTS.
- No implementation child edits PLAN. No child may run git, including status or stash. Worktrees are retained.

## Dispatches and results
None yet; claim PR must merge first.
- W0.4: removed only the three PLAN row additions from #312 in commit 05f111d8; code unchanged. Rows copied verbatim into this claim, with CE-SEC-008 doing. Comment posted on #312.
- R3/R5 audit: fetched origin, diffed all 17 open PRs against their actual bases. No Wave 1 implementation/design path overlaps an open PR or another reserved task. ADR numbers in flight stop at 0068; Q references stop at 608. ADR-0069 reserved for PLT-027; Q-609 held for coordinator use.
- Claim sets CMP-010, PLT-027, CE-SEC-008 and BPL-043 doing. GOV-071 remains todo because #296 remains open. BPL-044 is recorded todo; its adapter lane is unavailable.
- SEC-004 dispatched run 45646846161 on main at 1fa88849; in progress. An additional historical successful SEC-004 run 45088110814 exists after the previously reported failing run; no closure claimed without inspecting the fresh run.

- Coordinator handoff: the thread moved from Codex GPT-6.1 Sol to Claude Opus 5.5 (high) at the partner's request; sprint state recovered from this log and the child worktrees.
- Dispatched after the claim merged: T1a CMP-010 design (Claude Opus, running) and T2 PLT-027 design (Claude Opus). T3 CE-SEC-008 part 1 and T5 PLT-024 header tests not yet dispatched.
- T2 PLT-027 result: ADR-0069 Proposed (154 lines, design only, 29 threats each with a named proposed test). Coordinator added the INDEX entry, follow-up rows PLT-028 to PLT-031 (G3 go-live row depends only on earlier-gate Eldon rows) and Q-609 to Q-614 for Eldon's lane. check_docs, check_repo_hygiene and check_plan_independence pass. Security review by a different model is pending.

- PR #316 opened for PLT-027. Security review dispatched to Codex GPT-6.2 Sol (high), read-only.
- Dispatched T3 CE-SEC-008 part 1 (Claude Sonnet 5.5 high, own worktree) and T5 PLT-024 header tests (Claude Sonnet 5.5 medium, own worktree) with the sprint-6 briefs unchanged.

- PLT-027 security review (GPT-6.2 Sol): changes required, with 9 High, 5 Medium and 1 Low findings (audit loss when an intent is acked before its outcome, spool rollback and truncation, unauthenticated flood capacity, WSGI framing limits, business-write idempotency, per-route method and effect declarations, stale role reads, stable session id, upstream cookie control, transport-level caps, the existing adapter correlationId, path redaction, the PLT-029 to PLT-028 dependency). Sent back to the author child as revision round 1.
- T5 PLT-024 result: 5 tests, 62 gateway tests pass, and a pass-through mutant fails all 5. PR #318 opened with its own log; Tier 2, waiting for Eldon's review.
- T1a CMP-010 result: docs/compliance/ksa-vat-return.md, 253 lines, design only, five official ZATCA sources fetched on 2026-11-25. Only Boxes 7 to 9 are confirmed by number. Coordinator allocated Q-615 to Q-622. PR #319 opened; cross-model review dispatched to GPT-6.2 Sol (high). Open point: the code location (the doc proposes zatca_sa/vat_return.py; the path lock reserved ksa_vat_return/**).
- GitHub returned intermittent 500 and 502 errors on push and PR creation; retries succeeded and no duplicate PRs were created.

- PLT-027 revision round 1: author fixed all 15 findings (none rebutted; the code claims in findings 7, 10, 11 and 12 were confirmed in the code), and the ADR grew from 154 to 187 lines. Coordinator applied the PLAN changes (PLT-028 to PLT-031 text; PLT-029 and PLT-030 now depend on PLT-028; PLT-031 gated on Q-609, Q-302 and Q-613) and reworded Q-609, Q-610, Q-611, Q-613 and Q-614. Fresh re-review dispatched.

- PLT-027 re-review round 2 (GPT-6.2 Sol, head 4c7176a9): changes required. Resolved: findings 8, 9, 10, 12 and 13. The rest are partly resolved, with 6 new High defects (recovery metadata after pruning, checkpoint race, placeholder HMAC and crash before quarantine, preauth isolation and record-size ceiling, one stalled tenant stopping the instance, cross-principal dedupe disclosure and admin step-up) and 2 Medium. Advice accepted: split PLT-028. Sent to the author as revision round 2.
- CMP-010 review (GPT-6.2 Sol, head 7b0d9880): changes required, 9 High and 4 Medium. Main points: the Art. 63 threshold reportedly amended to SAR 15,000; reverse-charge VAT in Box 9 under full recovery; mixed zero-rated subtotals; deferred versus customs-paid imports; note filing state; calendar quarters; deferred input claims; refusal output must carry no amounts; a replay and taxpayer-binding key. Sent to the author as revision round 1, with an instruction to verify every reviewer citation against the official text before acting.

- PLT-027 revision round 2 committed (35f53c26): PLT-028 split into PLT-028 (local durability) and PLT-032 (forwarding and integrity conformance), with Q-613 and Q-614 updated. Re-review round 3 (GPT-6.2 Sol): changes required. M1 and M2 resolved, H1 to H6 partly resolved; 6 new High and 1 Medium, all in the spool, checkpoint and receipt protocol. **Parked for a founder decision**, as the coordinator proposed, with options posted on PR #316: (a) one more focused round, (b) simplify the protocol, or (c) move the state machines into PLT-028 and PLT-032 with their own review. Review rounds: 3.
- T3 CE-SEC-008 part 1 result: implemented test-first, but 108 existing tests failed closed on the new lock-timeout read-back in two test doubles outside the child's paths. Coordinator applied the child's 4-line patch to `adapter/simulated_frappe.py` and `tests/test_api_deployment.py` (no open-PR overlap), and the full suite then passed: 1555 passed, 86 skipped, 0 failed (baseline 1514 passed, 86 skipped). Coordinator added the CI step. PR #322 opened with its own log; cross-model review dispatched to GPT-6.2 Sol.
- CMP-010 revision round 1: all 13 findings fixed after the author read each reviewer citation (the Art. 63(3) threshold of 15,000 confirmed in the Umm al-Qura gazette, calendar quarters confirmed, 16 box labels taken from the illustrative form). Coordinator applied the Q changes, marked Q-621 PARTLY ANSWERED and added Q-623 to Q-626. Commit 5baf921e; re-review round 2 dispatched.

- CMP-010 re-review round 2 (GPT-6.2 Sol, head 5baf921e): changes required, converging. Resolved: 1, 4, 6, 8, 9, 10 and 12; the rest partly resolved. All FETCHED sources were confirmed. New: 3 High (mixed document kinds reconciling to one subtotal, `claim_date` not bound to the period, non-XML source bypassing BR-CO-17) and 2 Medium, plus vector fixes. Sent to the author as revision round 2.
- CE-SEC-008 review (GPT-6.2 Sol, head 56b00a23): changes required. The suite counts were confirmed (1555 passed, 86 skipped). Findings: 4 High (a regression where live workflow, report and property-setter deployments fail at prepare; the evidence namespace collides with caller keys and rollback accepts evidence rows; a pre-lock read view; no recovery entry point consumes the journal), 4 Medium, 1 Low. Sent to the implementation child as revision round 1, with the write paths widened to the two test doubles and a schema change or new API reported as follow-up. PR #322 must not merge before this is fixed.

- Later in the sprint (after the ADR-0069 park entry above; the earlier review entries were on #316 and are merged):
  - CMP-010: GPT re-review round 3 found 1 High and 3 Medium. Fixed in round 3 (68ba9b17). Round 4 (d184b227) applied Eldon's #319 review, including the founder decision recorded by Eldon for both founders that BR-CO-17 becomes a warning, not a refusal. The April 2025 amendments: Art. 54 and Art. 40(10) FETCHED, Art. 63 routes UNVERIFIED. Q-616, Q-620 and Q-624 updated. A final narrow GPT re-check is dispatched.
  - CE-SEC-008 (#322): round 1 fixes committed (500134f6). Full suite 1591 passed, 0 failed. Follow-ups CE-SEC-009 (recovery entry point) and CE-SEC-010 (journal table) added on the PR. GPT round 2: changes required (2 High: the fresh read view commits caller writes, and lock and lookup equality differ; 3 Medium). Sent back as round 2.
- Partner instructions relayed from the side thread "Count Completed Rows" at about 16:26Z. Verified against the partner's own words before acting.
  - #318 PLT-024: merged (Tier 2, Eldon approved at ad99d276).
  - #316 PLT-027: merged as Proposed on the partner's Tier 3 say-so. Eldon's H1 and H2 checked as met at dc41fb05, with a findings table posted. The GPT round 3 items (R3-1 to R3-7) and Eldon's M3 to M6 and Lows are recorded in the ADR section "Open items before Accepted". Main merged in; the INDEX conflict was resolved by keeping ADR-0066 and ADR-0069.
  - #311 CMP-040: main merged in (PLAN conflict resolved: main's rows kept, CMP-040 marked done, a stray blank table line removed), then merged (Tier 2, Eldon approved at c9249ae8; the only change since was the merge of main).
  - #312 BPL-043: P1 fixed. Main was merged into the #310 base (1b44f015), and the base was merged into #312 (fd81304f), taking the base PLAN.md, so #312 no longer touches PLAN.md. The first attempt (dropping the hunk alone) failed the pre-push task trail, because the base lacked the BPL-043 row. An unpushed local merge from the previous coordinator, in the old bpl-043 worktree, was left untouched and not pushed. Full suite 1549 passed. Waiting for Eldon's re-review (Tier 2).
  - #306 ERP-033: Medium fixed test-first (8d043225; new case `approver-not-the-owner-holder`, red then green), main merged (e28ec6e8). Full suite 1571 passed. Findings table posted. Waiting for the partner's Tier 3 say-so.
  - #310 BPL-041: M1, L1 and L2 dispatched to a Claude Sonnet 5.5 child, test-first, in a fresh worktree at 1b44f015.
  - Cross-model reviews (GPT-6.2 Sol) of Eldon's Claude-authored PRs, posted as sayegh9 request-changes reviews; none were merged:
    - #321 BPL-039: 3 High (field order breaks apply and rollback, an unapplied precision change reported as applied, the secret-key check bypassed) and 3 Medium.
    - #279 QA-009: 1 High (fails against current main with CMP-MAP-002 then BS-015) and 2 Medium.
    - #278 WEB-007: 1 High (branding saved with the wrong permission) and 3 Medium.
    - #275 WEB-008: 1 High (credentials can reach the URL through a native GET) and 2 Medium.
  - #300 CMP-036: waiting for a partner decision on Q-601 (mark answered: ZATCA mandates half-up; negative-amount question kept open). Not acted on.
  - GOV-071: unblocked by #296; not started yet.

- After #327:
  - CMP-010 (#319):
    - Round 5 (ea847a20) made the UUID to source-document binding one-to-one (T43).
    - Partner decisions on 2026-11-25 recorded at 84732556: the code goes in `components/compliance/zatca_sa/vat_return.py`, and Q-601 is answered.
    - Ready for Eldon's re-review and the founders' Tier 3 read; status posted.
  - #310 BPL-041:
    - M1, L1 and L2 fixed test-first (c095a415), by a Sonnet child. Full suite 1543 passed.
    - Merged into #312 (29faa4d3), which gives 1556 passed. Findings table posted.
    - Waiting for Eldon.
  - GOV-071 (#328): rename to Seshna in partner-lane prose and visible text, by a Sonnet child.
    - Environment variables and package names are kept for GOV-002 (ADR-0066 item 7).
    - Tests pass. Waiting for Eldon (Tier 2).
  - CE-SEC-008 (#322):
    - Review rounds 2 to 7 (GPT-6.2 Sol). The child fixed rounds 2 to 4.
    - The coordinator fixed rounds 5 to 7 directly:
      - one authoritative site identity per site;
      - a read-only alias for legacy host-name rows;
      - the alias taken from the injected runtime;
      - the simulator's `IN` lookup.
    - Follow-up rows CE-SEC-009, CE-SEC-010 and CE-SEC-011 carry the deferred parts.
    - Review loop stopped after round 7. Full suite 1698 passed, 0 failed. Ready for Tier 3; status posted.
  - The partner said "approve", read as approving all three pending decisions:
    - #306 ERP-033: merged. Eldon approved at e28ec6e8, and the partner gave the Tier 3 say-so.
    - Q-601: marked answered on #300 (f6b22274), with the negative-amount question kept open. Main merged in; 205 country-pack tests pass. Waiting for Eldon's re-review and a Tier 3 say-so.
    - CMP-010 code location: `zatca_sa/vat_return.py`.

- After #329 (partner: "proceed"):
  - Merged:
    - #329 (Tier 1 log).
    - #310 BPL-041 (Tier 2, Eldon approved at c095a415).
    - #312 BPL-043 (Tier 2, Eldon approved at 29faa4d3). It was retargeted from the #310 branch to main through the REST API, because `gh pr edit` fails on the deprecated Projects-classic field.
  - #328 GOV-071: Eldon's blocker fixed at 5c051142.
    - The tax invoice's font stack is now Readex Pro for body text and Cairo for titles and number columns, with `tabular-nums`. Alexandria and Arial are removed.
    - Added a fonts-and-footer test. GOV-071 marked done.
    - ERP-035 (todo) carries moving the invoice's 36 hard-coded colours to tokens and adding it to the literal guard.
    - Waiting for Eldon's re-review.
  - #322 CE-SEC-008: Eldon's security review (at 56b00a23) sent to the child as round 5.
    - F1 and F5 are already fixed.
    - F2, F3, F4 and F6 to F10 are in progress.
    - `frappe_backend.py` is now allowed, since #310 and #312 have merged.
    - real-bench-tests passes on the PR.
  - #319 CMP-010: main merged (07a191f5; open-questions kept both the Q-609 to Q-614 and the Q-615 to Q-626 blocks). Eldon's narrow re-review (N1 to N4, M3, M5, Lows) sent to the author as round 6.
  - #300 CMP-036: Eldon approved at f6b22274 after a line-by-line read. Waiting for the partner's Tier 3 say-so.

- After #330:
  - Reviewer switch (partner instruction): GPT models hit their usage limits, so cross-model reviews now use Antigravity (Gemini 4 Argon, high) and Claude.
  - CMP-010 (#319):
    - Round 6 (8c341e0b) answers Eldon's N1 to N4, M3, M5 and the Lows.
    - Q-628 added. Q-627 was skipped because Eldon's #326 uses it.
    - The PR body counts are corrected.
    - Waiting for Eldon.
  - CE-SEC-008:
    - Eldon approved #322 at 750dc543. The F2 to F10 work (049c349c) had landed after that, so it was reverted on #322 (b6bb4840) to keep the approved content, and moved to `ce-sec-008-part-2`.
    - On part 2, the child fixed GPT's two Medium findings. Gemini 4 Argon then gave "approve with nits", and the coordinator fixed its two Lows (CE-SEC-011 text; N13 and N20 mutant tests).
    - PR #331 is open.
  - Partner: "proceed and merge":
    - **#322 merged** (CE-SEC-008 part 1).
    - **#300 merged** (CMP-036).
  - #331 retargeted to main:
    - When main was merged in, part 2's versions of the files #322 reverted were kept (a revert of the revert), after checking that main touched them only through the revert.
    - A new part-2 log was added for the task trail.
    - Full suite: 1775 passed, 0 failed.

- After #332:
  - Eldon approved #331, #332 and #328.
  - Merged:
    - **#332** (Tier 1 log).
    - **#331** (CE-SEC-008 part 2), on the partner's Tier 3 say-so ("yes merge it").
  - **CE-SEC-008 marked done.** Parts 1 and 2 are merged. Follow-ups stay in CE-SEC-009, CE-SEC-010 and CE-SEC-011.
  - #328 GOV-071: main merged in (PLAN conflict: kept the CE-SEC rows and ERP-035). CI running; the PR is watched and will merge on green (Tier 2, Eldon approved).
  - #319 CMP-010: Eldon's re-review at 8c341e0b found no number or vector wrong (T1 to T53 pass). Two sentence-level fixes (F1 ledger_only duty; F2 digest edge cases and a golden value) plus Lows sent to the author as round 7.

- After #333: Wave 2 approved by the partner (agents A to D; Gemini reviews of Eldon's open PRs deferred, remind later; mark PLT-027 done).
  - Plan cleanup:
    - Done: BPL-043 (#312), PLT-027 (ADR-0069 merged as Proposed; open items owned by PLT-028 to PLT-032) and CMP-036 (#300 delivered the full row).
    - BPL-041 stays doing, because slice 2 (real-bench CI sets the REQUIRE flag) is still open.
    - The `tenant_role_holders` resolver Eldon asked for on #306 already exists as SEC-025. A duplicate ERP-036 was dropped after Eldon's review of #334, and its detail was folded into SEC-025's text: per-request read with no cache, tenant from the verified token, suspended or away members and pending invitations counted. The SEC-025 gate (ADR and security review before any build) is kept. ERP-034 covers the scheduled report.
  - Claimed (doing):
    - ERP-035: invoice tokens, Sonnet.
    - CE-SEC-009 and CE-SEC-010: one design ADR-0070, Opus.
    - PLT-028: spool state-machine spec, Opus.
    - CE-SEC-011 slice 1: Sonnet. The dedicated connection and the keyed MAC wait for ADR-0070.
  - Reviews go to Gemini 4 Argon, because the GPT models are at their usage limit.
  - Reserved: ADR-0070 and Q-629 onward, both allocated by the coordinator only.

## Tokens or cost
Unknown.

## Next step
Verify historical evidence; move #312 plan hunks; merge the Tier 1 claim PR, then dispatch disjoint Wave 1 tasks.
