# Session log: gov-027-private-repo-decision

Date: 2026-11-18
Author: eldon
Tool and model: claude-code / sonnet-5.5
Plan IDs: GOV-027

## Summary
Closed GOV-027: the repo was switched back to private on 2026-11-18 on the free GitHub plan, a deliberate choice by Eldon.

## Files touched
- docs/PLAN.md: GOV-027 done

## Decisions
- Decision (Eldon, chat 2026-11-18): private repo on the free plan, no paid plan. Consequences accepted: no GitHub branch protection (no enforced required checks, review or no-push-to-main), so the local pre-commit and pre-push hooks, the main-guard audit and discipline replace it; Actions minutes are limited, so CI was split (GOV-049). Anything published while public may still exist in forks, caches and clones; secrets must be rotated if any ever appeared. Partner keeps push access as a collaborator.

## Tokens or cost
Unknown or approximate, if known.

## Next step
Partner installs the hooks (pip install pre-commit; pre-commit install). Watch the Actions usage page. If protection is needed later, upgrade the plan.
