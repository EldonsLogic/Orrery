# Country packs

Status: draft
Owner: eldon

A **Country Pack** is a certified, rigid-zone component bundle for one operating country. It carries everything that differs by country so that the rest of the platform stays country-neutral. Operating countries and launch order: **KSA, then UAE, then Egypt**. Egypt's regulations are UNVERIFIED (see [regulations research](../research/03-regulations.md)); no Egypt pack is started before its legal basis is checked.

## What a pack contains

| Area | Content | Notes |
|---|---|---|
| Tax | VAT rates, categories, exemptions, filing periods, rounding rules | Deterministic code, never AI-written |
| E-invoicing | Authority integration (KSA: ZATCA via the MIT ERPGulf app; UAE and Egypt: their regimes, UNVERIFIED), document types, status handling | `regulated` certification level |
| Holiday calendar | Public holidays as rules (fixed and Hijri-linked) with an announced-dates table | Id `<country>.holidays`; see [calendars-and-locale](calendars-and-locale.md) |
| Work week | Default weekend days, work days, working hours, reduced-hours rules such as Ramadan | Defaults only; the company overrides |
| Payroll rules | Social insurance, end-of-service, wage-protection files | Not v1 scope; pack ships with payroll empty and flagged |
| Document templates | Tax invoice, credit note, statements with legally required layout and languages | Legal layout wins over tenant branding ([theming](theming.md)) |
| Languages | Required document languages, default UI locale, glossary seeds | KSA tax invoices require Arabic content |
| Number and currency formats | Currency, decimals, digit shapes, separators, VAT number and registration number patterns | Feeds Blueprint validation |
| Defaults for `company.locale` | Timezone, calendars, fiscal year type, number system | Every omitted locale field resolves here |

## Relation to the component manifest and compiler
- A pack is a component with `kind: rigid` and id `country.<code>` (for example `country.sa`), whose `provides` lists the artifacts above and whose `requires` pulls in sub-components (for example `compliance.zatca_sa`, `calendar.holidays_sa`). It follows the [manifest schema](../../contracts/component.manifest.schema.json) and lifecycle in [component-library](component-library.md).
- Packs touch tax and the ledger, so certification is at least `reviewed` and `regulated` where an authority is involved.
- The Blueprint references the pack in `compliance.countryPack` (`id`, `version`). The Blueprint validator checks that `company.country`, `compliance.country` and the pack id agree.
- **Compiler order:** (1) resolve the pack version; (2) merge pack defaults with the Blueprint's `company.locale`, field by field (Blueprint wins); (3) validate the merged result against pack constraints; (4) emit engine configuration for the pack's components first, then the rest; (5) store the resolved locale with the compiled artifact so later pack upgrades do not silently change behaviour.
- Pack upgrades (for example a new VAT rate or holiday table) are shipped once for all tenants of that country through the canary path in [engine-adapter](engine-adapter.md). A tenant stays on its pinned pack version until the upgrade is promoted.

## Override rules
1. **Company locale overrides pack defaults** (weekend days, hours, fiscal year, calendars, number system), within pack constraints.
2. **Holidays**: the company can add, remove or move days via `locale.holidays.overrides`; each override is audited with reason. Overrides never change the pack.
3. **Rigid zone is not overridable**: tax rates and rules, e-invoicing behaviour, mandatory document content, mandatory document languages and legal layout cannot be changed by the Blueprint. A request to do so is a component request or a pack release.
4. **Branding** never overrides legal layout ([theming](theming.md)).
5. **Fiscal year**: the company may choose; the pack may restrict (for example where a tax year is fixed) and says so in its constraints.
6. A pack field marked `affectsLedgerOrTax` can only change through team review.

## Failure modes and tests
- Pack missing or incompatible with the engine version set: Blueprint cannot reach `built_in_sandbox`.
- Company country differs from pack country: validation error.
- Each pack ships tests: tax golden cases, e-invoicing sandbox, document golden PDFs (Arabic shaping), holiday and working-day cases, locale default resolution.

## Open questions
1. Egypt: e-invoicing regime, tax rules, data-residency rules (all UNVERIFIED).
2. UAE: e-invoicing regime and timeline (UNVERIFIED).
3. Whether packs ship as one component each or split by area (tax, calendar, documents) with a thin bundle manifest.
4. Who maintains packs after launch (regulatory watch process; owner per pack).

Plan IDs: ERP (pack components), CMP (compliance evidence), BPL (resolution and validation), QA (golden tests).
