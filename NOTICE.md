# NOTICE: third-party licences and provenance

This repository is private and proprietary. This file records what we use or plan to use and under what licence. The full register is plan item LEG-004. Licence facts below come from the project research ([docs/research/04-open-source.md](docs/research/04-open-source.md)) and must be re-verified by counsel (LEG-006); treat as UNVERIFIED until then.

| Component | Licence | Use | Notes |
|---|---|---|---|
| Frappe Framework | MIT | Engine framework | Used as the platform base. |
| ERPNext | GPL-3.0 | Engine, run as SaaS | Not bundled in this repository. Not distributed to customers. Our services stay separate and talk over API. |
| Frappe HRMS | GPL-3.0 | Engine skeleton only | Not bundled here. Same SaaS-only rule. |
| ERPGulf ZATCA app | MIT (planned) | ZATCA e-invoicing | Planned; evaluated in the G1 spike (CMP-002). |
| lavaloon ZATCA app | AGPL | NOT used | Rejected because of the AGPL. |

## Provenance
- The change engine is a prototype written by the partner. It was adapted into `apps/engine/change_engine/` (see its `PROVENANCE.md`; source repository `sayegh9/EXRP`, commit `f0ce226dd8d050fbc947caf50657e651e01792b8`). Licence and IP assignment are to be confirmed in the founders' agreement (LEG-001). It has no LICENSE file yet (LEG-002).
- Fonts and icons used in `docs/brand`: licences UNVERIFIED (BRD-011, BRD-012).

## Trademarks
"Frappe" and "ERPNext" are third-party trademarks. Do not use them in our product name or ads (LEG-009). "Orrery" is a working name and is not cleared (ADR-0001).
