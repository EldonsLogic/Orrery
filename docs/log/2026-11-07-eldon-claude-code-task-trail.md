# Session log: task-trail

Date: 2026-11-07
Author: eldon
Tool and model: claude-code
Plan IDs: GOV-023

## Summary
Made the task trail checkable: a CI gate now fails a PR whose new log has no valid plan IDs, or whose product-code changes are logged against plan rows that are still todo. STATUS now shows a queue for each founder (doing, ready next, waiting), so each person's flow is visible from the start.

## Files touched
- scripts/check_pr_trail.py (new): the gate; run by CI on pull requests.
- .github/workflows/ci.yml: new "Trail check" step in the pr-log-gate job.
- scripts/build_status.py: per-founder queues and an unassigned-rows count; docs/STATUS.md regenerated.
- docs/PLAN.md: GOV-023 done.

## Decisions
- The gate cannot prove a log is accurate or complete; it checks that a log exists, names real plan rows, and that code work shows as doing, done or blocked. Review by the other founder remains the check on quality. Branch protection (GOV-008) would make the gates blocking; it needs a paid GitHub plan.

## Tokens or cost
Unknown.

## Next step
Both founders: claim a row from your queue in docs/STATUS.md. GOV-008 when the GitHub plan is decided.
