# Session log: inf-003-services-ci

Date: 2026-11-18
Author: partner
Tool and model: antigravity / gemini-3.8-flash
Plan IDs: INF-003

## Summary
Delivered the build and test CI pipeline for platform services under `services/*` and `apps/engine` with per-service path filtering, dependencies, linting, and pinned action commit SHAs in `.github/workflows/tests.yml`; added a disabled `deploy-staging` skeleton job, documented staging deployment prerequisites and GitHub Environment secret specifications in `infra/staging.md` (and `infra/README.md`), and recorded open question Q-174.

## Files touched
- `.github/workflows/tests.yml`: extended `python-tests` job to pin action versions by commit SHA (`actions/checkout` and `actions/setup-python`), detect changed service paths, install dependencies per service, run lint (`compileall`) and test suites for changed services and engine, and added a disabled `deploy-staging` job skeleton with `if: false`.
- `infra/staging.md`: new specification of founder prerequisites for staging deploys (hosting provider/compute selection, GitHub Environment creation with required founder approvals, list of secret names only, and security/invisibility guardrails).
- `infra/README.md`: updated owner to partner and linked to `staging.md`.
- `docs/open-questions.md`: added Q-174 tracking founder staging prerequisites.
- `docs/PLAN.md`: set INF-003 row to `doing` (owner partner).

## Decisions
- Staging deployment is NOT done because no staging environment, hosting provider, or cloud account exists yet (ADR-0018). Per repo rules, agents do not invent hosts, credentials, or accounts. Documented exactly what founders must create in `infra/staging.md` and added Q-174.
- Extended `.github/workflows/tests.yml` to maintain the existing required check name (`Tests / python-tests`), avoid duplicate runner execution across pull requests, and keep Actions minutes minimal on a private repo (GOV-049).

## Tokens or cost
Approximate session cost.

## Next step
Founders decide on hosting provider (INF-001), create the `staging` GitHub Environment with required approvals, and populate deployment secret names so staging deploys (INF-004) can be enabled.
