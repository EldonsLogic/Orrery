# Data protection and residency

Status: draft
Owner: eldon

All items UNVERIFIED unless the research supports them. Source: [../research/03-regulations.md](../research/03-regulations.md) rows K16, K17, K18, K19, U13, U14, U15, U16 (access 2026-11-04) and [../strategy/05-hosting-and-data.md](../strategy/05-hosting-and-data.md). Not legal advice.

## What the research gives
| Topic | KSA | UAE |
|---|---|---|
| Law | PDPL, Royal Decree M/19 (2021), amended M/148 (2023); in force 2023-09-14, enforced 2024-09-14 (SECONDARY, Dentons/PwC/Clyde) | Federal Decree-Law 45/2021, in force 2022-01-02 (SECONDARY); executive regulations reportedly not yet issued (single source) |
| Regulator | SDAIA (https://sdaia.gov.sa, not fetched) | Not confirmed; creation of a Federal Authority for AI and Data reported 2026-06-14 (single source) |
| Transfers | Adequacy or safeguards (SCCs, BCRs, certification), minimum necessary data, risk assessment; regulation versions conflict; no adequacy list per secondary source | UNVERIFIED |
| Residency | No in-Kingdom mandate for private ERP data confirmed; NCA CCC data localisation applies to regulated entities (UNVERIFIED applicability) | No general localisation law confirmed; sector rules exist |
| Free zones | n/a | DIFC and ADGM have own regimes (not retrieved) |
| Retention | VAT/tax records: 6 years commonly cited, do not rely | 5 years VAT, 15 years real estate, 7 years corporate tax: all UNVERIFIED |

## Egypt
Data-protection law, regulator, transfers, residency, processor registration and retention: all research needed (see E5, E8, E10 in [country-matrix.md](country-matrix.md)). Nothing is assumed from KSA or UAE.

## Our roles
Tenant is controller; we are processor (DPA required, [../legal/checklist.md](../legal/checklist.md)). For our own website/sign-up data we are controller. Whether we must register with SDAIA as processor or appoint a DPO: UNVERIFIED.

## Product decisions already made (ADR-0006)
In-country hosting per tenant region; per-tenant keys and backups; export and delete per tenant; consent and DSAR tooling in the platform; breach log; audit trail.

## The cross-border AI question
Is sending tenant business or personal data to a foreign model API a cross-border transfer needing a legal basis under KSA or UAE PDPL? UNVERIFIED (counsel question 10). Interim rules:
1. Minimise: IDs and aggregates, redaction ([../security/hosting-rules.md](../security/hosting-rules.md)).
2. Gateway region routing; approved providers only; no training; minimum retention.
3. Tenant disclosure of sub-processors and AI use in privacy documents.
4. If counsel says restricted: self-hosted open-weight models for KSA tenants (trigger in [../strategy/06-model-strategy.md](../strategy/06-model-strategy.md)).
5. Do not market "your data never leaves the country" until true.

## Retention
Periods per record type and country: research needed; configurable per tenant and per country; legal hold supported; deletion on termination with documented exceptions for tax records.

## Open items
| # | Item |
|---|---|
| 1 | Acceptable transfer mechanism for hosting or AI outside KSA |
| 2 | SDAIA processor registration, DPO need |
| 3 | UAE PDPL executive regulations status |
| 4 | Breach notification deadlines and recipients |
| 5 | Retention periods per record |
| 6 | Whether analytics on the marketing site is a transfer |
| 7 | Employee data (HR module) special handling |
