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
| **Frappe HRMS** | [github.com/frappe/hrms](https://github.com/frappe/hrms) | v15 (planned) | GNU GPL v3.0 | Payroll and HR skeleton only for regional compliance. | Planned; same SaaS-only boundary as ERPNext (ADR-0002). |
| **ERPGulf ZATCA app** | [github.com/ERPGulf/zatca_erpgulf](https://github.com/ERPGulf/zatca_erpgulf) | v3.0.1 (evaluated) | MIT | Saudi ZATCA Phase 2 e-invoicing integration. | Evaluated in CMP-002 ([docs/compliance/zatca-erpgulf-evaluation.md](../compliance/zatca-erpgulf-evaluation.md)). Permissive MIT licence confirmed; core logic to be vendored/wrapped without Desk UI per ADR-0016. |

## 2. Forbidden components

| Component | Upstream / source | Licence | Status | Reason |
|---|---|---|---|---|
| **Lavaloon ZATCA app** | Upstream Frappe marketplace | GNU AGPL v3.0 | Rejected / Forbidden | AGPL-3.0 network copyleft conflicts with our SaaS architecture and proprietary service boundary. |

## 3. Infrastructure base containers

| Component | Upstream / image | Pinned version | Licence | Role / Why used | Boundary notes |
|---|---|---|---|---|---|
| **MariaDB** | `mariadb` official Docker image | 10.6 | GNU GPL v2.0 | Primary relational database for engine tenant sites. | Standard server backend; isolated network in Docker. |
| **Redis** | `redis` official Docker image | 7-alpine (floating tag, to be pinned) | BSD-3-Clause up to 7.2.x; RSALv2 or SSPLv1 from 7.4; Redis 8 adds AGPLv3 (UNVERIFIED, re-check upstream) | Cache and background queue broker for Frappe bench. | The floating `7-alpine` tag moves to 7.4 or later, which is not BSD. Pin 7.2.x (last BSD line) or switch to Valkey (BSD-3-Clause) before any hosted use; dev compose is a partner-lane change (open question Q-15). |

## 4. Verification and maintenance

1. Version pins are tested in `infra/dev/docker` (ERP-001) before promotion to production.
2. Any newly adopted Frappe app or Python/Node library must be added to this register before merging to `main`.
3. GPL boundaries are reviewed by counsel under LEG-006 to ensure SaaS API boundaries remain clean and non-derivative.
