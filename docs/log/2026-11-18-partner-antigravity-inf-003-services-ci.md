# Session log: inf-003-services-ci

Date: 2026-11-18
Author: partner
Tool and model: antigravity / gemini-3.8-flash
Plan IDs: INF-003

## Summary
Delivered the build and test CI pipeline for platform services under `services/*`, `apps/engine`, `components/*`, `evals/*`, `scripts/*`, and `infra/*` with fail-closed PR path filtering, cross-service dependency triggers, `push` to `main` execution, per-service dependency installs, linting, and pinned action commit SHAs in `.github/workflows/tests.yml`; added a disabled `deploy-staging` skeleton job, documented staging deployment prerequisites (without pre-selecting hosts or secret schemas ahead of `INF-001`) in `infra/staging.md` (and `infra/README.md`), and recorded open question Q-291.

## Files touched
- `.github/workflows/tests.yml`: extended `python-tests` job to pin action versions by commit SHA (`actions/checkout` and `actions/setup-python`), run on `pull_request`, `push` to `main`, and `workflow_dispatch`, detect changed service paths fail-closed (running all suites on `merge-base`/`diff`/empty failures, shared `contracts/`/`.github/` edits, or unmapped paths), include cross-service dependency triggers and verified dependencies (`jsonschema` via `services/blueprint/requirements.txt` for `gateway`, `discovery`, `operate`, `studio`, `engine`, `components`), run `services/control-plane/tests`, `infra/invisibility/tests`, `country_pack/tests`, and `test_erp_009_*`, and keep a disabled `deploy-staging` skeleton job with `if: false`.
- `infra/staging.md`: specification of founder prerequisites for staging deploys (hosting provider/compute decision deferred to `INF-001`, GitHub Environment creation with required founder approvals, secret categories rather than pre-selected host/SSH schemas, and security/invisibility guardrails).
- `infra/README.md`: updated owner to partner and linked to `staging.md`.
- `docs/open-questions.md`: added Q-291 (renumbered after merging `origin/main` through Q-209) tracking founder staging prerequisites.
- `docs/PLAN.md`: set INF-003 row to `doing` (owner partner).

## Decisions
- Staging deployment is NOT done because no staging environment, hosting provider, or cloud account exists yet (ADR-0018). Per repo rules, agents do not invent hosts, credentials, or accounts. Documented exactly what founders must decide/create in `infra/staging.md` and added Q-291.
- Extended `.github/workflows/tests.yml` to maintain the existing required check name (`Tests / python-tests`), avoid duplicate runner execution across pull requests, and keep Actions minutes minimal on a private repo (GOV-049).

## Tokens or cost
Approximate session cost.

## Next step
Founders decide on hosting provider (INF-001), create the `staging` GitHub Environment with required approvals, and finalize/populate deployment secrets so staging deploys (INF-004) can be enabled.
