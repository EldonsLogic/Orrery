# services/discovery

Status: draft (template-first path started, DSC-002; interview engine, mapper, gap analyser and quote not started)
Owner: unassigned

Purpose: Part 1. Interviewer, template-first drafts, connector orchestration, source-to-Blueprint mapping, gap analysis, visual Blueprint, quote. Spec: [01-discovery](../../docs/specs/01-discovery.md). Contracts: Blueprint, connector interface.

## Template library

| Path | Content |
|---|---|
| `templates/trading-distribution/blueprint.template.json` | Root of the generic trading and distribution Blueprint (company neutral). Its `entities`, `workflows` and `roles` arrays hold `{"$include": "parts/..."}` items so that every file stays under 500 lines. |
| `templates/trading-distribution/parts/` | The included arrays: `entities-1.json`, `entities-2.json`, `workflows.json`, `roles.json`. |
| `templates/trading-distribution/questions.json` | The confirm-with-the-owner list: 8 sections (company, locations, roles and approvals, sales flow, purchase flow, stock, pricing, compliance), each question in Arabic and English with the Blueprint JSON pointers it changes and a default if the owner does not know. |
| `templates/trading-distribution/questions.schema.json` | JSON Schema for `questions.json`. |
| `templates/instantiate.py` | `instantiate(template_path, answers, now=None) -> dict` and the CLI. |
| `tests/` | pytest suite (52+ tests). |

Derived from the hand-written fixture in [services/blueprint/fixtures](../blueprint/fixtures/README.md), made generic: one head office, one main warehouse and a finance department; roles, approvals, workflows (sales order, purchase order, sales invoice, stock transfer), 6 reports, 16 component bindings, Arabic and English text everywhere. Every element has provenance `template` (`trading_distribution@0.1.0`) and the Blueprint is in state `draft`. There is no company data, no tax rate and no integration (import mappings belong to the interview).

### What the template covers
Customers, suppliers, items, price lists, quotes, sales orders, delivery notes, sales invoices, credit notes, purchase orders, goods receipts, purchase invoices, payments and warehouse stock transfers; approvals for large sales orders, discounts, large purchase orders and credit notes; owner, general manager, accountant, sales rep, branch sales manager, purchasing officer, warehouse keeper and auditor roles.

### Run
From the repo root (needs `jsonschema` and `pytest`, see `services/blueprint/requirements.txt`):

```
python3 -m pytest services/discovery/tests -q
python3 services/discovery/templates/instantiate.py --country sa --name-ar "NAME" --name-en "NAME" \
    --vat-registered yes --vat-number 15DIGITS --branches 2 --out /path/outside/the/repo/bp.json
PYTHONPATH=services/blueprint python3 -m validator /path/outside/the/repo/bp.json --registry services/blueprint/fixtures/registry
```

Without `--out` the Blueprint goes to stdout; the CLI never writes into the repo by default. Python 3.9 or newer.

### Answer keys
| Key | Type | Required | Effect |
|---|---|---|---|
| `name_ar`, `name_en` | string, up to 120 characters, no braces | yes | Fills the only placeholder, `{{company.name}}`, per locale; also sets `meta.id`. |
| `country` | `sa`, `ae`, `eg`, `qa` | yes | Country, country pack id and the compliance block. Locale values are left out so they resolve from the pack. |
| `branches` | whole number 1-50 (default 1) | no | Adds `branch_N` and `wh_N` locations; location selects and the warehouse keeper scope follow. |
| `currency` | ISO 4217 code | no | `company.locale.currency`; else the pack default. |
| `vat_registered` | boolean (default false until confirmed) | no | true: VAT block and the country's e-invoicing mode; false: mode `none`. |
| `vat_number`, `cr_number` | 15 and 10 digit strings | no | `company.vatNumber`, `company.crNumber`. Saudi e-invoicing needs the VAT number (rule 13): without it the validator reports `BP-EINV-002`, deliberately not hidden. |
| `languages` | list of `ar` and/or `en`, containing `ar` | no | Default and document languages. `meta.locales` always stays `ar` and `en` because the contract requires both in every text. |

Unknown keys, values that are not strings, numbers, booleans or lists of those, and contradictions raise `InstantiationError`. The function never evals, never formats with answers, never mutates the template or the answers, and fails if a placeholder is left over.

### Limits and open points
- Everything else in `questions.json` (`fillsBy: interview`: thresholds, which documents exist, units, price lists, VAT filing period and so on) is applied later as Blueprint patches by the interview engine; `instantiate()` does not take those answers yet. The defaults shown there are the template values.
- Approval thresholds (50000 and 100000) and the 10 percent discount limit are template defaults in the company currency, not rules.
- Country values in `instantiate.py` (`COUNTRIES`: VAT rate, filing period, e-invoicing mode) are placeholders so that schema-required fields are filled until the country pack (CMP-021) exists; they are not tax logic. UNVERIFIED for the UAE, Egypt and Qatar, whose e-invoicing modes are contract placeholders (Qatar has none) and have no component in the registry, so those Blueprints carry no e-invoicing component yet. For Qatar, VAT status is UNVERIFIED: no rate is assumed, the Blueprint carries VAT as not registered, and `vat_registered: true` is rejected. Only Saudi Arabia binds `compliance.zatca_sa`.
- Registry used by the tests is the fictional fixture registry (adapter id `change_engine`, version set `set-example`); metrics are not checked (no metric registry), which gives warning `BP-REF-002`. The platform colours give an auto-adjust warning `BP-BRAND-002` in the dark theme (no single colour passes both themes).
- Extra branches get generic names; roles are not duplicated per branch (the branch sales manager stays on the head office until the owner says otherwise).

### Not done
Interview engine and prompts, import readers (Excel, documents with OCR, connectors), source-to-Blueprint mapping, gap analysis, visual Blueprint, quote, and the pre-tenant workspace. Other templates (retail, services, contracting) do not exist.
