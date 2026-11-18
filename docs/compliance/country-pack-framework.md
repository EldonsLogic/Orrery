# Country pack framework

Status: draft
Owner: partner
Related: [ADR-0015](../decisions/ADR-0015-country-packs-calendars-locale.md), [ADR-0024](../decisions/ADR-0024-four-phase-1-markets.md), [country-packs.md](../architecture/country-packs.md), [calendars-and-locale.md](../architecture/calendars-and-locale.md), [country-matrix.md](country-matrix.md)

## 1. Scope and markets
A **Country Pack** is a versioned, rigid-zone configuration bundle (`kind: rigid`) that supplies country-specific statutory metadata and company locale defaults so the rest of the platform remains country-neutral. Per [ADR-0024](../decisions/ADR-0024-four-phase-1-markets.md), phase-1 operating markets are Saudi Arabia (`SA`), the United Arab Emirates (`AE`), Egypt (`EG`), and Qatar (`QA`), with no fixed launch order. Country packs hold declarative metadata, references, and defaults only; deterministic tax, ledger, e-invoicing, and payroll maths live in separate human-reviewed engine/component code ([ADR-0031](../decisions/ADR-0031-rigid-zone-code-authorship.md)).

## 2. Pack contents and disk layout
Packs live on disk under a configured packs root:

```text
<packs_root>/
  <country_code_lower>/      # sa | ae | eg | qa
    <semver>/                # e.g. 0.1.0
      pack.json              # validated against pack.schema.json
      manifest.json          # companion component manifest (component.manifest.schema.json)
```

Every `pack.json` declares eight areas (`additionalProperties: false` throughout):

| Area | Key | Contents | Override status |
|---|---|---|---|
| Identity & status | `packId`, `componentId`, `countryCode`, `version`, `status`, `evidenceStatus`, `name` | Country ISO code, component id (`country.<code>`), semver, certification state, evidence flag, bilingual `ar`/`en` name | **Locked** |
| Chart of accounts | `coaTemplate` | `componentId`, `artifactRef`, `versionRange` pointing to the country's CoA component | **Locked** |
| Tax profile | `tax` | `vatSupported`, `taxCodesRef` (engine template/component ref, no inline tax rates or maths), `filingPeriods`, `roundingRule`, `vatNumberPattern`, `crNumberPattern` | **Locked** |
| E-invoicing | `eInvoicing` | `required`, `mode`, `authority`, `componentId`, `mandatoryDocumentLanguages`, `archiveRetentionYears` | **Locked** |
| Calendar & week defaults | `localeDefaults` | `timezone`, `calendar` (`primary`, `secondaryDisplay`), `week` (`startDay`, `weekendDays`), `workingTime` (`workDays`, `hours`, `reducedPeriods`), `fiscalYear`, `holidays` (`calendarRef`, `announcedDates`), `numberSystem`, `currency` | **Overridable** (except `holidays.calendarRef`, `currency`, and pack-locked `fiscalYear`) |
| Formats | `formats` | `currency`, `currencyDecimals`, `gregorianDateFormat`, `hijriDateFormat`, `numberSystem`, `decimalSeparator`, `thousandsSeparator` | **Locked** (`numberSystem` overridable in UI via `localeDefaults.numberSystem`) |
| Payroll / WPS hooks | `payrollHooks` | `wpsEnabled`, `wpsFormatRef`, `socialInsuranceRef`, `eosbRuleRef` (disabled/null where v1 payroll is out of scope) | **Locked** |
| Print formats | `printFormats` | `legalLayoutPrecedence: true`, `mandatoryLanguages`, `templates` (`kind`, `templateRef`, `componentId`) | **Locked** (legal layout always wins over tenant branding, [ADR-0014](../decisions/ADR-0014-theming-and-tenant-branding.md)) |

