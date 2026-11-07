# NOTICE: third-party licences and provenance

This repository is proprietary. This file summarizes what we use or plan to use and under what licence. The full register is in [docs/legal/licence-register.md](docs/legal/licence-register.md) (LEG-004). Licence facts below come from the project research ([docs/research/04-open-source.md](docs/research/04-open-source.md)) and the partner's verified bench installation, to be re-verified by counsel (LEG-006).

| Component | Pinned version | Licence | Use | Notes |
|---|---|---|---|---|
| Frappe Framework | 15.126.0 | MIT | Engine framework | Used as the platform base. Full-stack metadata and ORM. |
| ERPNext | 15.124.5 | GPL-3.0 | Engine, run as SaaS | Enterprise modules. Not bundled in this repository. Not distributed to customers. Our services stay separate and talk over API. |
| Change engine module | 0.1.0 | Proprietary / Founder contribution | Engine app | Guarded apply, DDL gate, rollback, audit, runtime policies (`apps/engine/change_engine/`). |
| Frappe HRMS | v15 (planned) | GPL-3.0 | Engine skeleton only | Not bundled here. Same SaaS-only rule. |
| ERPGulf ZATCA app | Planned | MIT | ZATCA e-invoicing | Planned; evaluated in the G1 spike (CMP-002). |
| lavaloon ZATCA app | - | AGPL-3.0 | NOT used | Rejected because of the AGPL. |

## Provenance
- The change engine is a prototype written by the partner. It was adapted into `apps/engine/change_engine/` (see its `PROVENANCE.md`; source repository `sayegh9/EXRP`, commit `f0ce226dd8d050fbc947caf50657e651e01792b8`). Licence and IP assignment are to be confirmed in the founders' agreement (LEG-001). It has no LICENSE file yet (LEG-002).
- Fonts and icons used in `docs/brand`: licences UNVERIFIED (BRD-011, BRD-012).

## Trademarks
"Frappe" and "ERPNext" are third-party trademarks. Do not use them in our product name or ads (LEG-009). "Orrery" is a working name and is not cleared (ADR-0001).
