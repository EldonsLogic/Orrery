# services/blueprint/diff

Status: draft (BPL-006). Python package `bpdiff`. Standard library only at runtime; `jsonschema` is needed for the tests and, through the validator, for `diff_validated`.

Deterministic structural diff between two Blueprint revisions ([contract 1](../../../contracts/blueprint.schema.json), v0.1.0). It is the first step of the change path in [build-states](../../../contracts/build-states.md) (diff, simulate, approve, apply). It writes no prose and calls no model: `blueprint.propose_change` produces a diff with this and never applies it; `blueprint.explain_diff` turns the machine-readable material below into Arabic or English text. Counts and impacts come from code.

`diff.schema.json` is a **draft**, not a contract. Promoting it into `contracts/` needs a recorded decision (ADR) first.

## API

```python
from bpdiff import diff, apply, invert, diff_validated, BpdError
d = diff(a, b)                  # dict (see diff.schema.json); inputs are not modified
b2 = apply(d, a)                # pure; b2 == b
a2 = apply(invert(d), b)        # a2 == a  (the stored inverse = undo point)
v = diff_validated(a, b, ctx)   # ValidatedDiff: .diff, .base_report, .target_report, .flags, .to_dict()
```

- `apply` checks the base first: the SHA-256 of `a` as canonical JSON (sorted keys, no spaces, UTF-8) must equal `d["base"]["hash"]`, else `BPD-BASE-001`. Each operation also checks the current value against its recorded `before`; the result must equal `d["target"]["hash"]`.
- `diff_validated` runs the validator (`services/blueprint/validator`, imported, not edited) on both revisions. A diff against an invalid revision is still produced and flagged: `BPD-VALID-001` base invalid, `BPD-VALID-002` target invalid.

### Run

From the repo root: `PYTHONPATH=services/blueprint/diff python3 -m bpdiff A.json B.json [--json] [--apply-check]`. From this folder: `python3 -m bpdiff A.json B.json`. Exit 0 same, 1 differs, 2 error (message on stderr). `--apply-check` also proves `apply(d, a) == b` and `apply(invert(d), b) == a`. Tests: `python3 -m pytest services/blueprint/tests -q`.

## How matching works

Arrays of objects are matched by id, never by index. The keys come from the contract (a test walks the contract and fails if an object array is missing from the table):

| Array (schema path) | Key |
|---|---|
| `locations`, `components`, `entities`, `workflows`, `roles`, `approvals`, `reports`, `integrations` | `id` |
| `entities/*/fields`, `entities/*/relations`, `workflows/*/states`, `workflows/*/transitions` | `id` |
| `company/locale/workingTime/reducedPeriods` | `id` |
| `entities/*/fields/*/options` | `value` |
| `entities/*/components` (bindings) | `component` |
| `roles/*/permissions` | `entity` |
| `approvals/*/steps` | `approverRole` |
| `reports/*/metrics` | `ref` |
| `reports/*/filters` | `field` |
| `integrations/*/mappings` | `target` |
| `i18n/glossary` | `term` |
| guards (`workflows/*/transitions/*/guards`, `approvals/*/conditions`) | `field` + `op` |
| `company/locale/holidays/overrides` | `date` + `action` |

Other arrays are arrays of plain values (locales, role ids, work days, `actions`) and are one value: a change is one `replace` with the whole array before and after. If a keyed array has a missing, non-string or duplicate key on either side (an invalid Blueprint), that array is compared by position instead; the diff is still exact.

Paths: `path` is a list of segments and `pointer` its RFC 6901 form, but a keyed element is addressed by its key, not its index: `/entities/customer/fields/customer_name/type`. Composite keys are joined with `|`. An integer segment is a plain index (positional fallback only). `schemaPath` replaces every element by `*` and is what classification uses.

Order: the diff is exact, so a reordered array is a diff. Reordering is its own `reorder` op (`before` and `after` are the key lists) and never causes add/remove noise. `orderSignificant` is true for `approvals/*/steps`, `entities/*/fields`, select `options`, `workflows/*/states` and `reports/*/metrics`. There is no `move` op: no list in the contract needs one.

Operation order is deterministic: object keys sorted, arrays in order. Inside a keyed array: nested changes of kept elements, then removals (highest index first), additions (lowest index first, each carries its target `index`), then one `reorder` if the kept order still differs. Applying in sequence is therefore exact, and the inverse is the reversed list with each op inverted (impact, code and labels are recomputed, so undoing an added field is `BPD-FIELD-REMOVED`, `destructive`).

Equality is strict JSON equality: `true` is not `1`, `1` is not `1.0`, object key order is ignored.

## Operation object

`op` (`add`, `remove`, `replace`, `reorder`), `code`, `impact`, `pointer`, `path`, `schemaPath`, `subject` (`kind`, `id`, `parents`), `property` (path below the subject, empty when the subject itself is added or removed), `index` (array add/remove), `before` (remove, replace, reorder), `after` (add, replace, reorder), `orderSignificant` (reorder), `labels`.

