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
| **hijridate** | [github.com/dralshehri/hijridate](https://github.com/dralshehri/hijridate) (PyPI `hijridate`, successor of the deprecated `hijri-converter`; accessed 2026-11-18) | 2.6.0 | MIT (package metadata, accessed 2026-11-18) | Umm al-Qura Hijri to Gregorian conversion in the document intake (CMP-022). Tables cover 1343 to 1500 AH; outside that it raises and the intake drops the date. | Permissive, pure Python, no network. Table accuracy against the official Saudi calendar is UNVERIFIED beyond the library's own claim; a Saudi accountant should spot-check month starts before dates drive any legal or tax logic. |
| **Lucide icons** | [github.com/lucide-icons/lucide](https://github.com/lucide-icons/lucide) (LICENSE read 2026-11-18) | 1.75.0 (release 2026-11-18) | ISC; 130-odd icons derived from Feather are MIT (Cole Bemis) | Outline icon set for the web app and marketing site (brand: 24 px, 1.75 px stroke, BRD-012). | Permissive. Keep both licence texts in the third-party notices that ship with the web bundle. Pin the version when the package is added. Directional icons mirror in RTL by our component, not by the library. Icons are used as-is; no logos of third parties. |

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

1. Version pins are tested in `infra/dev/docker` (ERP-001) before promotion to production.
2. Any newly adopted Frappe app or Python/Node library must be added to this register before merging to `main`.
3. GPL boundaries are reviewed by counsel under LEG-006 to ensure SaaS API boundaries remain clean and non-derivative.
