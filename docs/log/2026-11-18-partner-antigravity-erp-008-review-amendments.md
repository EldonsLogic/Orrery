# Session log: erp-008-role-mapping-review-amendments

Date: 2026-11-18
Author: partner
Tool and model: antigravity / gemini-4-hydrogen
Plan IDs: ERP-008

## Summary
Merged `origin/main` into `erp-008-role-mapping-design` and amended `docs/decisions/ADR-0039-role-and-permission-mapping.md`, `docs/architecture/role-and-permission-mapping.md`, and `docs/security/agent-least-privilege.md` to address all High, Medium, and Low findings from Opus and all Blocker, High, Medium, and Low findings from Gemini 4 Hydrogen on PR #129.

## Changes made
- **ALP-001 / OQ-2 clarification (`docs/security/agent-least-privilege.md`, Opus M6, Hydrogen High 5):** Reworded §3.1.1–2 and `ALP-001` to distinguish a `human shadow engine user` from a `separate draft-only agent engine user`, and recorded the `OQ-2` choice (`one grant-intersected managed role per agent grant = agent-eligible Blueprint role ∩ grant`) for Eldon's confirmation.
- **Multi-role scope conflict fix (Hydrogen Blocker 1, `RM-015` / `D-4` / `DENY-34`):** Resolved `D-4` strictly by forbidding one member from holding multiple active roles with differing scopes on any shared entity (preventing fail-open OR union semantics for `own_records` + `branch` or `branch-A` + `branch-B`), enforced at the assignment store and `sync_members`.
- **Permlevels & child tables (Hydrogen Blocker 2, Med 7, `RM-018` / `DENY-23` / `DENY-38`):** Excluded uniformly `readOnly`/computed fields (`read_only=1`) at level 0 so they do not consume permlevels 1..9; gated `create`/`write`/`report`/`print` enablement on `DENY-23` passing on the bench; required `insert`/REST `PUT` and `reqd` hidden field verification (`DENY-38`).
- **Drift fingerprint & unmapped DocTypes (Opus H4, Hydrogen High 4, `RM-005` / `DENY-37` / `DENY-44`):** Expanded the fingerprint to cover every role on every engine user (managed and built-in/automatic), the complete set of enabled engine users, and built-in/automatic role permissions (`All`, `Guest`, `Desk User`, `Website Manager`) across mapped AND unmapped business/audit/system/file/ledger DocTypes (`Version`, `Comment`, `Communication`, `Activity Log`, `Notification Log`, `File`, `ToDo`, `User`, `Prepared Report`, `Data Import`, `GL Entry`, `Stock Ledger Entry`); stripped non-managed roles and extra grants first.
- **Agent draft-only enforcement & boundary honesty (Opus H5, H7, M6, Hydrogen High 3):** Restricted agent `create`/`write` exclusively to `docstatus == 0` drafts on draft-capable entities (`transitionKind`, `ADR-0037`) and stripped writes on non-submittable master/settings entities (`DENY-36`); stated plainly that engine bounds grant only while gateway enforces on-behalf-of intersection (residual risk); required synchronous durable agent user disablement on revoke/expire/kill (`ALP-022`) and fail-closed adapter kill-flag checks (`ALP-036`, `DENY-42`); flagged follow-up contract ADR for `sync_members` / `sync_principals` (`agent`/`support` + `S17` expiry) and `S09` principal-kind credential split (`ADR-0038`).
- **Scope link check, external assignment store, apply-sync ordering, baseline & gateway checks (Opus H6, M4, M5, L3, L6, Hydrogen High 5, Med 6-7, Low 8):** Added location link validation at plan (`DENY-35`), named single external assignment store refining `ADR-0007` item 9, required role-touching `apply` to pass cache clear + `sync_members` + drift post-condition before reporting `applied` (`DENY-43`), added structural lint on baseline grants (`DENY-45`), clarified `ADR-0027` restoration of approved layout vs extra grants, noted `role.upsert` reuse of disabled managed role records on restore, and added missing negative tests (`DENY-35` to `DENY-46`).

## Verification
- Ran `python3 scripts/check_docs.py`, `python3 scripts/check_repo_hygiene.py`, `python3 scripts/scan_secrets.py --all`, `python3 scripts/check_lanes.py`, and `python3 scripts/check_pr_trail.py`.
