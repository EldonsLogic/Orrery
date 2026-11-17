# datasets

Status: built (DAT-002)
Owner: eldon

Synthetic trading and distribution datasets for dev hosts, demos and evals, one file per market: Saudi Arabia (`ksa.json`), the UAE (`uae.json`), Egypt (`egy.json`) and Qatar (`qat.json`). The generator is deterministic and stdlib only. Companion row: DAT-009 (a larger generator for previews) builds on this.

## Synthetic only, class C1
- Every name, number, phone, email, document and amount is invented. No real customer, supplier, person, brand or pilot data was used or looked at. Classification: **C1** (synthetic and eval data, [data classification](../../docs/security/data-classification.md) section 6). Dev hosts get synthetic data only (ADR-0018).
- Never copy real or pilot data into this folder, never edit a committed file by hand (regenerate), never use it as a template for a customer document.

## Fake identifier policy
- Tax and registration numbers are fake and use an obviously fake pattern with a reserved-looking block `99999`:
  - Saudi Arabia VAT: 15 digits, first and last digit `3` (the shape rule BR-KSA-40), then `99999`, a 4-digit serial, `9999`, `3`. Example shape: `3 99999 NNNN 9999 3`. CR numbers: `99999` plus 5 digits.
  - UAE TRN: `100` + `99999` + 4-digit serial + `999`. Egypt: 9 digits `999` + 3-digit serial + `999`. Qatar: 10 digits `99999` + 4-digit serial + `9`. The non-Saudi formats are invented for this dataset and are UNVERIFIED against the real formats.
- **These numbers are not real, but they may by chance coincide with a real number.** They must never be used outside dev, demo and eval data: not on a real invoice, not in a submission, not in a production tenant.
- Emails use only `example.com` and `example.org` (reserved, RFC 2606). Phones are `+<country code> 000 000 0NNN` (subscriber numbers starting with zero are not assignable). No IBANs, card numbers or personal IDs.
- Barcodes start with `999`. Company names are generated from invented stems; a coincidence with a real firm is possible and unintended. The Saudi tenant is the BPL-005 fixture company so the two line up.

## Totals are test expectations, not tax output
- The VAT rate per market is a **config value in each file** (`config.vat.rate_percent`: SA 15, AE 5, EG 14, QA 0). It is a synthetic test configuration, UNVERIFIED against any authority, and is passed in; the generator contains no tax logic.
- Every `expected` block (order, invoice, credit note, stock, receivables) is computed with `decimal.Decimal`: line net = quantity x price minus the line discount (rounded); subtotal; document discount (rounded) on the subtotal; VAT rounded once on the net total; total. Rounding mode `ROUND_HALF_UP` to 2 decimals, which is half away from zero (the golden path rule, ADR-0033). Money is a string with 2 decimals; quantities are integers. They are synthetic test expectations and must not be presented as tax authority output.
- `vat_unrounded` shows the unrounded VAT so a reader can see the rounding step. `SO-0007` is a rounding probe (an exact half cent in SA, AE and EG).

## The story in each file
Golden path ([spec](../../docs/specs/golden-path-trading-sale.md)): `ITEM-001`, warehouse `W1`, `CUST-001`, opening stock 100 at 10.00, price 15.00. `SO-0001` is the 10-piece sale (150.00 before VAT), `SO-0002` the 10 percent discount variant (135.00 before VAT). The golden path has no tax; here VAT is added at the configured rate, so the tax variant (path 2) can reuse the data.

Contents: tenant company, 2 warehouses, 8 roles and one user each (role ids from the [Blueprint fixture](../blueprint/fixtures/trading-distribution.blueprint.json)), 5 item groups, 4 units, 13 items, 2 price lists, 9 customers (5 normal, 4 edge cases) with credit limits, 4 suppliers, opening stock, 11 sales orders (draft, pending approval, approved, invoiced), 7 delivery notes, 7 invoices, 1 credit note, payments, and expected stock balances and receivables. Order states are the fixture's sales order workflow states. `SO-0005` is partly delivered (12 of 20) and invoiced for 12; `SO-0009` exceeds its customer's credit limit and sits in `pending_approval`.

Edge cases, all flagged in `customers[].edge_cases`: `long_name` (about 140 characters, the fixture limit), `apostrophes` (straight and typographic), `arabic_indic_digits` (Arabic-Indic digits in the Arabic name), and `bidi_control_characters` (a balanced right-to-left isolate pair and right-to-left marks, no embeddings or overrides). Format characters are written as `\uXXXX` escapes in the files so no raw bidi control character sits in the repo. Every party, item, warehouse and price list has both `name_ar` and `name_en`.

## Regenerate
From the repo root:
```
python3 -m services.datasets                 # writes services/datasets/data/*.json and manifest.json
python3 -m services.datasets --seed 7 --out /some/scratch/dir   # another seed, written elsewhere
python3 -m services.datasets --check         # exit 1 if the committed files differ from a fresh run
python3 -m pytest services/datasets/tests -q
```
Default seed `20261101`, generator version `1.0.0`. Same seed and version give identical bytes (sorted keys, fixed indent, no clock, no `random` module; integers come from SHA-256). The seed picks names, serials, quantities, cost jitter and terms; the scenario shape is fixed. Changing the generator or seed means regenerating and committing the new files and manifest together. Python 3.9 or later.

## Manifest and limits
`data/manifest.json` records the dataset name, generator version, seed, base date, total bytes and, per file, path, bytes, SHA-256, market and record counts. Each file is under 100 KB and the folder under 300 KB (tests enforce both).

## How an eval or the dev bench loads it
```python
from services.datasets.loader import load_market, load_all
sa = load_market("SA")      # verifies the SHA-256 against manifest.json, raises ValueError on a mismatch
everything = load_all()     # {"SA": ..., "AE": ..., "EG": ..., "QA": ...}
```
Or read `data/<file>.json` directly and check it against the manifest. Seeding a dev bench means mapping these records to the engine's import format, which belongs to the importer that needs it, not here. The data never names the engine. No eval-set export is shipped: `evals/sets` is a JSONL layout for prompt and expected-behaviour records (Arabic core), and the month-simulation replay format is still undefined in [evals/README.md](../../evals/README.md); the first eval that needs this data defines it.
