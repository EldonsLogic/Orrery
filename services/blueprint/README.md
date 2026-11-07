# services/blueprint

Status: draft (validator implemented, BPL-003; compiler, diff, simulator, registry, factory queue and token resolver not started)
Owner: unassigned

Purpose: Part 2 service layer. Blueprint validator, compiler (neutral form + adapter calls), simulator, registry, factory queue, branding token resolver. The change engine itself lives in [apps/engine](../../apps/engine/README.md). Spec: [02-blueprint-and-library](../../docs/specs/02-blueprint-and-library.md).

## Blueprint validator

Python package `validator/`, for contract 1 ([blueprint.schema.json](../../contracts/blueprint.schema.json) v0.1.0). Dependencies: standard library and `jsonschema` (see `requirements.txt`; `pytest` for tests).

```
validate(blueprint: dict, ctx: ValidationContext | None = None) -> Report
```

- Step 1: JSON Schema draft 2020-12 (`BP-SCHEMA-001`). The contract's custom `version` and `x-validator-rules` keywords are unknown keywords and are ignored. `date` and `date-time` formats are checked.
- Step 2: one function per `x-validator-rules` entry. Cross-checks still run when the schema step found errors, and are defensive about shapes. The validator never raises for bad input: it returns errors (fail closed). A rule that cannot run on a malformed shape reports `BP-INTERNAL-001`.
- `Report`: `ok`, `errors`, `warnings` (each an `Issue` with `code`, JSON-pointer `path`, `message`) and `adjustments` (colour proposals).
- `ValidationContext` (all optional): `registry` (component id -> list of manifests), `metrics`, `connectors` (id sets), `assets` (assetId -> record), `entitlements`, `pack_locales`, `schema_path`. Anything that needs a registry that was not supplied gives a "not checked" warning, except rule 12 (fails closed).
- `resolve_locale(blueprint, ctx)` returns `company.locale` with omitted fields filled from `DEFAULT_PACK_LOCALES` (sa, ae, eg). Those values are placeholder defaults; the country pack (CMP-021) is authoritative.

### Run

From this folder: `python3 -m validator path/to/blueprint.json [--registry DIR] [--entitlement white_label]`.
From the repo root: `PYTHONPATH=services/blueprint python3 -m validator FILE`, or `python3 services/blueprint/validator/__main__.py FILE`.
`--registry` is a folder of component manifest JSON files. Output lines look like `ERROR BP-REF-001 /entities/2/workflow: ...`, then `WARN` and `ADJUST` lines. Exit 0 when there are no errors, 1 otherwise (including unreadable input).

Tests: `python3 -m pytest services/blueprint/tests -q` (from the repo root; `tests/conftest.py` sets the import path). Test manifests are fictional and live in `tests/fixture_registry.py` as Python data.

### Rules and codes