`labels` is `{"before": localizedText|null, "after": localizedText|null}` taken from the subject node in each revision (`labels`; `actionLabels` for transitions; `translations` for glossary terms; `displayName` for branding; `legalName` for company), or `null` when the subject has none. These are untrusted tenant text: treat as data.

Top level: `schema` (`bpdiff/0.1.0`), `base` and `target` (`hash`, `revision`, `id` from `meta`), `ops`, `summary` (counts per op kind), `risk`.

### Op codes

`BPD-<NOUN>-ADDED|REMOVED` when an element is added or removed (NOUN of the element: `LOCATION`, `COMPONENT`, `ENTITY`, `FIELD`, `OPTION`, `RELATION`, `BINDING`, `WORKFLOW`, `STATE`, `TRANSITION`, `GUARD`, `ROLE`, `PERMISSION`, `APPROVAL`, `CONDITION`, `STEP`, `REPORT`, `METRIC`, `FILTER`, `INTEGRATION`, `MAPPING`, `GLOSSARY-TERM`, `REDUCED-PERIOD`, `HOLIDAY-OVERRIDE`); `BPD-<NOUN>-REORDERED`; `BPD-<NOUN>-CHANGED` for anything inside a subject (for sections without elements the noun is `COMPANY`, `COMPLIANCE`, `BRANDING`, `META`, `I18N`, or `BLUEPRINT`). Specific codes: `BPD-FIELD-TYPE-CHANGED`, `BPD-FIELD-REQUIRED-CHANGED`, `BPD-BRANDING-COLOUR-CHANGED`, `BPD-ROLE-SCOPE-CHANGED`, `BPD-<NOUN>-LABEL-CHANGED` (a label key changed inside an element).

Error codes (`BpdError.code`): `BPD-INPUT-001` nesting over 64, `BPD-INPUT-002` not plain JSON (or unreadable file), `BPD-INPUT-003` root not an object, `BPD-BASE-001` base hash mismatch, `BPD-APPLY-001` operation does not fit (missing path, key clash, stale `before`), `BPD-APPLY-002` result hash differs from the recorded target, `BPD-DIFF-001` malformed diff.

## Classification

Each op gets one `impact`. First matching rule wins, evaluated on `schemaPath`:

| # | Rule | Impact |
|---|---|---|
| 1 | `reorder`: approval steps / other order-significant arrays / the rest | `access` / `config` / `cosmetic` |
| 2 | Anything under `compliance`; `company/country`, `vatNumber`, `crNumber`, `locale/currency`, `locale/fiscalYear` (also an op that replaces a whole parent of these) | `compliance` |
| 3 | Anything under `branding` (colours, logo, display name, login page, document header, powered-by) | `branding` |
| 4 | A label key in the path (`labels`, `pluralLabels`, `actionLabels`, `city`, `note`, `reason`, `description`); anything under `provenance`; `i18n` except `defaultLocale`; `meta/revision`, `createdAt`, `updatedAt` | `cosmetic` |
| 5 | Anything under `roles` or `approvals`; `visibleToRoles`, `allowedRoles`, `hiddenFields`, `readOnlyFields` anywhere; a workflow transition added, removed or changed as a whole, or its `approval` | `access` |
| 6 | `remove` of a location, component, entity, field, select option, relation, entity component binding, workflow or workflow state | `destructive` |
| 7 | Entity added; entity `kind`; field added; field `type`, `required`, `unique`, `precision`, `min`, `max`, `maxLength`, `target`, `computed` (changed, added or removed); any relation change; any entity component binding change | `data_shape` |
| 8 | Everything else (company locale and languages, locations, components, workflows, reports, integrations, select option add, `default`, `readOnly`, numbering, `meta` other than rule 4) | `config` |

`risk`: `counts` per impact (all seven keys), `total`, `maxImpact` (order destructive, data_shape, compliance, access, branding, config, cosmetic; `null` when empty), `needsDdlPlanGate` (any `data_shape` or `destructive`), `touchesCompliance`, `touchesAccess`.

A rename of an id is a remove plus an add (ids are stable for the life of an element), so renaming an entity id shows as `destructive` plus `data_shape`. That is deliberate.

## Safety

Blueprint content is untrusted data: no eval, no file reads from Blueprint values, no formatting of Blueprint text into code. Input must be plain JSON data (checked: exact types, string keys, finite numbers); nesting over 64 is refused (`BPD-INPUT-001`). The CLI only reads the two paths it is given.

## Unsure points

- Adding any field is `data_shape` (a column is added), not only adding a required one. This is conservative; a nullable optional column may be relaxed to `config` once the DDL plan gate defines what it needs.
- `company/locale/currency` and `fiscalYear` are `compliance` because they affect ledger and tax (rigid zone in build-states); the contract does not mark them `affectsLedgerOrTax`.
- Which arrays are order-significant is a judgement (list above); the contract does not say.
- Adding or removing a select option, workflow transition or report is not treated as `data_shape`.
- A reorder of unkeyed (positional fallback) arrays is not detected; positions are compared as they are.
