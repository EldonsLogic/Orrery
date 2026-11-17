# Session log: scripted-tenant-creation

Date: 2026-11-07
Author: partner
Tool and model: antigravity / gemini-3.8-flash
Plan IDs: ERP-003

## Summary
Implemented scripted site-per-tenant creation for the Frappe/ERPNext engine runtime with per-tenant database isolation, automated app installation, regional market defaults (SA, AE, EG, QA), and headless engine invisibility.

## Files touched
- `scripts/provision_tenant_site.py`: core provisioning automation CLI implementing input validation, deterministic database name generation, password generation, bench command assembly, headless site config overrides, and structured JSON output.
- `infra/dev/docker/provision_tenant.sh`: shell wrapper for convenient tenant site provisioning inside the dev container bench.
- `apps/engine/change_engine/change_engine/tests/test_erp_003_tenant_provisioning.py`: comprehensive unit test suite covering tenant validation, market currency/locale defaults, command planning, headless flags, simulated execution, and CLI JSON output.
- `docs/PLAN.md`: marked `ERP-003` as `done`.
- `docs/STATUS.md`: regenerated status.

## Decisions
- ADR-0006 compliance: Each tenant receives a dedicated MariaDB database (`_t_<hash12>`) and database user (`u_<hash12>`) on the engine bench.
- ADR-0016 compliance: Automatically configures `engine_invisibility: 1` and `disable_website: 1` in `site_config.json` so the engine remains headless behind the platform gateway.
- Regional defaults (ADR-0024): Supported markets SA (`SAR`, Arabic, Asia/Riyadh), AE (`AED`, Arabic, Asia/Dubai), EG (`EGP`, Arabic, Africa/Cairo), QA (`QAR`, Arabic, Asia/Qatar).

## Tokens or cost
Approximate session token usage via Gemini 3.8 Flash.

## Next step
Pick up `BPL-012` (engine adapter interface) and `CMP-002` (evaluate ZATCA app).
