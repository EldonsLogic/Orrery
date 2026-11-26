# services/discovery

Status: draft (template-first path started, DSC-002; interview agent started (DSC-005), mapper, gap analyser and quote not started)
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
- Registry used by the tests is the fictional fixture registry (adapter id `change_engine`, version set `set-example`); metrics are not checked (no metric registry), which gives warning `BP-REF-002`. Rule 10 reports light-theme adjustments only (`BP-BRAND-002`); dark-theme derivations of the platform colours are silent, since the token derive is authoritative there.
- Extra branches get generic names; roles are not duplicated per branch (the branch sales manager stays on the head office until the owner says otherwise).

### Not done
Interview engine and prompts, import readers (Excel, documents with OCR, connectors), source-to-Blueprint mapping, gap analysis, visual Blueprint, quote, and the pre-tenant workspace. Other templates (retail, services, contracting) do not exist.

## Connector runtime boundary (DSC-010)

`connectors/` is the framework every connector runs behind, not a connector. Offline, stdlib only, no file or network access.

| Module | Content |
|---|---|
| `connectors/model.py` | `Connector` protocol (tier, `extract`, `normalise`, `writes=False`, read-side `capabilities`), `Registry`, `RunContext`, `Limits`, `Budget`, coded refusals (`CON-001` to `CON-019`) |
| `connectors/sanitise.py`, `detect.py` | Section 3.3 steps (bidi, zero-width, tag characters; digits and confusables in a comparison copy) and the en and ar instruction-like pattern list (metric only) |
| `connectors/runner.py` | `run_connector(connector, source_bytes, ctx, sink)`: restricted call, budgets, sanitise, L3 envelope on every field (set only here), audit events, fail closed |

Tests: `tests/connectors/` (fake connectors only; requirement IDs PI-002 to PI-007 in test names). Open questions Q-90 to Q-95.

## Excel and CSV connector (DSC-011)

`connectors/tabular/` is the first real connector: tier 2 (file upload), `writes=False`, capabilities `read` and `parse`, id `discovery.tabular`. `register(registry)` adds it; `run_connector` then wraps every cell, header, comment and defined name in an L3 envelope. Stdlib only, nothing evaluated, no network, no file access.

- CSV: UTF-8 (with or without BOM), UTF-16 with BOM, else windows-1256; delimiter comma, semicolon or tab by a fixed score on the first 20 records; header row = first of the first 10 non-empty rows whose cells are all non-numeric text (a label only, A06). The encoding and delimiter used are reported as info issues.
- XLSX: hand-parsed OOXML. Refused with a coded class: `Tab001` legacy .xls, .xlsb, .ods or other formats; `Tab002` encrypted; `Tab003` zip bomb (ratio and size caps, 200 entries), nested archive, zip64, path traversal; `Tab004` DOCTYPE or ENTITY (also UTF-16 XML); `Tab005` macros; `Tab006` malformed; `Tab007` undecodable text. The runner reports an extract fault as `CON-010` plus the class name, so the code is in the reason text.
- Hidden sheets, rows and columns are emitted with `visible=false` (not model-facing unless the owner opts in via `include_hidden`) and a `hidden_sheet`, `hidden_rows` or `hidden_columns` issue (A05). Comments and defined names are L3 text.
- Formulas are never evaluated: the cached value is kept, `formula` issue. Text starting with `=`, `+`, `-`, `@`, tab or CR (plain numbers excepted) is kept and reported as `formula_like`. Dates become ISO strings only when the number format is clearly a date; other numbers stay raw.
- Budgets: rows, columns, cells and sheets are constructor limits (default 50000, 256, 200000, 100); input bytes, steps, fields and characters come from the framework `Limits`.

Tests: `tests/connectors/tabular/`. Not covered: .xls and other formats are refused, not read; pivot tables, charts, merged cells, rich-text formatting and cell styles are ignored.

## Odoo extractor (DSC-012)

`connectors/odoo/` is a tier 1 (official API, read-only) connector, id `discovery.odoo`, `writes=False`, capability `read`. Generic: no client specifics. Offline and stdlib only: the only I/O seam is an injected `Transport` (`call(model, method, args, kwargs) -> JSON`) that the platform vault supplies ready-made; this package contains no network code and never sees credentials.

