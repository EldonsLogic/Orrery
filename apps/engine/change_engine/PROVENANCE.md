# Provenance of the change engine module

Status: accepted | Owner: eldon

## Source
Adapted from a prototype written by the partner (GitHub `sayegh9/EXRP`, branch `develop`, commit `f0ce226dd8d050fbc947caf50657e651e01792b8`, snapshot of 2026-11-05). The prototype was a standalone Frappe app for natural-language form customisation inside Frappe's Desk. We kept the parts that fit the Orrery architecture and removed the rest. The prototype repository is not modified and remains the original reference. This file is the only place in the repo that names the prototype.

## Kept (renamed, code logic unchanged unless listed under "Changed")
Safety guardrails, DDL plan inspection gate, six-stage deploy with advisory lock and audit journal, property-setter engine, workflow engine (reachability checks), report engine (operator allowlist), rollback and soft quarantine, runtime and cross-document policy engines, compact schema extractor, the API layer without its LLM paths, and the unit tests for all of these.

## Not imported, and why
| Prototype part | Why it does not fit |
|---|---|
| LLM planner (provider-specific, runs inside the engine process) | AI work runs in separate services behind the model gateway and outputs a Blueprint diff; engine-side code stays deterministic and unlinked from model providers. Its prompts and self-correction idea can be reused when the Blueprint planner is built (plan items under BPL/DSC) |
| In-Desk AI sidebar (JS/CSS) | The product has one chat in its own interface with role-based views, not a Desk add-on |
| LLM settings screen and doctype | Provider keys and models belong to the gateway |
| Mock ERP data seeder and demo workspaces | We use real ERPNext doctypes; synthetic data will come from a separate generator (DAT items) |
| Branding assets, brand kit, landing-route hooks | Old identity; the product identity is in `docs/brand/` |
| Desk-runner docker setup (machine-specific paths) | Dev stack is rebuilt in `infra/dev/` during the G1 spike |
| Prototype design documents and decision records | Superseded by our own decision records; they stay in the prototype repository |
| Prototype CI and templates | Replaced by repo-level CI |

## Changed during import
- Package and app renamed to `change_engine`; sub-package `guarded_apply`; endpoints in `api/endpoints.py`. Audit table renamed `tabChange Engine Audit`. Advisory lock key prefix renamed.
- CE-SEC-001: roles taken only from the session inside Frappe. CE-SEC-002: role lookup fails closed. CE-SEC-004: LLM endpoints removed. CE-SEC-003 partly: policy registration no longer exposed over HTTP, read endpoints require an authorised role (persistence still open).
- Added `tests/test_caller_roles.py` (6 regression tests).
- `hooks.py` reduced to policy enforcement; `pyproject.toml` rewritten; licence field set to TBD.

## Verification at import
68 inherited unit tests and 6 new tests pass standalone (mocks). The live MariaDB test and any real Frappe bench run are not done.

## Licence and IP
The prototype's code header states MIT, but the source repository has no LICENSE file. Contribution and IP assignment to the company must be confirmed in the founders' agreement (plan item LEG-002) before any external use.
