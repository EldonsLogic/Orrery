# Session log: erp-003-live-bench-and-ci

Date: 2026-11-17
Author: partner
Tool and model: antigravity / gemini-4-hydrogen
Plan IDs: ERP-003

## Summary
Resolved the remaining ERP-003 follow-ups (pre-provisioning credentials-file reservation, CI test integration, and live synthetic-bench provisioning proof) and marked ERP-003 done.

## Files touched
- `scripts/provision_tenant_site.py`: exclusively reserve `--credentials-file` (`O_CREAT | O_EXCL | O_NOFOLLOW`, mode `0600`) before `provision()` so collisions or invalid paths abort before site creation, unlink the empty file on provisioning failure, and document the upstream Frappe v15 `bench new-site` argv constraint.
- `apps/engine/change_engine/change_engine/tests/test_erp_003_tenant_provisioning.py`: added `test_12_credentials_file_precheck_aborts_before_provisioning_and_cleans_up_on_error`.
- `.github/workflows/ci.yml`: run `test_erp_003_tenant_provisioning.py` in `script-tests`.
- `docs/PLAN.md`: marked `ERP-003` `done`.

## Verification
- `python3 -m unittest apps/engine/change_engine/change_engine/tests/test_erp_003_tenant_provisioning.py -v`: 14 tests, OK.
- Live bench test on `platform-erp001-20261111b`: `python3 scripts/provision_tenant_site.py --tenant-id erp003-live-probe --country QA --compose-project platform-erp001-20261111b --credentials-file <tmp> --json` exited `0`; verified `["frappe", "erpnext", "hrms", "change_engine"]`, `site_config.json` (`QA`, `QAR`, `ar`, `Asia/Qatar`, `developer_mode: 0`), and `0600` credentials JSON; dropped the temporary site and removed the credentials file afterwards.
- Inspected `frappe.commands.site.new_site` in the pinned container: confirmed `db_password`, `db_root_password`, and `admin_password` Click options expose no envvar or stdin support (`envvar=None`).

## Decisions
- None.

## Tokens or cost
Unknown.

## Next step
Eldon reviews the PR (touches shared `scripts/` and `.github/workflows/ci.yml`). Next partner tasks: finish `CMP-003` and `ERP-006`, then `BPL-012`, `ERP-021`, `ERP-024`, `PLT-025`.
