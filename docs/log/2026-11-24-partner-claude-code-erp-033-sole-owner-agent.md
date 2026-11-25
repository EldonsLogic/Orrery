# Session log: erp-033-sole-owner-agent

Date: 2026-11-24
Author: partner
Tool and model: claude-code (Sonnet 5.5, implementation sub-agent; review by a different model still needed, Tier 3)
Plan IDs: ERP-033

## Summary
The action-policy enforcer now allows the Q-41/Q-563 sole-owner self-approval for the R1 to R3 rows AP-STOCK-01 and AP-FIN-01 only, with step-up, only when a trusted role-holder fact shows the owner is the single human holding the approving roles, and flags the result and the audit record as self-approved; R4 and every other case keep the strict deny.

## What was already there
- Nothing: `_approve` excluded the submitter, the drafter, the agent owner (and editors on SOD-DIFF-AUTHOR rows) unconditionally. Neither Q-41 (human initiator) nor Q-563 (own agent) was implemented, and no review-report hook existed.

## Rule implemented (docs/security/action-policy-table.md section 6, Q-41, Q-42, Q-563, ALP-030, TC-22, TC-23)
The exclusion is lifted for an approval only when all hold (`_sole_owner`, `action_policy_enforcer.py`):
- row is in the allow-list `_SOLE_OWNER_ROWS` (AP-STOCK-01, AP-FIN-01); R4 rows (AP-FIN-02, AP-PERM-01, AP-BPL-01) and any new row are out by default;
- exactly one approval is required (a tightened count of 2 cannot be met by one person);
- the approval carries step-up, even where the row itself does not require it;
- the approver is a human holding the `owner` role;
- `ActionContext.tenant_role_holders` (trusted, resolver-filled) lists, for every approving role of the row, only that approver: role holding, not availability. Missing, malformed, unlisted approver, or any second holder means deny.
The result is `AuthorizedAction.self_approved` and `ActionAudit.self_approved` (also persisted in the audit journal). It is set only when the exemption was actually used, never on a deny.

## Trust decision
`ActionContext` is already the enforcer's trusted channel (resolved server-side from the session: memberships, editors, amounts, break-glass state). The new `tenant_role_holders` field is read from there, never from the request payload (a test puts the claim in the payload and it is ignored). No production resolver exists in the repo yet (only tests build `ActionContext`), so whoever writes it (OPR-004 / OPR-007 gateway) must fill this field from the tenant role assignments, including suspended or away members, or the fallback stays off (default `None` = strict deny).

## Files touched
- apps/engine/change_engine/change_engine/guarded_apply/action_policy_enforcer.py: `tenant_role_holders` field, `_SOLE_OWNER_ROWS`, `_sole_owner`, `_approve` returns the flag, `AuthorizedAction.self_approved`, audit flag.
- apps/engine/change_engine/change_engine/guarded_apply/action_policy_store.py: `ActionAudit.self_approved` (default False, old records still load); denial downgrades reset it.
- apps/engine/change_engine/change_engine/tests/test_erp_033_sole_owner_agent.py: new, 29 tests (TC-22 allowed cases, TC-23 denied cases, fail-closed role-holder fact, R4, unchanged behaviour).
- .github/workflows/tests.yml: the new test file added to the existing ERP-023 step.

## Tests run
- New file before the change: 29 failed (the context field did not exist). After: 29 passed.
- ERP-023, ERP-029 and ERP-033 files together: 175 passed. Full `apps/engine/change_engine` suite: 1428 passed, 27 failed, 86 skipped. The failures are in test_cmp_005_calendar, test_cmp_005_hijri_dates, test_erp_007_bilingual_tax_invoice, test_erp_016_branded_templates and test_zatca_phase1_engine (Hijri date errors, template parsing), none of which import the action-policy modules. Not re-run on a clean tree (git state changes are forbidden here), so "pre-existing" is UNVERIFIED; CI is the check.

## Not built
- The periodic review report itself (no hook existed; the audit flag is the input). Needs its own plan row.
- The resolver that fills `tenant_role_holders`.
- docs/PLAN.md row status and the stricter-deny wording were not edited (outside the allowed paths).