- Read-only in code (PI-006): `ReadOnlyGateway` passes only `search_read`, `read`, `search_count`, `fields_get`, `name_get` and `common.version`. `ODO-002` write-style names (write, create, unlink, execute, action_, button_, private), `ODO-001` any other method, `ODO-003` model not on the configurable allow-list, `ODO-004` bad arguments (unknown keyword, `search_read` without a page limit of 1 to 500), `ODO-005` secret-like key in input, `ODO-008` transport failure (its message is dropped), `ODO-009` malformed response. The runner reports them as `CON-010` plus the class name.
- Budgets: hard page size (max 500), `max_pages`, `max_records_per_model`, `max_records_total` stop paging and report `budget_stopped_paging` (rows read versus `search_count`); the framework `Limits` and `Budget` still apply.
- Output: one entity per model; per field a label (`column_header`), a spec (type, neutral type, required, relation, selection, translate) and a mapping line, then one `cell` per record value. many2one gives the name plus `#id`, x2many an id list, `False` on non-boolean fields is empty (counted, not emitted), selection keeps the key. Arabic labels and values are data; every string is L3 via the runner; instruction-like text is flagged, never acted on. Binary fields are never fetched (`binary_not_fetched`); secret-like field names are withheld.
- Data tables in `connectors/odoo/mapping.py`: `DEFAULT_MODELS` (trading business) and `MAPPING` (source model/field to neutral name and type; the Blueprint mapping is DSC-013). Fields without a mapping are reported (`unmapped_field`, `unmapped_model`), never dropped.

Tests: `tests/connectors/odoo/` (FakeTransport, synthetic data). Not covered: any real Odoo version quirk beyond the generic shapes, domain filters, incremental sync, and the transport itself (vault-side).

## Pre-validation and quarantine (DSC-019)

`prevalidate/` runs BEFORE any replay or import of an owner's historical rows (already parsed by the tabular connector, the extractor or intake). Pure functions, stdlib only, no I/O, no model calls, deterministic. It flags dirty rows and quarantines them; it never corrects, rounds into place or adopts a stated figure.

- `normalise_arabic(text)`: comparison key for matching only (display spelling is kept): NFKC, bidi and zero-width removed, tatweel and diacritics dropped, alef forms unified, ta marbuta to ha, alef maqsura to ya, Arabic-Indic and Eastern digits to ASCII, lower-case Latin, punctuation to spaces, business words (data list `BUSINESS_WORDS`) stripped at the edges, never to empty. Hamza on waw or ya is not unified.
- `group_duplicates(names, threshold=1)`: groups by equal key, same token set, or edit distance up to the threshold (and at most a quarter of the shorter key; digit sequences must match). Connected components; canonical = most frequent display form, tie by first seen. Suggestions for owner confirmation, never merged.
- `prevalidate(dataset, config)` returns a report: findings (`PRE-` code, severity `blocking`, `needs_owner` or `info`, i18n `reason_key`, row pointers as sheet and row ids, `quarantined`), `accepted`, `quarantine` (intact copy plus SHA-256), `owner_review`, counts per code, name groups. Codes: 101 negative stock, 201 to 204 dates (unparseable, future, outside period, Hijri detected not converted), 301 to 303 line and document totals and unparseable amounts, 401 to 403 duplicates, 501 missing required, 601 to 603 quantity and price signs, 701 currency mismatch, 801 and 802 duplicate party and item names. Malformed input is refused with `PRE-E01` to `PRE-E05`.
- Defaults: line total = round(qty x price) minus discount plus VAT, ROUND_HALF_UP to 2 places, tolerance 0, compared with the stated total unrounded. Stock: receipts before issues on the same date, per item and warehouse, first negative balance only. Future-date check runs only when `today` is given in the config (no clock).
- CLI: `cd services/discovery && python3 -m prevalidate <dataset.json> --config <config.json>` (exit 0 clean, 1 quarantined rows, 2 refusal).

Tests: `tests/prevalidate/` (synthetic data only). Not covered: Hijri conversion, currency conversion, tax-rate correctness (only arithmetic), returns and credit notes as signed stock, stock moves between warehouses, fuzzy matching of phonetic or transliterated names.

## Odoo to Blueprint mapping (DSC-013)

