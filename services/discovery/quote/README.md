# quote (DSC-008)

Deterministic quote from a Blueprint, its gap analysis (DSC-006) and a price book. No model calls, network, randomness or file writes; the clock is the caller's `now`. Numbers come from code, words come from i18n keys (principle 6).

```python
from quote import generate_quote, default_price_book, verify_quote, quote_state
q = generate_quote(blueprint, gap_report, default_price_book(), now=aware_utc_datetime,
                   validity_days=None, discount_bp=0, expected_price_book_digest=None)
verify_quote(q)               # digest and quote id match the content
quote_state(q, now)           # valid | expired | not_yet_valid (raises QTE-TAMPER-001 if edited)
```

**A quote is always a DRAFT**: `status: "draft"`, `binding: false`, `requires_human_approval: true`. Nothing here sends or accepts it (DSC-009).

## Price book (`price_book.placeholder.json`)
PLACEHOLDER values, UNVERIFIED (Q-400); real prices are a founder decision. Strictly validated (it is untrusted data): exact keys, integers only (no float, bool, string, negative or oversized), id patterns, duplicate JSON keys and NaN refused, validity 1 to 90 days. Per market: currency and a flat VAT rate in basis points. Per currency: base platform fee (monthly), default module price (monthly), per-component overrides, one-off configuration fee, one-off build fees (`configurable`, `rigid`), AI-action allowance and overage pack. Its `id`, `status` and SHA-256 digest are recorded in the quote; `expected_price_book_digest` pins one.

## Lines
| Gap status | Quote line |
|---|---|
| base | one recurring base platform fee (unlimited users) |
| `covered` / `partial` | one recurring module line per distinct matched component (several requirements share it); `partial` adds a one-off configuration line |
| `uncovered` with a `component_requests` entry | one one-off build line by `kind_hint` (`rigid` or `configurable`) |
| `uncovered` component binding (no request) | listed in `unpriced`, quote `complete: false` (Q-403) |

Allowances (AI actions per month, overage pack) are shown, not charged. Tax is shown separately for the recurring and the one-off section. `discount_bp` (a person's choice) is a negative one-off line applied before tax.

## Money
Integer minor units everywhere; `money()` gives `{minor, currency, exponent, text}` with the currency's digits (SAR, AED, EGP, QAR 2; KWD, BHD, OMR, JOD 3; JPY 0). The only rounding is tax and discount: `Decimal` **ROUND_HALF_UP** to a whole minor unit (`1.5 -> 2`, never banker's). Any price, subtotal or total of 10^15 minor units or more, or more than 2000 lines, is refused.

## Refusals (fail closed, no partial quote)
Bad price book (QTE-PB-001), pinned digest mismatch (QTE-PB-002), gap analysis for another Blueprint id or revision (QTE-GAP-002, stale), inconsistent summary (QTE-GAP-003), unknown country (QTE-BP-002), naive clock (QTE-CLOCK-001), out-of-range amounts (QTE-RANGE-001, 002), bad discount or validity (QTE-ARG-001, 002), edited quote (QTE-TAMPER-001).

## Integrity
`digest` is SHA-256 over the canonical JSON of the quote, `quote_id` derives from it, and inputs (Blueprint, gap report, price book) are digested inside. It is tamper-evident, not a signature: approval must sign or store it (Q-401). Blueprint text in labels is stripped of control and bidi characters and capped; render it escaped.

Labels: `labels.json` (ar and en, same keys and placeholders, tested). Arabic UNREVIEWED (ADR-0033). Open questions: Q-400 to Q-405.

Run: `uv run --no-project --with pytest --with jsonschema --with "pydantic>=2" --with hijridate==2.6.0 python -W ignore -m pytest services/discovery -q -p no:cacheprovider`