## Decisions
- None needing an ADR; the rule is Q-41/Q-563 as resolved. Reviewer: touching auth and compliance needs security review (Tier 3).

## Tokens or cost
Unknown.

## Next step
Human line-by-line review of `_sole_owner` and `_approve`; a plan row for the periodic self-approved review report and one for the resolver that supplies `tenant_role_holders` (OPR-004 / OPR-007); then set ERP-033 done.

## Coordinator check (Claude Opus 5.5)
- Applied onto a fresh branch from main; ERP-023, ERP-029 and ERP-033 files: 175 passed. The 27 Hijri-date failures in the full suite also fail on main locally (library gap), so they are not caused by this change. ERP-033 set `doing` in docs/PLAN.md. The audit flag is persisted: the store writes `asdict(audit)` as JSON.

## Review fixes (#306), 2026-11-24
Implementation sub-agent (Sonnet 5.5) fixing the code-correctness review of PR #306. Each test was written first and seen to fail (finding 1: 6 failed before the fix; finding 2: 12 failed with no method; finding 3 tests passed on current code and were mutation-checked instead).
- Finding 1 (HIGH, `_sole_owner`): the exclusion is now lifted only when the approver is the submitter (Q-41, owner initiated) or the drafter is an agent whose `owner_id` is the approver and, on SOD-DIFF-AUTHOR rows, the approver did not also edit it (Q-563). A staff-initiated draft that the owner authored or edited, another person's agent draft the owner edited, and an own-agent draft the owner edited are denied (`ineligible_approver`). An owner who initiated keeps the fallback whoever drafted or edited. Mutation check: removing the new condition fails the 6 negative tests; removing only the own-agent editor clause fails its test.
- Finding 2 (MEDIUM): `ActionPolicyStore.self_approved_report(tenant_id, since, until)` returns that tenant's persisted `allow` records with `self_approved` true and `since <= timestamp < until`, ordered by time, as the stored `ActionAudit` snapshots (no payload fields; the audit only holds the payload hash). Fail closed: a blank or non-text tenant, a non-aware instant, or `since >= until` raises `ValueError`; an unparsable journal row raises rather than being skipped. It scans the whole append-only journal in Python (no tenant index), which is fine for a periodic report but would need an indexed column before high volume.
- Finding 3: tests that a self-approved allow downgraded by expiry, clock failure (raise, naive instant, clock going back) and replay is stored as deny with `self_approved` false and returns no `AuthorizedAction`. Removing the three resets in `action_policy_store.py` fails 5 tests.
- Finding 4: no change; the holder-id validation in `_sole_owner` stays as defence in depth.
- Not built (follow-up, needs a plan row): scheduling and delivery of the periodic report, who receives it, and the resolver that fills `tenant_role_holders`. This replaces the earlier "Not built" note that no report hook existed: the read side now exists, the periodic run does not.
- Tests: ERP-023, ERP-029 and ERP-033 files together pass: 202 passed (ERP-033 file 56). `check_docs.py` and `check_repo_hygiene.py` clean. Cross-model review of this fix is still required (Tier 3).

## Review fix (2026-11-25, Eldon's Fable 5.2 review at 2aa0a931, Medium)
- `_sole_owner` now also requires `holders["owner"] == {actor.id}`, so an approver whose principal still carries a stale `owner` role is refused when the authoritative map lists no owner, even if that approver is the only other holder of an approving role (`action_policy_enforcer.py`).
- Test-first: new case `approver-not-the-owner-holder` (holders `{"owner": frozenset(), "tenant_admin": {"owner-a"}}`) in `test_untrusted_or_malformed_role_holder_fact_fails_closed`. It failed before the fix and passes after.
- ERP-023, ERP-029 and ERP-033 tests: 203 passed (202 before, plus the new case).
- Still open from the review, as tracking only: plan rows for the `tenant_role_holders` resolver and for the periodic report. The Lows are not changed here.
