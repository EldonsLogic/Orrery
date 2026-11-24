# Staging environment and deployment prerequisites

Status: draft
Owner: partner

Purpose: defines the staging deployment prerequisites, GitHub Environment configuration, secret categories (pending `INF-001`), and deployment approval controls for `INF-003` and `INF-004`.

## Context and references

Per [ADR-0018](../docs/decisions/ADR-0018-development-environments-and-progress-viewing.md), [ADR-0006](../docs/decisions/ADR-0006-tenancy-site-per-tenant.md), and [ADR-0016](../docs/decisions/ADR-0016-engine-invisibility.md):
- Progress must always be viewable.
- The web app runs on Vercel with preview links per pull request.
- The ERP engine and AI / gateway platform services require a dedicated non-production runtime environment (`infra/dev/docker` or an equivalent staging deployment topology decided under `INF-001`).
- Synthetic data only on non-production hosts: customer or pilot data is strictly forbidden.
- The engine must remain invisible (ADR-0016): customer-facing requests route strictly through the web app and gateway.
- No secrets or credentials are ever committed to the repository.

As of gate G1, no staging environment, hosting provider, or cloud accounts exist yet (`INF-001` has not selected a provider). Plan row `INF-003` delivers CI/CD for services (build, test, and a disabled staging deploy skeleton). Nothing about the runtime host, deployment mechanism, or secret schema is pre-committed here; the prerequisites below must be finalized after `INF-001`.

## Founder setup prerequisites

Before enabling automated staging deployments in `.github/workflows/tests.yml`:

### 1. Hosting provider and runtime model decision (INF-001)

The founders must decide the hosting provider and deployment model via an ADR under `INF-001`:
- **Provider and residency**: Select the hosting provider and region satisfying data residency rules (ADR-0006). No cloud vendor, VM host, or PaaS is pre-selected by this document.
- **Runtime prerequisites**: Provision compute capable of running the engine, MariaDB, Redis, background workers, and platform service containers.
- **Ingress and TLS**: Configure TLS termination, DNS routing, and reverse proxying through the gateway routes.
- **Access control**: Protect staging ingress behind authentication, VPN, or platform access controls so synthetic staging environments are not publicly indexable.

### 2. GitHub Environment configuration

The founders must create the `staging` environment in GitHub:
1. Navigate to repository **Settings** -> **Environments**.
2. Click **New environment** and enter name: `staging`.
3. Configure **Deployment protection rules**:
   - Enable **Required reviewers**: select founders `EldonsLogic` and `sayegh9` (at least 1 required approval before a deployment job runs).
   - Enable **Deployment branches**: restrict deployments to the `main` branch.
   - Set **Wait timer** (optional, e.g. 0 minutes).

### 3. Deployment secret and variable categories (TBD pending INF-001)

Exact secret and variable names depend on the deployment mechanism chosen in `INF-001` (for example, OIDC/workload identity, provider CLI token, or SSH deploy key) and must NOT be committed to git. Populate the final provider-specific names in the `staging` GitHub Environment covering:
- **Deployment / target authentication**: provider OIDC role or deploy credentials scoped to staging only.
- **Container registry credentials** (if images are pushed to a private registry).
- **Runtime service secrets**: inter-service gateway signing secret, AI provider API key, and staging database password.
- **Non-secret environment variables**: target environment identifier (`staging`) and the provisioned staging base URL once allocated.

## Deployment skeleton in CI

In `.github/workflows/tests.yml`, the workflow triggers on `pull_request`, `push` to `main`, and `workflow_dispatch`, and the `deploy-staging` job is present as a disabled skeleton:
```yaml
deploy-staging:
  name: Deploy to staging (disabled)
  needs: [python-tests]
  runs-on: ubuntu-latest
  # When enabled after INF-001/INF-004, restrict to main pushes:
  # if: github.event_name == 'push' && github.ref == 'refs/heads/main'
  if: false
  environment: staging
```
Once the founders complete `INF-001` (hosting ADR) and provision the `staging` GitHub Environment and secrets under `INF-004`, replace `if: false` with `if: github.event_name == 'push' && github.ref == 'refs/heads/main'` so deployments run only on `main` pushes with founder approval enforced by the GitHub Environment rules.
