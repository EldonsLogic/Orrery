# Session log: gov-055-reviewer-ci-check

Date: 2026-11-21
Author: partner
Tool and model: claude-code (Sonnet 5.5)
Plan IDs: GOV-055

## Summary
Shipped the CI half of GOV-055 (ADR-0034 enforcement): `scripts/check_component_reviewers.py` fails any component manifest at `reviewed`, `certified` or `regulated` whose `certification.reviewedBy` has no login, or lists `owner.github` (case-insensitive, `@` and whitespace normalised). Unreadable, non-object or invalid-level manifests fail closed. Wired as one step in the `repo-hygiene` job of `ci.yml`. The four real manifests under `components/` are all at `tested` and pass.

Not done, by founder decision: the engine/apply eligibility check or compiled-artifact certification binding. It waits on Q-297, so GOV-055 stays open for that part. `docs/PLAN.md` is untouched (the row is claimed in PR #251).

## Files touched
- scripts/check_component_reviewers.py: new check, standard library only
- scripts/tests/test_check_component_reviewers.py: new tests (clean, owner as reviewer with case and `@` variants, empty list, unreviewed level, malformed, run output and exit code, real repo)
- .github/workflows/ci.yml: one step in `repo-hygiene`
- docs/log/: this log

## Decisions
- None new; implements ADR-0034 follow-up "author-not-reviewer check". The login comparison cannot tell a different person using a second account; that stays a human review matter.

## Tokens or cost
Unknown.

## Next step
Q-297 answer, then the engine/apply eligibility part of GOV-055.
