# ADR-0023: One personal GitHub account per founder

Status: Accepted
Owner: eldon
Approved by: Eldon (founder decision, 2026-11-07)
Supersedes: the two-account line in ADR-0021 (the rest of ADR-0021 stands)

## Context
ADR-0021 recorded that Eldon works from two GitHub accounts. GitHub's terms, as we understand them, allow one free personal account per person; the second account was suspended. Continuing would put the main account at risk.

## Decision
- Each founder uses exactly one personal GitHub account: `EldonsLogic` (Eldon) and `sayegh9` (partner).
- Several Claude subscriptions or tools may connect to the same GitHub account, one session at a time (ONBOARDING.md).
- The second account is removed from the lane map, code owners and docs. Work it left was re-committed under the main account.

## Alternatives rejected
- Appeal and keep both accounts: still breaks the one-account rule if reinstated.
- A separate machine account for automation: not needed now; revisit with counsel if wanted.

## Consequences
Old logs and ADR-0021 keep their wording as history; they are append-only.
