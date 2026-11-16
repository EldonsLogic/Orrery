# Session log: gov-014-cross-model-review-trial

Date: 2026-11-16
Author: eldon
Tool and model: claude
Plan IDs: GOV-014

## Summary
Closed the trial of the cross-model review routine using the real PRs from this period: code written with Claude and reviewed by the partner's GPT-based agent (#40, #56, #57, #58, #59).

Result:
- It works as designed: a different model reviewed each change at a pinned commit and returned findings with file and line.
- Real catches: the production-eligibility boundary for ledger/tax components (#57, fixed with `Registry.eligible`), the adapter contract ambiguities (#40, resolved as Q-45 to Q-49), the small-tenant approver gap in the action-policy table (#58, interim fail-closed rule, Q-41 still open).
- Cost: too many rounds and comments per PR, including on docs-only changes. Answered by ADR-0035 (risk tiers, block only on defects, at most two rounds).
- A change-request review still blocks merging in GitHub until dismissed or re-approved; with the tiers, an addressed finding is replied to once and the stale review is dismissed.

## Files touched
- docs/PLAN.md: GOV-014 done

## Decisions
- [ADR-0035](../decisions/ADR-0035-risk-tiered-review.md) is the outcome of this trial.

## Tokens or cost
Unknown or approximate, if known.

## Next step
Open G0 rows left in this lane are founder tasks (LEG-001, LEG-003, LEG-005, GOV-010, INF-013, GOV-002).
