# Session log: sec-002-review-amendments

Date: 2026-11-18
Author: partner
Tool and model: antigravity / gemini-4-hydrogen
Plan IDs: SEC-002

## Summary
Merged `origin/main` into `sec-002-secrets-design` and amended `docs/decisions/ADR-0038-secrets-management.md` and `docs/security/secrets-management.md` to address all Critical, High, Medium, and Low findings from both the Opus pre-review and the Gemini 4 Hydrogen cross-model review on PR #128, plus the founder's pilot-only ZATCA fallback signer decision and `ADR-0042` renumbering cross-reference.

## Changes made
- **ZATCA signer hardening (Opus C1, Hydrogen H4, pilot rule):** Replaced bare digest signing with canonical invoice / `<xades:SignedProperties>` input verification, ICV/PIH chain verification, mTLS (`S03`) caller pool binding (never caller-asserted `tenantId`), per-unit rate cap/alerting, isolated per-tenant fallback process with single-signature zeroization (no shared batch key cache), explicit `Z1` addition to `SEC2-005`, updated `Z3` multi-year CSID lifetime note (`UNVERIFIED` pending `CMP-004`) + bounded retry drain overlap, and recorded the first-pilot-only fallback exception (encrypted at rest, signer-only readable, replaced before G3; `CMP-004` still tests non-exportable KMS/HSM) citing `ADR-0042` (`#124`).
- **Workload identity & provisioning boundary (Opus H1/M1/M2/M3, Hydrogen H2):** Clarified `SEC2-018` is an application guard for pool-shared `S05`/`S07` while store enforces pool workload identity (recorded in `SEC-004`), narrowed `S11`/`Z1`/`S17` to per-tenant identities, introduced ephemeral `provisioning-site-init` separate from `provisioning-secret-admin` and `engine-adapter`, documented the inside-container `ERP-003` argv gap requiring file/fd/stdin/SQL before production, added backup exclusion + archive scanning for `site_config.json`, and specified dual-slot (`slot_a`/`slot_b`) rotation for `S05`/`S07`.
- **Break-glass refinement (Opus H2, Hydrogen M6):** Refined `ADR-0007` item 7 explicitly (platform-incident repair with zero tenant-data read, `PLT-019` approval where reachable, `Q-14` cross-border dependency), added automated forced rotation at session close / T+60m (alert at T+65m), and defined `S06` multi-tenant DB server audit/notification rules.
- **OTP & gateway fingerprint mechanics (Hydrogen H1/H3, Opus L2):** Reconciled `Z4` unstored plaintext OTP with persisted keyed-HMAC single-use replay marker (`SEC2-T10`), added `S23` gateway fingerprint HMAC key with synchronous invalidation, mid-run fail-closed staleness handling, and oracle-safe refusal (`SEC2-T36`–`T37`), and reworded `SEC2-035` to OTP-in-form-only instead of chat pattern matching.
- **Inventory & external sources (Hydrogen M5/M7/L8, Opus L1):** Split `S10` into regional `S10a` KEK and per-tenant `S10b` DEKs/backup DEKs, added `S21` (`site_config.json` `encryption_key`), `S22` (control-plane regional DB credentials), and `S23` (`S23` HMAC key), required OIDC federation (`INF-003`) for `S18`, cited OpenBao/Azure/GCP/ZATCA statuses with `UNVERIFIED` markers, and added tests `SEC2-T33`–`T39`.

## Verification
- Ran `python3 scripts/check_docs.py`, `python3 scripts/check_repo_hygiene.py`, `python3 scripts/scan_secrets.py --all`, `python3 scripts/check_lanes.py`, and `python3 scripts/check_pr_trail.py`.
