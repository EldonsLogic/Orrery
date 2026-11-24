# Session log: plt-003-provisioning-review-amendments

Date: 2026-11-18
Author: partner
Tool and model: antigravity / gemini-4-hydrogen
Plan IDs: PLT-003

## Summary
Merged `origin/main` into `plt-003-provisioning-design` and amended `docs/decisions/ADR-0040-tenant-provisioning-service.md` and `docs/architecture/tenant-provisioning.md` to address all High, Medium, and Low findings from Opus and all Blocker, High, Medium, and Low findings from Gemini 4 Hydrogen on PR #144.

## Changes made
- **Step 10 invisibility probe gate & UNVERIFIED flags (`PROV-008`, `PROV-T32`, Opus H3, L1):** Gated public host routing (`register_route`) strictly on a passing gateway-path invisibility probe (`PLT-024`, `ERP-020`) rather than deferring to `QA-016`; marked `Administrator login off` and `customer login off` `UNVERIFIED` pending bench tests.
- **Secret custody, argv gap & adoption safety (Hydrogen Blocker 1, Opus H8, `PROV-006`, `PROV-T31`):** Reconciled `S05`/`S06`/`S08` with `ADR-0038` via ephemeral `provisioning-site-init` (or `site.schema.json` follow-up ADR), flagged the `scripts/provision_tenant_site.py` container argv gap requiring file/fd/stdin/SQL before production, added `S21` (`encryption_key`), `S22` (control-plane DB), `S10a`/`S10b` split, and `S07` check, banned `tenantId` reuse, and required `{workflowId, state}` metadata so `pending_destruction` secrets block rather than get adopted.
- **`ADR-0041` initialization & Step 3 partial crash repair (Hydrogen Blocker 2, `PROV-T33`):** Moved `init_adapter_state` immediately upon DB creation inside Step 3 (`create_site`) before app installs complete, added deterministic partial DB/`sites/<tenant>` observation and repair on retry, and made Step 5 `verify_adapter_state`.
- **Parked wait states & Steps 7–9 order (Hydrogen High 3, `PROV-007`, `PROV-T39`):** Added lease-releasing `awaiting_approval` (with clean re-`plan` on `planToken` expiry), `waiting_grace`, and `waiting_recovery_window` (`resumeAt`) states; aligned Steps 7–9 with `ADR-0039` so `apply` verifies role/level schema while Steps 8–9 complete full `sync_members` and drift baseline before Step 10.
- **Deprovisioning completeness, legal-hold lock, dual approval & AI/search purge (Hydrogen High 4, Opus M7, M8, Low 8):** Step 1 (`close_access`) now engages per-tenant agent kill switch (`ALP-035`), drops triggers (`ALP-025`), pauses connectors, and halts e-invoices; Step 5 deletes all AI/search/memory/transcript/embedding/cache/brand stores per `data-retention.md` §7 Step 5; Step 5/8 retries avoid deleted tenant DBs; live deletion requires dual approval (`PROV-015`) plus transactional DB hold lock (`SELECT ... FOR UPDATE` + fencing token) before each destructive call (`PROV-T37`); clarified `DAT-007` tombstone retention.
- **Slug uniqueness/quarantine, verified signup, `D-1` update & `PROV-T31..T39` (Hydrogen High 5, Med 6-7, Opus M9, M10, L4):** Enforced canonical/homograph DB unique constraint in `reserve`, quarantined cancelled/deprovisioned slugs (`PROV-T34`), required verified identity + rate limit + server-derived region/pack/Blueprint (`PROV-T35`), updated `D-1` for `c51ebc8` (`#147` `services/provisioning/`), and added tests `PROV-T31` to `PROV-T39`.

## Verification
- Ran `python3 scripts/check_docs.py`, `python3 scripts/check_repo_hygiene.py`, `python3 scripts/scan_secrets.py --all`, `python3 scripts/check_lanes.py`, and `python3 scripts/check_pr_trail.py`.