## 3. Overridable vs locked settings (fail-closed)
Each pack declares `overridesPolicy`:
- `overridablePaths`: explicit allowlist of dotted paths inside `localeDefaults` that a company profile may override (typically `timezone`, `calendar.primary`, `calendar.secondaryDisplay`, `week.startDay`, `week.weekendDays`, `workingTime.workDays`, `workingTime.hours`, `workingTime.reducedPeriods`, `fiscalYear`, `holidays.overrides`, `numberSystem`).
- `lockedPaths`: explicit denylist of non-overridable paths (`countryCode`, `packId`, `version`, `componentId`, `coaTemplate`, `tax`, `eInvoicing`, `formats`, `payrollHooks`, `printFormats`, `holidays.calendarRef`, `currency`). A pack whose `overridablePaths` and `lockedPaths` overlap fails validation.
- `constraints`: optional guardrails (`fiscalYearLocked`, `allowedFiscalYearTypes`, `allowedCurrencies`, `allowedTimezones`).

Merge semantics:
1. **Default-deny:** Any override key matching `lockedPaths` or absent from `overridablePaths` is **rejected** (`OverrideRejectedError`), never silently ignored.
2. **Deep merge for objects, whole replacement for scalars/lists:** Matches Blueprint locale resolution (`services/blueprint/validator/defaults.py`).
3. **Post-merge invariants:** Resolved `timezone` must be a valid IANA zone (`zoneinfo`), `workDays` and `weekendDays` must be disjoint, `workingTime.hours.from < workingTime.hours.to`, non-overlapping `fixed_dates` reduced periods, valid `holidays.overrides` actions (`add`, `remove`, `move`), and constraint compliance.
4. **Unknown country or missing pack:** Fails closed (`UnknownCountryError` / `PackNotFoundError`). No silent fallback to another country or hardcoded defaults.

## 4. Selection by Blueprint company profile
In [blueprint.schema.json](../../contracts/blueprint.schema.json) (`0.2.0`), `company.country` (`SA`, `AE`, `EG`, `QA`) names the country, `compliance.countryPack` (`{ id, version }`) pins the pack, and `company.locale` carries per-company overrides. Because `contracts/` is owned by `eldon`, the loader in `components/compliance/country_pack/` takes explicit input parameters (`country_code`, optional `pack_id`, `version`, `company_overrides`) rather than reading or mutating `contracts/`.

### Proposed Blueprint schema updates (pending `contracts/` review)
Raised in [open-questions.md](../open-questions.md) (`Q-147`, owner `eldon`):
1. Optional `company.countryPackSelector` (`{ packId, versionRange }`) or keeping `compliance.countryPack` as canonical with `versionRange` support for discovery-stage pack selection.
2. Delegate `company.crNumber` and `company.vatNumber` format validation from KSA-only regex (`^[0-9]{10}$`) to the selected pack's `tax.crNumberPattern` / `tax.vatNumberPattern`.
3. Enforce pack locking on `company.locale.currency` and `company.locale.holidays.calendarRef` during Blueprint validation unless unlocked by `overridesPolicy`.
4. Extend `compliance.eInvoicing.mode` and `compliance.payroll.socialInsurance` enums (or make them pack-validated strings) so `QA` and `EG` are not constrained to KSA/UAE literals.

## 5. Versioning and upgrade of packs
- Packs use semantic versioning (`MAJOR.MINOR.PATCH`):
  - **Patch (`x.y.Z`)**: non-breaking fixes (label corrections, announced holiday date additions).
  - **Minor (`x.Y.0`)**: backward-compatible additions (new optional tax code ref, new holiday year table, additional print format).
  - **Major (`X.0.0`)**: breaking regulatory or override-policy changes (new mandatory e-invoicing mode, newly locked field, CoA restructuring). `upgradePolicy.migrationRequired` must be `true` with a `migrationNote`.
- **Pinning & rollout:** Tenants pin an exact `version` in their compiled artifact. Upgrades validate stored `company_overrides` against the target pack's `overridesPolicy` (failing closed if a previously allowed field is now locked), run through canary tenants, and apply via the change-engine diff/preview/rollback path.
- **Regulatory evidence:** Pack facts follow [country-matrix.md](country-matrix.md) (`VERIFIED-OFFICIAL`, `SECONDARY`, or `UNVERIFIED` per `evidenceStatus`; no unverified regulatory claim is treated as verified).
