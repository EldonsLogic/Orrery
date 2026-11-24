# Staging environment and deployment prerequisites

Status: draft
Owner: partner

Purpose: defines the staging environment architecture, founder setup prerequisites, GitHub Environment configuration, secrets specification, and deployment approval controls for INF-003 and INF-004.

## Context and references

Per [ADR-0018](../docs/decisions/ADR-0018-development-environments-and-progress-viewing.md), [ADR-0006](../docs/decisions/ADR-0006-tenancy-site-per-tenant.md), and [ADR-0016](../docs/decisions/ADR-0016-engine-invisibility.md):
- Progress must always be viewable.
- The web app runs on Vercel with preview links per pull request.
- The ERP engine and AI / gateway platform services require a dedicated compute environment running Docker (`infra/dev/docker` or staging compose).
- Synthetic data only on non-production hosts: customer or pilot data is strictly forbidden.
- The engine must remain invisible (ADR-0016): customer-facing requests route strictly through the web app and gateway.
- No secrets or credentials are ever committed to the repository.

As of gate G1, no staging environment or cloud accounts exist yet. Plan row INF-003 delivers CI/CD for services (build, test, and a disabled staging deploy skeleton). The founders must perform the setup steps below before automated staging deploys can be enabled.

## Founder setup prerequisites

Before enabling automated staging deployments in `.github/workflows/tests.yml`:

### 1. Hosting provider and compute platform decision (INF-001)

The founders must choose and provision the staging host/provider:
- **Compute selection**: Small shared cloud host (cloud VM or container platform such as Fly, Railway, Render, or DigitalOcean; or regional in-country cloud provider per data residency rules).
- **Runtime prerequisites**: Docker and Docker Compose capability to run `infra/dev/docker` (engine, MariaDB, Redis, background workers) alongside platform service containers.
- **Networking**: Secure ingress with TLS, DNS routing, and reverse proxying (Traefik / Caddy / Nginx) terminating SSL and mapping gateway routes.
- **Access control**: Staging ingress must be protected behind basic authentication, corporate VPN, or platform sign-in so unreleased features and synthetic environments are not publicly indexable.

### 2. GitHub Environment configuration

The founders must create the `staging` environment in GitHub:
1. Navigate to repository **Settings** -> **Environments**.
2. Click **New environment** and enter name: `staging`.
3. Configure **Deployment protection rules**:
   - Enable **Required reviewers**: select founders `EldonsLogic` and `sayegh9` (at least 1 required approval before a deployment job runs).
   - Enable **Deployment branches**: restrict deployments to the `main` branch.
   - Set **Wait timer** (optional, e.g. 0 minutes).

### 3. Required GitHub Environment secrets (names only)

The following secret names must be populated in the `staging` GitHub Environment. Do NOT commit values to git:

| Secret Name | Purpose | Example / Description |
|---|---|---|
| `STAGING_HOST` | Hostname or IP address of the staging server | FQDN or IP of the staging server |
| `STAGING_SSH_USER` | Deploy user account on the staging server | e.g. `deploy` or `orchestrator` |
| `STAGING_SSH_KEY` | Private SSH key for automated deployment authentication | OpenSSH private key (ed25519) |
| `STAGING_CONTAINER_REGISTRY` | Container image registry URL | e.g. `ghcr.io` or provider registry |
| `STAGING_REGISTRY_USER` | Registry authentication username | GitHub actor or robot account |
| `STAGING_REGISTRY_TOKEN` | Registry authentication token or PAT | Token with package read/write scope |
| `STAGING_GATEWAY_SECRET` | Secret token for gateway inter-service authentication | High-entropy random token |
| `STAGING_AI_GATEWAY_KEY` | Provider API key for model calls through gateway | AI provider API key |
| `STAGING_DB_PASSWORD` | MariaDB / database root password for staging bench | Generated strong password |

### 4. Required GitHub Environment variables (names only)

| Variable Name | Purpose |
|---|---|
| `STAGING_BASE_URL` | Public base URL of the staging deployment (e.g. `https://staging.internal.domain`) |
| `ENVIRONMENT` | Target environment identifier (set to `staging`) |

## Deployment skeleton in CI

In `.github/workflows/tests.yml`, the `deploy-staging` job is present as a skeleton but disabled:
```yaml
deploy-staging:
  name: Deploy to staging (disabled)
  needs: [python-tests]
  runs-on: ubuntu-latest
  if: false  # DISABLED: No staging environment exists yet (ADR-0018)
  environment: staging
```
Once the founders complete the infrastructure provisioning and secret configuration above, the job guard can be changed to trigger on pushes to `main` (with founder approval enforced by the GitHub Environment protection rules).
