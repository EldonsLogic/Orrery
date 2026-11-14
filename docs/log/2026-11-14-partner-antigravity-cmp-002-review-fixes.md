# Session log: cmp-002-review-fixes

Date: 2026-11-14
Author: partner
Tool and model: antigravity / gemini-4-hydrogen
Plan IDs: CMP-002

## Summary
Addressed all seven PR #42 review findings on the `CMP-002` ERPGulf ZATCA evaluation by re-verifying upstream facts against primary sources on 2026-11-14, marking unverified runtime/audit claims as `UNVERIFIED`, framing architectural recommendations as `PROPOSED`, keeping `R-018` `open`, and recording corrections to the 2026-11-07 log without editing prior logs.

## Files touched
- `docs/compliance/zatca-erpgulf-evaluation.md`: Changed `Status: final` to `Status: draft`; added G1/G0 gate note while `CMP-002` is `doing` and `ERP-001` is open; replaced unverified commit/date/licence/issue figures with verified values and full source URLs (accessed 2026-11-14); separated static code inspection from runtime/ZATCA validator/sandbox conformance (`UNVERIFIED`), transitive dependency tree (`UNVERIFIED`), production adoption breadth (`UNVERIFIED`), and broader library survey (`UNVERIFIED`); marked wrapper/vendoring, `components/compliance/zatca` / `apps/engine/zatca_engine`, and roadmap items as `PROPOSED` requiring an ADR and a dedicated `PROVENANCE.md` + `NOTICE.md` PR; replaced working codename references with "the platform".
- `docs/compliance/e-invoicing.md`: Softened line 19 from "completed" to "Draft technical evaluation of ERPGulf" (`CMP-002`, `doing`; runtime/sandbox conformance `UNVERIFIED`).
- `docs/legal/licence-register.md`: Updated the ERPGulf row to note `v3.0.1 (draft evaluation; tag commit d906ba7)`, 2026-11-14 access date, transitive dependency tree `UNVERIFIED`, and `PROPOSED` wrapper/vendoring requiring an ADR and dedicated `PROVENANCE.md` PR.
- `docs/risks.md`: Restored `R-018` status from `mitigating` back to `open` (matching `main` + adding "may lag ZATCA changes" and regulation watcher), marked mitigation steps as `PROPOSED`, and noted transitive deps / sandbox conformance `UNVERIFIED`.
- `docs/log/2026-11-14-partner-antigravity-cmp-002-review-fixes.md`: Created this session log recording all seven fixes, verified URLs, `UNVERIFIED` boundaries, and the append-only correction to the 2026-11-07 log.

## Review verification & corrections (accessed 2026-11-14)
- **Version, tag commit, release date, and branch head:** `v3.0.1` (`__version__ = "3.0.1"`, https://github.com/ERPGulf/zatca_erpgulf/blob/main/zatca_erpgulf/__init__.py) points to tag commit `d906ba70ad95ae985c9fe3cc5debbb7782f9a82a` (`d906ba7`, authored 2026-02-22, https://github.com/ERPGulf/zatca_erpgulf/commit/d906ba70ad95ae985c9fe3cc5debbb7782f9a82a); GitHub release `v3.0.1` was published 2026-07-22 (https://github.com/ERPGulf/zatca_erpgulf/releases/tag/v3.0.1). The 2026-11-07 draft cited non-existent commit `7d686f7` (HTTP 422 on GitHub API) and "active through 2026-11-03" (commit prior to 2026-11-07 was `ba0a088` on 2026-10-26; latest on `main` as of 2026-11-14 is `c3fabcb` on 2026-11-13, https://github.com/ERPGulf/zatca_erpgulf/commits/main).
- **Upstream licence & dependencies:** Upstream `LICENSE` is MIT (`Copyright (c) 2024 ERPGulf`, https://github.com/ERPGulf/zatca_erpgulf/blob/main/LICENSE) and `hooks.py` sets `app_license = "mit"` (`license.txt` is an unedited template). Declared direct dependencies in `pyproject.toml` (https://github.com/ERPGulf/zatca_erpgulf/blob/main/pyproject.toml): `asn1>=2.7.0,<3.0.0` is MIT (https://pypi.org/project/asn1/); `pikepdf>=8.0.0,<10.0.0` is **MPL-2.0** (https://pypi.org/project/pikepdf/, https://github.com/pikepdf/pikepdf/blob/main/LICENSE.txt; correcting the 2026-11-07 claim of "MPL 2.0 / LGPL-3.0+"; wheel third-party notice in https://github.com/pikepdf/pikepdf/blob/main/third-party-licenses/README.md). Direct Python imports supplied via Frappe v15 / environment: `cryptography` (Apache-2.0 OR BSD-3-Clause, https://pypi.org/project/cryptography/), `lxml` (BSD-3-Clause, https://pypi.org/project/lxml/), `requests` (Apache-2.0, https://pypi.org/project/requests/), and `PyQRCode` (BSD, https://pypi.org/project/PyQRCode/). Transitive dependency tree remains `UNVERIFIED`.
- **Alternatives:** `lavaloon-eg/ksa_compliance` is GNU AGPL-3.0 (https://github.com/lavaloon-eg/ksa_compliance/blob/master/LICENSE); Odoo `addons/l10n_sa_edi` is LGPL-3 (https://github.com/odoo/odoo/blob/18.0/addons/l10n_sa_edi/__manifest__.py, https://github.com/odoo/odoo/blob/18.0/LICENSE). Broad market survey outside these three options is `UNVERIFIED`.
- **Community, issues/PRs, and tests:** Repo has `65` stars and `95` forks (https://github.com/ERPGulf/zatca_erpgulf, accessed 2026-11-14; production adoption breadth `UNVERIFIED`), `43` issues (https://github.com/ERPGulf/zatca_erpgulf/issues) + `226` PRs (https://github.com/ERPGulf/zatca_erpgulf/pulls) = `269` total (`34` open combined, including PR #265 https://github.com/ERPGulf/zatca_erpgulf/pull/265 and PR #266 https://github.com/ERPGulf/zatca_erpgulf/pull/266), correcting the 2026-11-07 "~270 issues" claim. All four `test_*.py` files contain `pass` stubs and `.github/workflows/frappe-ci.yml` targets `raven`.
- **Correction to prior log (`docs/log/2026-11-07-partner-antigravity-zatca-erpgulf-evaluation.md`):** Left untouched per append-only log rules. Note that the 2026-11-07 log recorded marking `CMP-002` as `done` (inaccurate for a G1 row while G0 is active and `ERP-001` is open; reverted to `doing` in `docs/PLAN.md` by the 2026-11-11 rebase) and wrote `Tool and model: antigravity` without specifying the model name in the header (its body mentions Gemini model calls; exact Gemini model version unknown).

## Decisions
- Kept `CMP-002` in `doing` and `R-018` in `open`.
- Marked all architectural choices (wrapper vs. vendoring, target module paths, transactional PIH sequence, event adapter, sandbox suite) as `PROPOSED`, requiring an ADR before implementation and a dedicated `PROVENANCE.md` + `NOTICE.md` PR if any third-party code is vendored.

## Tokens or cost
Unknown.

## Next step
After `ERP-001` delivers a working bench, run live ZATCA validator/sandbox/PDF/A-3 conformance verification and full transitive dependency auditing to complete `CMP-002` and unblock `CMP-003` / `CMP-004` at G1.
