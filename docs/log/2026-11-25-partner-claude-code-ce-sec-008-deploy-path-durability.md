# Session log: ce-sec-008-deploy-path-durability

Date: 2026-11-25
Author: partner
Tool and model: claude-code / claude-opus-5-5 (coordinator); implementation by a Claude Sonnet 5.5 child, test-first
Plan IDs: CE-SEC-008

## Summary
CE-SEC-008 part 1 fixes four durability defects in today's guarded deploy path, found in the #309 reviews.
- Durable baseline and statement evidence is written before any effect.
- Idempotency and recovery lookups fail closed on database errors.
- The lock-wait timeout is checked by reading it back.
- The Stage 3 intent is inserted strictly.

Part 2 is the per-process deployment-id counter in the adapter; it is adapter-lane work and comes later. Coordination is in 2026-11-25-partner-claude-code-partner-sprint.md (PR #316).

## Files touched
All under `apps/engine/change_engine/change_engine/`:
- `api/endpoints.py`:
  - The baseline is committed with the intent in one transaction, before any DDL. It reuses the existing audit table as append-only `<dep>#evidence` rows, so there is no schema change.
  - `load_durable_evidence()` rebuilds the evidence after a restart.
  - A dispatch-intent row is written before each statement and a completed row after it, so a statement is never recorded as executed before it takes effect. Completion truth is the main row's Stage 6 status.
  - Lookups raise on database errors and on unparseable stored outcomes.
  - The lock-timeout setter validates its value, raises on failure and checks the read-back.
  - The Stage 3 intent is a plain INSERT. A duplicate raises `DeploymentIntentConflictError` (`binding_mismatch` or `already_recorded`) and leaves the older row untouched.
- `guarded_apply/schema_reconciler.py`:
  - A lookup failure gives `REJECTED` with `engine_unavailable`, and no intent is written.
  - The lock timeout is set and verified before the intent (`lock_timeout_not_effective`).
  - An intent conflict gives `REJECTED` with `intent_<reason>`.
- `adapter/simulated_frappe.py`, `tests/test_api_deployment.py`: the test doubles answer `SELECT @@SESSION.lock_wait_timeout` (3 lines and 2 lines). The coordinator applied these.
- `tests/test_ce_sec_008_deploy_path_durability.py`: new, 41 tests with 16 subtests. They cover:
  - crash boundaries
  - repeated identical requests
  - conflicting bindings
  - database outages
  - timeout read-back mismatch
  - restart from durable evidence
- `.github/workflows/tests.yml`: a new CI step for the new test file.

## Evidence
- Red before: the new file had 45 failing tests and 12 passing. The 12 cover behaviour that was already correct.
- Green after: the new file passes 41 tests.
- Full change-engine suite (`PYTHONPATH=apps/engine/change_engine uvx --with pyyaml --with jsonschema --with pydantic --with pymysql --with werkzeug --with hijridate pytest -q apps/engine/change_engine/change_engine/tests`):
  - before the change: 1514 passed, 86 skipped
  - after it, with the test-double patch: 1555 passed, 86 skipped, 0 failed
- Without the test-double patch, 108 tests in 8 files failed closed on the new read-back. That failure is expected.

## Decisions
- No new ADR: this implements ADR-0068 items 13, 15 and 18 (Proposed, PR #309) for today's path.
- Design call for review: a dispatched statement that left the live schema equal to the baseline counts as "nothing executed" (ADR-0068 item 16), so `FAILED_CLEAN` stays for failed ALTERs.

## Open follow-ups
- `frappe_backend._execute_six_stage_field` still sets the timeout after the intent, and its lookups now raise raw exceptions. Both are adapter lane (part 2), blocked by the open PRs #310 and #312.
- `get_deployment_record` and `mark_recovery_required` still swallow database errors.
- The workflow, report and property-setter engines call the same lookups, so they now raise on a database outage. That is fail closed, but they have no clean refusal yet.
- The new test file has 734 lines, above the ~500-line guideline.

## Review round 1 (GPT-6.2 Sol at 56b00a23: changes required; 4 High, 4 Medium, 1 Low)
- Fixed:
  - non-DDL deployments (workflow, report, property setter) no longer need a DDL baseline;
  - caller ids that could collide with evidence keys are rejected, and rollback, lookups and finalizers act on main rows only;
  - a fresh read view is taken after the locks;
  - provenance is computed, and a restarted deployment always ends in RECOVERY_REQUIRED;
  - lookup row shapes are strict and read failures are typed;
  - a site-scoped idempotency lock, with `already_recorded` replaying the stored outcome;
  - stable reason codes, with exception text in internal logs only;
  - timeout validation at the RPC boundary, with a re-read on the dispatching session;
  - a stateful live mock.
- Red then green: the new `test_ce_sec_008_review_fixes.py` went from 69 failed and 16 passed to all passing. The two CE-SEC-008 files now give 77 passed with 76 subtests.
- Full suite: 1591 passed, 86 skipped, 0 failed.
- Follow-ups added to PLAN:
  - CE-SEC-009: a locked recovery entry point (needs an ADR).
  - CE-SEC-010: a dedicated journal table with a unique idempotency index (needs an ADR).
- Other follow-ups:
  - Adapter lane, part 2: in `frappe_backend.py`, the decimal backend must set the timeout before the intent. The workflow, report and property-setter engines need the idempotency lock and a fresh read view.
  - A bench proof with two MariaDB sessions.

## Review round 2 (GPT-6.2 Sol at ea12c1f1: changes required; 2 High, 3 Medium, 6 partly resolved)
- Fixed:
  - N1: the fresh read view no longer commits; it refuses over pending caller writes and otherwise rolls back a read-only transaction.
  - N2: locks fold site, doctype and key by case and trailing spaces, matching the column collation; new ids and keys must be canonical ASCII.
  - N3: both locks are acquired in one try/finally; release is verified, and a failed release discards the session.
  - N4: new ids are limited to 100 characters so derived keys fit; existing longer ids still look up and revert.
  - N5: the timeout is rechecked before the Custom Field insert, and pending writes are rolled back when no DDL was sent.
  - Round 1 remainders: the main-row filter on the internal lookup; an ordinary revert refused while a deployment is on hold (DEPLOYMENT_ON_HOLD); strict outcome objects; `revision_unavailable`.
- Red to green: the two CE-SEC-008 files went from 37 failed and 86 passed to 99 passed with 103 subtests.
- Full suite: 1613 passed, 86 skipped, 0 failed.
- UNVERIFIED: the Frappe 15 attribute name `transaction_writes`.
- Follow-up added to PLAN: CE-SEC-011, the adapter lane, bringing the non-DDL engines and the decimal backend onto the same lock discipline.

## Review round 3 (GPT-6.2 Sol at 510fcfb9: changes required; 1 High, 3 Medium; N3 and N4 fixed)
- Fixed:
  - The fresh read view refuses a write counter that is missing, invalid or non-zero, with no commit fallback. A dedicated connection is follow-up work in CE-SEC-011.
  - The site identity comes from the resolved site, never from caller input. Anything else is refused as `SITE_MISMATCH` or `INVALID_SITE_ID`.
  - A failed rollback discards the session and returns RECOVERY_REQUIRED (`session_discarded`), so the PREPARED hold stays.
  - The revert hold check runs only after authorisation. Moving it under the target lock is follow-up work in CE-SEC-011.
- Red then green: the two CE-SEC-008 files went from 21 failed and 103 passed to 124 passed, with 118 subtests.
- Full suite: 1624 passed, 86 skipped, 0 failed.
- The CE-SEC-011 row text now includes the dedicated connection and the locked hold check.

## Review round 4 (GPT-6.2 Sol at 716eb136: changes required, 3 regressions from round 3)
- Fixed:
  - The site identity is now the tenant id the backend binds (`site_id=tenant_id`). It is accepted only if it is canonical and belongs to the resolved site. A hold and a replay record written by the backend are found through the RPC path.
  - A typed `SessionDiscardedError` refuses every commit, finalize and prepare once the session is unusable. All 12 raw commits now go through `_commit_durable`.
  - Native apply re-checks the session and lock ownership (`IS_USED_LOCK`) before it commits. The decimal path finalizes through the guarded adapter.
  - A failed close never reports a successful release. The close is retried once per release call.
- Red then green: 8 failed, then 128 passed in the two CE-SEC-008 files.
- Full suite: 1633 passed, 86 skipped, 0 failed.
- The CE-SEC-011 text now includes mapping `SessionDiscardedError` in the decimal path, and resolving a custom `site_map` through the backend's resolver.

## Review round 5 (GPT-6.2 Sol at 54aab24b: 1 new High; discarded-session commits and failed close resolved)
- High: `t_alpha`, `t-alpha` and `t-alpha.localhost` were all accepted for one site, but gave separate lock and audit scopes. The coordinator fixed it directly (a small fix): `_resolve_site_id` now derives ONE identity per site. A tenant site (`t-alpha.<domain>`) maps to exactly the tenant id the backend binds (`t_alpha`), using the backend's injective grammar. Any other spelling is refused as `SITE_MISMATCH`. With no caller identity the derived tenant id is used, so holds and replays apply. A non-tenant site keeps its own name as its only identity. Custom `site_map` sites stay with CE-SEC-011.
- Tests first: `TestR5OneAuthoritativeSiteIdentity` (aliases refused, a missing identity still hits the hold, a non-tenant site). 6 failed before the fix, then passed.
- Full suite: 1636 passed, 86 skipped, 0 failed.

## Review round 6 (GPT-6.2 Sol at be4a11a4: 1 High; all 966 generated site cases matched the backend's identity)
- High: holds and replay records written before the single-identity rule, under the host name, became invisible. The coordinator fixed it directly: `_read_site_ids` adds the host name as a read-only alias in the hold and idempotency lookups, and only when the current site maps back to exactly this tenant identity. Writes, locks and journal entries still use the single identity.
- Result: a legacy hold still blocks, whether or not the caller passes an identity. A legacy idempotency key still holds its key, but is refused as `IDEMPOTENCY_CONFLICT` rather than replayed, because its payload hash was taken with the host name. That fails closed and sends no second statement. Another site's hold never matches.
- Tests first: 3 new tests in `TestR5OneAuthoritativeSiteIdentity`. The fake database models `site_id IN (...)`.
- Full suite: 1639 passed, 86 skipped, 0 failed.

## Review round 7 (GPT-6.2 Sol at 78338507) and the coordinator's close-out of the review loop
- Fixed:
  - The legacy alias now takes the site from the adapter's own runtime when it is injected, and from the global Frappe runtime otherwise.
  - The offline simulator answers the three-parameter `IN` lookup. Its test fails without the simulator fix and passes with it.
- Full suite: 1641 passed, 86 skipped, 0 failed.
- Not fixed here, recorded as residuals:
  - Rows under a bare site slug or under arbitrary caller-chosen site ids are not read as aliases. The bare slug was accepted only by the round 4 resolver on this unmerged branch. Before this PR, any caller string was accepted, so no complete alias set exists. CE-SEC-010's journal migration rekeys such rows.
  - The decimal backend skips the deployment idempotency lookup (`frappe_backend.py`, CE-SEC-011).
  - Revert and recovery reads use deployment ids, and the policy store uses its own host-scoped tables. The reviewer noted both and did not raise them as defects of this PR.
- Review loop stopped after round 7 (the coordinator's call, reported to the partner): each round since round 3 has found one narrower edge case, and the remaining items belong to CE-SEC-009, CE-SEC-010 and CE-SEC-011, which need an ADR or adapter-lane files.

## Review round 8: Eldon's security review (Fable 5.2 at 56b00a23)
- F1 (non-DDL engines) and F5 (`#` in keys) were already fixed, and re-checked.
- Fixed in this round:
  - F2: deployment ids are `prefix_<uuid4 hex>`, unique across restarts.
  - F3: an evidence digest over baseline, plan, id, site, doctype, field and payload hash, stored in the existing plan column. Each journal row is chained to it, and all of it is verified on load. Limit: the digest is unkeyed and journal-tail truncation is not detected; a keyed MAC is in CE-SEC-010 and CE-SEC-011.
  - F4: evidence must match the request's doctype, field and bound site.
  - F6: the decimal path now runs through `execute_single_field_deployment` (`approved_plan`). It inherits both locks, the fresh view, the idempotency and recovery lookups and the timeout before the intent. Failures map to `engine_unavailable` or `recovery_required`.
  - F7: the three surviving mutants are now killed, with meta-tests.
  - F8: `_commit_durable` raises when there is no `commit`.
  - F9: distinct `evidence_unavailable` and `snapshot_unavailable` codes.
  - F10: the timeout ceiling is now 60 s, and the previous session value is restored and verified on every exit path.
- `frappe_backend.py` was edited in this PR, because #310 and #312 had merged.
- Red then green: 38 failed and 128 passed before, 150 passed after (two CE-SEC-008 files).
- Full suite: 1721 passed, 86 skipped, 0 failed.
- CE-SEC-011 text trimmed to what remains.

## Tokens or cost
Unknown.

## Next step
Cross-model review of this PR (Tier 3). Then CE-SEC-008 part 2 (the adapter deployment-id counter), after #310 and #312 merge.