`blueprintmap/` turns the Odoo extractor's raw extract (neutral intermediate records) into a mapping report and a draft Blueprint fragment. Pure, offline, stdlib only, deterministic; `python3 -m blueprintmap <extract.json>` prints `{report, fragment}` (exit 0 clean, 1 needs_human or conflicts, 2 coded refusal `BMP-E01..E04`).

- Data, not code: `table.py` holds the model dispositions, the neutral-name to Blueprint-target table (this fixes the vocabulary of Q-114), record checks and type compatibility. Entity and field ids come only from the trading-distribution template (`template.py`; the table is checked against it at start, fail closed); nothing is invented.
- Report lists: `mapped`, `unmapped_field`, `unmapped_model`, `needs_human`, `conflicts`, each entry with a reason code and an i18n `reason_key` (`bmp.reason.*`). A field that cannot be placed is reported, never dropped; two sources for one target and type mismatches are `conflicts` (first in table order wins).
- Fragment: `entities` (template fields trimmed to the mapped ones, provenance `imported`; each validates against `#/$defs/entity`), `locations` (warehouses), partial `company` (legal name, VAT number, base currency; only when valid), and `reference_data` (currencies, units, item groups, taxes, accounts, journals: ids and labels only).
- Rigid zone (ADR-0027): tax rates and types, account kinds, debit and credit, journals, stock quantities and posted entries are never interpreted; they are unmapped with a `*_semantics` or `posted_entries` code and listed in `needs_human` with record counts.
- Untrusted input: source text only selects nothing; names must match a strict pattern, text copied into labels is cleaned (control and bidi characters removed) and capped, limits on models, fields and records.

Tests: `tests/blueprintmap/`. Not covered: record-level value translation (select options, currencies by amount), partner role split by rank, and a combined Blueprint with workflows, roles and components (the fragment is a starting point for the owner review).

## Date tests (QA-015)

`tests/dates/test_date_properties.py`: deterministic property tests (seeded loops, no model calls, stdlib plus `hijridate` and `zoneinfo`; needs `tzdata`). Covers Hijri to Gregorian to Hijri round trip over the whole 1343 to 1500 AH table, month and year lengths, monotonic and contiguous months, refusal of out-of-range years and days, Gregorian leap years and month ends, ambiguous day/month flags, Arabic-Indic and Persian digits equal to Latin digits, weekend overrides, Hijri and Gregorian fiscal-year boundaries, and Asia/Riyadh, Asia/Dubai, Asia/Qatar and Africa/Cairo offsets and local date at midnight. Weekend, week-start and fiscal rules are not in production code yet, so the file tests the doc's rule through a small reference helper. Rules the doc marks UNVERIFIED (weekend defaults, Egypt daylight saving) are `xfail`; week start per market is undefined in the doc and is an `xfail` placeholder. Not covered: announced and company overrides, due dates, working-day functions, Ramadan hours (no code yet).

## Interview agent (DSC-005)
`interview/` asks the question list in `questions.json` in Arabic or English (language follows the owner's last message) and returns a Blueprint-draft input for `instantiate()`. Never a Blueprint; the owner approves.
- State machine: `Interviewer.start / answer / ingest_document / confirm / reject / resolve_contradiction / draft_input`. Order, retries and completion are code; the model only extracts.
- Extraction: simple answers (yes or no, an option label, one number, Arabic-Indic digits) are parsed by rules with no model call. Anything else goes to the injected `ExtractionPort.extract(request)`. Its reply is untrusted: exact shape, exact answer keys, per-type and range checks, and free-text and numeric values must appear in the owner's text, otherwise discarded and the question is asked again.
- Owner and document text is stripped of invisible characters, capped, scanned for instruction-like text (flag `injection_suspected`) and passed to the port only in `untrusted_text`. Values read from documents are `proposed` until the owner confirms.
- Flags: `uncertain` (owner does not know, low confidence; defaults from the question list are recorded as `default`), `contradiction` (a later value differs from a confirmed one; the old value is kept until the owner decides), `cross_check`, `ungrounded`, `extraction_rejected`, `budget`.
- Resume: `Session.to_dict()` JSON; `Session.from_dict()` re-validates everything (stored state is untrusted).
- Arabic question text is `unreviewed` (ADR-0033) until a native speaker reads it. Tests use fakes only: `python -m pytest services/discovery/tests/interview -q`.
