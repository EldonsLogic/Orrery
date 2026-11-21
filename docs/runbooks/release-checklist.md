# Release checklist (tenant environment)

Status: draft
Owner: unassigned
Gate: G1 (deploy and rollback process; see [../GATES.md](../GATES.md))

## Purpose
Ship a release of the platform to a tenant environment (staging first, then production) with every automated check, review and recovery step recorded. Use it for each release; tick each box or write why it does not apply.

## Preconditions
- The release is a merged PR on `main`, built from a commit that CI has tested.
- The release owner is named in the release log entry.
- Rules: [../../AGENTS.md](../../AGENTS.md) (review tiers, lanes, no direct pushes to `main`), [../security/hosting-rules.md](../security/hosting-rules.md) (PR, CI, staging, approval, prod).

## Pre-release

### Checks and gates
- [ ] CI is green on the release commit: `ci.yml` (docs, secret scan, repo hygiene, lanes, trail), `tests.yml` (service tests, contract checks, `web` tests), `web.yml` (lint, `check:tokens`, typecheck, tests, build), `audit.yml` (pip-audit and SBOM).
- [ ] Eval gate passed: `python3 -m evals.gate` (the `Eval harness` job in `tests.yml`). Thresholds and baseline are in `evals/gate/`; see [../../evals/README.md](../../evals/README.md). A drop in any `agent_behaviour` category blocks the release.
- [ ] Repo checks pass locally: `python3 scripts/check_docs.py`, `python3 scripts/check_repo_hygiene.py`, `python3 scripts/scan_secrets.py`.
- [ ] Phase or gate exit run recorded if this release closes one: `python3 scripts/phase_exit_check.py --phase <name>` and the session log with its `Phase exit:` header (see [../GATES.md](../GATES.md)).

### Review
- [ ] Review tier recorded for the PR per [ADR-0035](../decisions/ADR-0035-risk-tiered-review.md). Tier 2 has one review by the other founder or a different model. Tier 3 has human line-by-line review.
- [ ] Security review done for every Tier 3 change and for any change touching auth, tenancy, contracts or compliance (RULES 42, [../../SECURITY.md](../../SECURITY.md)). Rigid-zone code follows [ADR-0031](../decisions/ADR-0031-rigid-zone-code-authorship.md).
- [ ] Ledger, tax, e-invoice and payroll logic is deterministic code, not AI-written, and was reviewed by a human (AGENTS.md principle 3).

### Data and schema
- [ ] Migrations and DDL plan reviewed: run the adapter `plan()` dry run ([../architecture/engine-adapter.md](../architecture/engine-adapter.md)) on a copy of the tenant and attach the list of DDL, schema and data changes and risk flags to the release log.
- [ ] Destructive operations in the plan are listed, justified and have a restore point (see the backup step below).
- [ ] Apply is journaled and recoverable (ADR-0028). Any `recovery_required` path is covered by [adapter-recovery-required.md](adapter-recovery-required.md).

### Licences, language and brand
- [ ] Licence register updated for every new or upgraded open-source component (LEG-004, row in [../PLAN.md](../PLAN.md)).
- [ ] Arabic and English strings complete: no hard-coded user-facing strings, every string through i18n (principle 4).
- [ ] RTL check passes: `pnpm check:rtl` in `web/` (also run by `pnpm lint`). Layout checked in RTL at phone width.
- [ ] Tokens only: `pnpm check:tokens` passes; no new hard-coded colours or fonts ([ADR-0014](../decisions/ADR-0014-theming-and-tenant-branding.md)).

### Engine invisibility (ADR-0016)
- [ ] Engine invisibility crawl run against the staging build: `python3 infra/invisibility/crawler.py --base-url <staging-url>` exits 0. Markers are in `infra/invisibility/markers.json`.
- [ ] Manual check of new text, PDFs, emails, error messages, API paths, headers and cookies for "Frappe", "ERPNext" or engine paths ([ADR-0016](../decisions/ADR-0016-engine-invisibility.md), [ADR-0029](../decisions/ADR-0029-engine-disclosure-wording-and-saas-only.md)).

### Compliance fields
- [ ] ZATCA (Saudi Arabia) and UAE e-invoicing fields are unchanged, or any change was reviewed against [../compliance/e-invoicing.md](../compliance/e-invoicing.md) and [../compliance/country-matrix.md](../compliance/country-matrix.md) and signed off by the compliance owner.
- [ ] VAT, WPS and PDPL-related fields are unchanged, or reviewed as above ([../compliance/regulation-watch.md](../compliance/regulation-watch.md)).

## Release

### Staging first
- [ ] Deploy to staging only, from the tested commit. Staging holds synthetic or anonymised data only ([../security/hosting-rules.md](../security/hosting-rules.md)).
- [ ] Staging smoke tests pass (see below) and the invisibility crawl passes on staging.
- [ ] Approval recorded before production (founder sign-off in the PR or release log).

### Backup
- [ ] Tenant backup taken and verified before the production apply. The backup and restore runbook is listed in [README.md](README.md) as G3 and does not exist yet; until it does, record the backup location and checksum in the release log.

### Rollout
- [ ] Roll out to production per tenant or per site in a stated order, one at a time. Record each tenant's version pin.
- [ ] Watch each site's apply result. A `recovery_required` or `failed_clean` outcome stops the rollout.

### Smoke tests (production, after each site)
- [ ] Sign in with a test account for each role in use (owner, accountant, sales).
- [ ] Open the chat and one approval in the human review queue ([ADR-0049](../decisions/ADR-0049-human-review-queue.md)).
- [ ] Arabic and English views both render in RTL and LTR.
- [ ] Create and read back one test record; confirm it appears in the audit trail.

## Post-release

### Monitoring
- [ ] Error rate, failed applies and `recovery_required` count watched for the first working session after rollout.
- [ ] Gateway and model fallback behaviour checked (model/provider switch runbook is listed in [README.md](README.md) as G2 and does not exist yet).
- [ ] Incidents raised per [../security/incident-response.md](../security/incident-response.md).

### Rollback criteria
Roll back if any of these hold:
- [ ] Any smoke test fails and cannot be fixed within the rollout window.
- [ ] Any site shows `recovery_required` after apply.
- [ ] Any engine invisibility or compliance-field regression is found.
- [ ] Any eval or agent_behaviour regression is seen in production traffic.
- [ ] Data loss or cross-tenant access is suspected: stop the rollout, treat as a security incident.

### Rollback steps
- [ ] Stop the rollout. Pin affected sites to the previous version.
- [ ] Restore from the pre-release backup if data was changed. Follow the restore rules in [../security/data-retention.md](../security/data-retention.md).
- [ ] Clear `recovery_required` on any site using [adapter-recovery-required.md](adapter-recovery-required.md). Do not re-run a blind apply.
- [ ] Re-run smoke tests on the rolled-back version.

### Log entry
- [ ] Session log written (`python3 scripts/new_log.py --author <eldon|partner> --tool <tool> --slug release-<id> --ids <PLAN-IDs>`) with: version, commit, tenants and order, DDL plan reference, backup reference, smoke result, any rollback, and open items.
- [ ] Manual steps logged in [exceptions-register.md](exceptions-register.md).
- [ ] Open questions or risks added to [../open-questions.md](../open-questions.md) or [../risks.md](../risks.md).
