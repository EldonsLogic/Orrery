# ADR-0020: Lane guard

Status: Accepted
Owner: eldon
Approved by: Eldon and partner

## Context
Two founders and several agents work in parallel. Lanes were described in the onboarding guide but nothing stopped someone editing the other's files.

## Decision
`scripts/lanes.json` maps path prefixes to each founder and maps GitHub logins to founders. `scripts/check_lanes.py` fails a change that edits the other founder's lane, in CI (using the PR author), in the pre-push hook and in `finish_session.py` (using `gh api user`). The only way through is an agreed waiver: a line `Cross-lane: approved by <eldon|partner> (where and when)` in the session log added by the same change; reviewers confirm the agreement is real. Shared paths are open to both with the other's review. Bots and unmapped logins are skipped. Lanes are re-assigned by editing `scripts/lanes.json` and plan owners in a PR with both founders' approval.

## Alternatives rejected
- Convention only: not enforced.
- CODEOWNERS: needs branch protection (a paid plan) to block.

## Consequences
- A founder's agent that needs a change in the other lane stops and asks instead of editing.
- The waiver line can be typed falsely; review is the check. Without branch protection the CI result is advisory on merge.

## Supersedes
Extends ADR-0017 and ADR-0019.