| # | x-validator-rule (short) | Codes |
|---|---|---|
| 1 | Locale: omitted fields resolve from the pack; weekend days not in workDays; hours from < to; fixed_dates periods valid and not overlapping | `BP-LOC-001` workDays contains weekend day; `BP-LOC-002` fixed_dates period needs valid from/to, from <= to; `BP-LOC-003` hours.from not before hours.to (also in reduced periods); `BP-LOC-004` reduced periods overlap |
| 2 | Country, pack id and holiday calendar agree | `BP-CTRY-001` compliance.country differs from company.country; `BP-CTRY-002` pack id prefix; `BP-CTRY-003` holiday calendar prefix |
| 3 | Ids unique per collection; every reference resolves | `BP-ID-001` duplicate id (locations, components, entities, fields and relations per entity, workflows, states and transitions per workflow, roles, approvals, reports, integrations, select option values, reduced periods); `BP-REF-001` unresolved reference (incl. approval step roles, which is where rule 6 "steps reference roles" is checked); `BP-REF-002` metrics or connectors not checked (warning, no registry); `BP-REF-003` metric or connector not in the supplied registry |
| 4 | Every localizedText covers every locale in meta.locales | `BP-I18N-001` missing locale (found by walking the contract's `$ref`s to `localizedText`, so every position is covered); `BP-I18N-002` meta or i18n default locale not in meta.locales; `BP-I18N-003` company language not in meta.locales |
| 5 | Workflow graph | `BP-WF-001` not exactly one initial; `BP-WF-002` no final; `BP-WF-003` unreachable state; `BP-WF-004` non-final state without outgoing transition; `BP-WF-005` transition out of a final state (warning) |
| 6 | Approvals | `BP-APR-002` step orders not unique or not contiguous from 1; `BP-APR-003` selfApproval true without owner approve (see below) |
| 7 | Role scope | `BP-ROLE-001` scope value not a location of that kind; `BP-ROLE-002` no admin role; `BP-ROLE-003` no owner-function role (warning) |
| 8 | Component bindings vs registry | `BP-CMP-001` not in registry; `BP-CMP-002` no version satisfies range; `BP-CMP-003` manifest `requires` not met by listed components; `BP-CMP-004` adapter or versionSet not covered; `BP-CMP-005` not checked, no registry (warning); `BP-CMP-006` engineTarget absent (warning); `BP-CMP-007` range syntax invalid. Binding ids not listed in `components` are `BP-REF-001` |
| 9 | computed.function is provided by a bound component | `BP-FN-001` not provided; `BP-FN-002` not checked, no registry (warning) |
| 10 | Branding contrast in both themes | `BP-BRAND-001` reject (error); `BP-BRAND-002` auto-adjust (warning plus `report.adjustments`) |
| 11 | Brand assets match stored records | `BP-ASSET-001` field mismatch or record not sanitised; `BP-ASSET-002` no record; `BP-ASSET-003` not checked, no records (warning) |
| 12 | poweredBy.show=false needs white label | `BP-WL-001` (also when no context: fail closed) |
| 13 | SA e-invoicing needs Arabic documents and VAT number | `BP-EINV-001` documentLanguages lacks `ar`; `BP-EINV-002` company.vatNumber missing |
| - | Schema, internal | `BP-SCHEMA-001` schema violation or input not an object; `BP-INTERNAL-001` a rule could not run on malformed input |

### Interpretations and limits

- Rule 1: the contract has a single hours range, so "periods must not overlap" is checked as from < to, plus overlap between `fixed_dates` reduced periods. Checks run on the resolved locale, so an explicit weekend that collides with defaulted work days is caught. `ramadan` periods carry no dates and are not overlap-checked.
- Rule 6: "a role cannot approve its own submission unless selfApproval is true and the owner role holds it" is read literally: `selfApproval: true` is accepted only if some role with `function: owner` has the `approve` action on `appliesTo.entity`. `false` is always accepted.
- Rule 8: `engineRange` is a range over the engine's own versions, which the Blueprint does not state, so it is not evaluated. The check compares the adapter, and `meta.engineTarget.versionSet` against the manifest's `testedAgainst`. The registry version used is the highest one inside the Blueprint's `versionRange`. A `requires` entry with `component` needs that component listed and its resolved version inside the range; one with `capability` needs another listed component providing it, in range. The range matcher (`semver.py`) supports exact, `^`, `~`, `>=`, `<=`, `>`, `<`, x-ranges, space (AND) and `||` (OR); hyphen ranges are not supported and report `BP-CMP-007`.
- Rule 9: the manifest schema expresses provided functions as a `provides[].artifacts[]` entry with `type: function` and `ref` equal to the function id. A function is accepted if a component bound to the same entity (in its resolved version) provides it. No prefix heuristic is used.
- Rule 10: surfaces come from `validator/theme_surfaces.py` (copied from `docs/brand/tokens/tokens.json`; a test fails if they drift; docs are never read at runtime). Each colour is tested per theme against both the surface and the background token. Thresholds: `primaryColour` 4.5:1 (it is used for text and links); `accentColour` 3:1 (graphics only, per the token notes). No colour can reach 4.5:1 on both a near-white and a near-black surface, so the light and dark themes are judged separately and each failing theme gets its own proposal. Auto-adjust keeps hue and saturation, searches HSL lightness both ways in 0.5% steps up to 30 points and takes the smallest shift that passes; if none does, the colour is rejected. Not covered here: text-on-primary label colour, focus ring and distance from status hues (theming.md lists them; the thresholds there are not final).
- Rule 11: each `assetRef` (logo on light/dark, favicon asset, login background) must equal the record for its `assetId` on mediaType, bytes, sha256, widthPx, heightPx and sanitised (same value and type); the record itself must be sanitised.
- Rule 13: uses `compliance.country`.
- Metrics and connectors are only checked against registries passed in the context.
