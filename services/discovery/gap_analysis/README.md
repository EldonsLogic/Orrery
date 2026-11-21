# gap_analysis (DSC-006)

Deterministic comparison of a Blueprint draft with the component library. No model calls, clock or randomness. Feeds the component request pipeline (BPL-016) and the quote generator (DSC-008).

```
from gap_analysis import analyse
report = analyse(blueprint_dict, library)   # library: registry.Registry or a list of raw manifest dicts
```
`environment` (default `"sandbox"`; `"production"` needs certified or regulated) decides which components are eligible.

## Requirements read from the Blueprint
| Kind | Source | Covered when |
|---|---|---|
| `compliance` | `compliance.eInvoicing` (mode other than none) | the named `componentId` is in the library and provides a `compliance.` capability |
| `component` | `components[]` bindings | the component exists in a version inside `versionRange` |
| `entity`, `workflow`, `report` | same-named arrays | a manifest provides an artifact of the same type and ref |

Integrations, VAT, payroll and roles are not analysed (Q-340).

## Status
- `covered`: an admitted, eligible manifest provides it, in a version every binding accepts, its own `requires` are met, the binding's parameters fit the manifest and the engine target is tested.
- `partial` (configuration gap): matched, but a parameter is unknown, invalid or missing, or the manifest is not tested against the engine target.
- `uncovered`: anything else, including a draft-level manifest, an unsatisfiable or invalid range, unmet `requires`, and a rejected or malformed library entry. Uncovered non-component requirements become `component_requests` (stable `request_key`, evidence ids, `kind_hint` rigid for compliance).

Several providers: the one the item names as `implements`, then a bound component, then the lowest component id; highest version per component. Others are listed in `alternatives` with reason `duplicate_providers`.

## Output
`requirements[]` sorted by kind (compliance, component, entity, workflow, report) then ref; each has `status`, `reasons[]` (`code`, i18n `key`, `params`, `labels` ar and en), `evidence[]` (`blueprint` JSON pointer, `provenance`, `manifest` id@version), `match`, `alternatives`. `summary` has counts, `malformed_blueprint_items` and `library_entries_rejected`. Labels live in `labels.json` (ar and en, same keys and placeholders, enforced by a test).

Run: `uv run --no-project --with pytest --with jsonschema --with "pydantic>=2" --with hijridate==2.6.0 python -W ignore -m pytest services/discovery/gap_analysis -q -p no:cacheprovider`
