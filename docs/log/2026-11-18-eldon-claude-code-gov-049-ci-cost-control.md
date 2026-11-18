# Session log: gov-049-ci-cost-control

Date: 2026-11-18
Author: eldon
Tool and model: claude-code / sonnet-5.5
Plan IDs: GOV-049,GOV-010,LEG-001

## Summary
Prepared for the repo going private on a free GitHub plan (founder's decision): split CI so a PR costs about a quarter of the Actions minutes and stays free of paid features; closed GOV-010 (pre-commit hooks installed and run on Eldon's machine) and LEG-001 (founders' agreement signed, per Eldon in chat).

## Files touched
- .github/workflows/ci.yml, tests.yml, web.yml, audit.yml: four required checks only; one Python job; web and audit on relevant changes; concurrency cancel; push-to-main left to main-guard
- docs/PLAN.md: GOV-049 added and done; GOV-010 and LEG-001 done

## Decisions
- Repo to go private on a free plan: no branch protection (hooks, CODEOWNERS review and discipline replace it) and a limited Actions allowance. Cross-lane: n/a. LEG-001 closed on Eldon's statement that the agreement is signed; prototype IP assignment should be covered by it.

## Tokens or cost
Unknown or approximate, if known.

## Next step
Partner installs the hooks (pip install pre-commit; pre-commit install). Watch Actions usage after the switch. Then G0 exit: GOV-002 is no longer wanted by Eldon (organisation dropped).
