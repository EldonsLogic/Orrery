# Session log: dev-bench-pin

Date: 2026-11-07
Author: partner
Tool and model: antigravity / gemini-3.8-flash
Plan IDs: ERP-001

## Summary
Pinned the Frappe v15 ecosystem version set (Frappe Framework 15.126.0, ERPNext 15.124.5, Frappe HRMS 15.64.8, MariaDB 10.6, Redis 7.2.7-alpine) and established a reproducible dev bench in `infra/dev/docker/`.

## Files touched
- `infra/dev/docker/Dockerfile`: built headless dev engine image based on `frappe/erpnext:v15` with pinned Frappe HRMS `v15.64.8` and change engine mounting support.
- `infra/dev/docker/entrypoint.sh`: added headless runtime initialization, multi-tenant database connection setup, and automatic mounting/editable installation of `change_engine`.
- `infra/dev/docker/docker-compose.dev.yml`: added `engine` service, pinned MariaDB 10.6, and pinned Redis 7.2.7-alpine (BSD-3-Clause).
- `infra/dev/docker/.env.example`: updated with explicit version pins, database credentials, initial site parameters, and configurable ports.
- `infra/dev/docker/README.md`: created complete documentation with pinned version table, quickstart commands, and tenant provisioning workflow.
- `infra/dev/docker/verify_dev_bench.py`: created verification test suite asserting compose syntax, container health, and exact runtime version pins.
- `apps/engine/README.md`: recorded confirmed version pins and reference to `infra/dev/docker`.
- `docs/legal/licence-register.md`: updated Frappe HRMS and Redis rows with exact pinned versions and licence boundaries.
- `docs/open-questions.md`: marked Q-6 (version pin set) and Q-15 (dev Redis BSD licence pin) as resolved.
- `docs/PLAN.md`: marked `ERP-001` as `done`.
- `docs/STATUS.md`: regenerated status.

## Decisions
- Version Set: Pinned Frappe Framework `v15.126.0` (commit `53bae3ef2550ca96320f036f581446783cd11b72`), ERPNext `v15.124.5` (commit `e5cde8c4b9e3f7f567a92ca3e65fd411402b89ce`), and Frappe HRMS `v15.64.8` (commit `186900a6e3db4e6f927f1ee20df745bbb082638a`).
- Redis Licence Hardening: Pinned dev Redis image to `redis:7.2.7-alpine` (BSD-3-Clause) instead of floating `redis:7-alpine`, resolving open question Q-15 for the local development bench.

## Tokens or cost
Approximate session token usage via Gemini 3.8 Flash.

## Next step
Pick up `ERP-003` (scripted site-per-tenant creation) and `BPL-012` (engine adapter interface).
