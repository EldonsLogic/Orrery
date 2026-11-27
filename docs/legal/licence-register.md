# Third-party licence register

Status: accepted
Owner: partner

Principle 1: Build on open source; record every licence. Every adopted open-source component, framework, service base image, and engine add-on must be recorded here with its upstream source, version, licence, and architectural boundary.

## 1. Engine and ERP runtime components

| Component | Upstream / source | Pinned version | Licence | Role / Why used | Boundary & compliance notes |
|---|---|---|---|---|---|
| **Frappe Framework** | [github.com/frappe/frappe](https://github.com/frappe/frappe) | 15.126.0 | MIT | Core web framework, DocType metadata, Desk, ORM, MariaDB abstraction, auth, RBAC, REST APIs, background worker jobs. | Permissive; no copyleft restrictions. Modified or configured freely. |
| **ERPNext** | [github.com/frappe/erpnext](https://github.com/frappe/erpnext) | 15.124.5 | GNU GPL v3.0 | Foundational enterprise ERP modules (Accounts, Selling, Buying, Stock, HR, Manufacturing). | SaaS-only runtime behind platform gateway (ADR-0002). Never distributed as client software or binaries. Invisible to end customers (ADR-0016). |
| **Change engine module** | `apps/engine/change_engine/` (adapted from partner prototype) | 0.1.0 | Proprietary / Founder contribution | Deterministic configuration change engine: safety guardrails, DDL plan inspection gate, 6-stage deploy with advisory lock, rollback, and runtime policy engine. | Adapted from partner prototype (commit `f0ce226dd8d050fbc947caf50657e651e01792b8`). IP assignment to be formalized under LEG-001/LEG-002. Runs as an engine app. |
| **Frappe HRMS** | [github.com/frappe/hrms](https://github.com/frappe/hrms) | 15.64.8 | GNU GPL v3.0 | Payroll and HR skeleton only for regional compliance. | SaaS-only runtime behind platform gateway (ADR-0002). Pinned for G1 dev bench under ERP-001. |
| **ERPGulf ZATCA app** | [github.com/ERPGulf/zatca_erpgulf](https://github.com/ERPGulf/zatca_erpgulf) (accessed 2026-11-14) | v3.0.1 (draft evaluation; tag commit `d906ba7`) | MIT | Saudi ZATCA Phase 2 e-invoicing integration. | Early draft evaluation in CMP-002 ([docs/compliance/zatca-erpgulf-evaluation.md](../compliance/zatca-erpgulf-evaluation.md)). Upstream MIT licence and checked direct/runtime deps confirmed (accessed 2026-11-14); transitive tree UNVERIFIED. PROPOSED wrapper/vendoring without Desk UI (ADR-0016) requires an ADR and, if vendored, a dedicated PR with `PROVENANCE.md`. |

### 1b. Python libraries used by our own services

| Component | Upstream / source | Pinned version | Licence | Role / Why used | Boundary & compliance notes |
|---|---|---|---|---|---|
| **hijridate** | [github.com/dralshehri/hijridate](https://github.com/dralshehri/hijridate) (PyPI `hijridate`, successor of the deprecated `hijri-converter`; accessed 2026-11-18) | 2.6.0 | MIT (package metadata, accessed 2026-11-18) | Umm al-Qura Hijri to Gregorian conversion in the document intake (CMP-022) and the Ramadan periods of per-company working hours (CMP-023, `components/compliance/company_calendar/`). Tables cover 1343 to 1500 AH; outside that it raises: the intake drops the date, and the calendar fails closed with `calendar_range`. | Permissive, pure Python, no network. Table accuracy against the official Saudi calendar is UNVERIFIED beyond the library's own claim; a Saudi accountant should spot-check month starts before dates drive any legal or tax logic. This applies with extra force to the CMP-023 Ramadan hours, which are close to labour law (the spec, section 3, repeats the caveat). The pin must equal the engine package's pin; a CMP-023 test fails when they differ. |
| **Lucide icons** | [github.com/lucide-icons/lucide](https://github.com/lucide-icons/lucide) (LICENSE read 2026-11-18) | 1.75.0 (release 2026-11-18) | ISC; 130-odd icons derived from Feather are MIT (Cole Bemis) | Outline icon set for the web app and marketing site (brand: 24 px, 1.75 px stroke, BRD-012). | Permissive. Keep both licence texts in the third-party notices that ship with the web bundle. Pin the version when the package is added. Directional icons mirror in RTL by our component, not by the library. Icons are used as-is; no logos of third parties. |

### 1b-ii. Typefaces (BRD-011)

Not bundled yet. The rows record licence and the boundary for self-hosting; the pinned file and its hash are set by the PR that adds the WOFF2 files. Licence check: [docs/brand/font-licence-check.md](../brand/font-licence-check.md), accessed 2026-11-21.

| Component | Upstream / source | Pinned version | Licence | Role / Why used | Boundary & compliance notes |
|---|---|---|---|---|---|
| **Readex Pro** | [fonts.google.com/specimen/Readex+Pro](https://fonts.google.com/specimen/Readex+Pro); [OFL.txt](https://github.com/ThomasJockin/readexpro) (accessed 2026-11-21) | Not bundled; variable wght 160 to 700 (Google Fonts METADATA, accessed 2026-11-21) | SIL OFL 1.1 (OFL.txt: "licensed under the SIL Open Font License, Version 1.1"). Reserved Font Name: 'RevReading Lexend' | Interface and body text in `web/app` and `web/marketing` (`--font-body`); the tax invoice print format (ERP-007). | Embedding in PDFs and self-hosted webfonts are permitted (OFL FAQ 1.12, 2.1, accessed 2026-11-21). Subsetting or format conversion is a modification: rename the subset, do not use the RFN, and ship OFL.txt with each file. Arabic-Indic digits and tabular figures UNVERIFIED. |
| **Cairo** | [fonts.google.com/specimen/Cairo](https://fonts.google.com/specimen/Cairo); google/fonts `ofl/cairo/Cairo[slnt,wght].ttf` and [OFL.txt](https://github.com/google/fonts/tree/a2c83daed9bc723922de8d0a9512990bd3d91df4/ofl/cairo) at commit `a2c83daed9bc723922de8d0a9512990bd3d91df4` (accessed 2026-11-23) | Not bundled; build-time input at that commit (TTF SHA-256 `667c987182391c91f4e57a2f455b1794fb5e3ee6ca4ef3383e86bb690fa9c964`); variable wght and slnt | SIL OFL 1.1 (OFL.txt: Copyright 2009 The Cairo Project Authors, https://github.com/Gue3bara/Cairo). No Reserved Font Name | Headings (`--font-heading`) in product, site and documents, and the outlined Seshna wordmark: `docs/brand/tools/build_logo.py` outlines it at wght 700 into `docs/brand/logo/*.svg` (ADR-0066, BRD-014). | Not shipped as a font file in the repo; the outlined wordmark is artwork, not a font. When WOFF2 files are self-hosted, ship OFL.txt with each file (no RFN, so subsets need no rename). Arabic-Indic digits, tabular figures and 2025 currency symbols UNVERIFIED. |
| **Alexandria** | [fonts.google.com/specimen/Alexandria](https://fonts.google.com/specimen/Alexandria); [OFL.txt](https://github.com/google/fonts/tree/main/ofl/alexandria) (accessed 2026-11-21) | Not bundled; variable wght 100 to 900 (Google Fonts METADATA, accessed 2026-11-21) | SIL OFL 1.1 (OFL.txt: "licensed under the SIL Open Font License, Version 1.1"). No Reserved Font Name | Retired from the brand by ADR-0066 (2026-11-23): Cairo replaces it for headings and the wordmark. Still named in the print format stack and the Studio page until their owners switch them. | Same OFL terms for embedding and self-hosting; no RFN, so subsetting needs no rename but keep OFL.txt. Arabic-Indic digits UNVERIFIED. |
| **Noto Sans Arabic** | [fonts.google.com/noto/specimen/Noto+Sans+Arabic](https://fonts.google.com/noto/specimen/Noto+Sans+Arabic); [OFL.txt](https://github.com/google/fonts/tree/main/ofl/notosansarabic) (accessed 2026-11-21) | Not bundled | SIL OFL 1.1 (OFL.txt, Copyright 2022 The Noto Project Authors). No Reserved Font Name | Named as a fallback in the print format `font-family` stack only (ERP-007). Not used in the web CSS. | Embedding permitted. Only a fallback name today; if the print format ships it, bundle with OFL.txt. Glyph coverage of Arabic-Indic digits and the SAR symbol UNVERIFIED. |
| **DejaVu Sans** | [dejavu-fonts.github.io](https://github.com/dejavu-fonts/dejavu-fonts) (LICENSE read 2026-11-21) | Not bundled | Bitstream Vera licence (permits redistribution; modified copies must not use the words "Bitstream" or "Vera") | Named as a fallback in the print format `font-family` stack only (ERP-007). | Permissive. Only a fallback name today; if bundled, keep the licence notice. |

Arial is also named in the print format stack. It is a Microsoft font, not licensed by this register, and is not bundled; the licence position is UNVERIFIED and it should be removed from the stack or replaced with a bundled fallback before print formats ship (see the check file).

### 1c. Planned libraries (not installed)

Recorded ahead of first use under ADR-0044 (Proposed). Not in any lockfile yet; the exact pin is set and this row updated by the PR that installs it (OPR-020, WEB-026).

| Component | Upstream / source | Pinned version | Licence | Role / Why used | Boundary & compliance notes |
|---|---|---|---|---|---|
| **ag-ui-protocol** (planned) | [github.com/ag-ui-protocol/ag-ui](https://github.com/ag-ui-protocol/ag-ui), PyPI [`ag-ui-protocol`](https://pypi.org/project/ag-ui-protocol/) (accessed 2026-11-18) | Not installed; latest seen 1.0.0 (2026-09-17) | MIT (PyPI `license_expression`, accessed 2026-11-18) | Python event types and SSE encoder for the agent stream endpoint (ADR-0044). | Owned by CopilotKit; single-vendor risk, fallback in ADR-0044 item 8. Transport only; no CopilotKit runtime or integrations (advisory GHSA-chx5-hp6j-gv92 hit `ag-ui-adk`, which we do not use). Transitive dependencies UNVERIFIED until installed. |
| **@ag-ui/client** (planned) | [github.com/ag-ui-protocol/ag-ui](https://github.com/ag-ui-protocol/ag-ui), npm [`@ag-ui/client`](https://www.npmjs.com/package/@ag-ui/client) (accessed 2026-11-18) | Not installed; latest seen 1.0.5 (release 2026-11-17) | MIT (repo `packages/client/package.json`, accessed 2026-11-18) | Browser client for the agent stream in `web/app` (ADR-0044). | Owned by CopilotKit; no CopilotKit UI components. Keep the licence text in the third-party notices of the web bundle. Transitive dependencies UNVERIFIED until installed. |

## 2. Forbidden components

| Component | Upstream / source | Licence | Status | Reason |
|---|---|---|---|---|
| **Lavaloon ZATCA app** | Upstream Frappe marketplace | GNU AGPL v3.0 | Rejected / Forbidden | AGPL-3.0 network copyleft conflicts with our SaaS architecture and proprietary service boundary. |

## 3. Infrastructure base containers

| Component | Upstream / image | Pinned version | Licence | Role / Why used | Boundary notes |
|---|---|---|---|---|---|
| **MariaDB** | `mariadb` official Docker image | 11.4 | GNU GPL v2.0 | Primary relational database for engine tenant sites. | Standard server backend; isolated network in Docker (upgraded from EOL 10.6 under ERP-024). |
| **Redis** | `redis` official Docker image | 7.2.7-alpine | BSD-3-Clause (source; counsel review pending) | Cache and background queue broker for Frappe bench. | The dev image is pinned by digest. [Upstream source licence](https://github.com/redis/redis/blob/7.2.7/COPYING), accessed 2026-11-11; image contents and legal interpretation remain UNVERIFIED (Q-15). |

## 4. Verification and maintenance

ERP-020 headless build dependency: `flit_core` 3.12.0, BSD-3-Clause. This is the
app's existing PEP 517 build backend, preinstalled by immutable wheel hash so
startup can install the mounted app with no package index or build isolation.
Source and licence: [PyPI release metadata](https://pypi.org/project/flit-core/3.12.0/),
accessed 2026-11-19. No upstream source is copied into this repository.

ERP-020 CI dependency: Werkzeug 3.1.3, BSD-3-Clause (package metadata).
The engine already uses Werkzeug; the standalone guard tests install it explicitly.
Source: [PyPI release metadata](https://pypi.org/project/Werkzeug/3.1.3/),
accessed 2026-11-19. No source is copied into this repository.

1. Version pins are tested in `infra/dev/docker` (ERP-001) before promotion to production.
2. Any newly adopted Frappe app or Python/Node library must be added to this register before merging to `main`.
3. GPL boundaries: for SaaS-only delivery they are answered by [gpl-saas-boundary.md](../research/gpl-saas-boundary.md) and [ADR-0074](../decisions/ADR-0074-gpl-boundary-settled-by-research.md) (LEG-006), with its rules enforced. ADR-0074 rule 7 makes this register the allowlist for apps, pip and npm packages and container images, beside a blocklist (AGPL, unknown licences), checked by QA-027 and QA-028. Counsel reviews before anything that conveys a copy (LEG-017).
