# Semantic layer for metrics (OPR-006)

Status: draft
Owner: eldon

Spec: [04-operate](../specs/04-operate.md) item 3. Code: `services/operate/metrics/`. Principle 6: numbers come from code, words come from the model.

## 1. What a metric is
A metric is a platform-registry entry (default, Q-669), never model output:
| Field | Meaning |
|---|---|
| `id` | Stable dotted id, `<domain>.<name>` (`sales.revenue`). An id never changes meaning; a new meaning is a new id. |
| `label_key` | i18n key with Arabic and English text (`metrics.sales.revenue`). No hard-coded strings. |
| `sources` | Event types read ([events](../../contracts/events.md)) or, later, a named engine report. A formula reads nothing else. |
| `formula` | Deterministic code. Exact `Decimal` sums, no floats, rounding once at the end. |
| `grain` | `month` (param `period=YYYY-MM`) or `as_of` (param `as_of=YYYY-MM-DD`). UTC days in v0; tenant time zone is a follow-up. |
| `dimensions` | Declared slices. None are sliceable in v0; a request with unknown params is refused. |
| `roles` | Any-of roles that may read it. The check uses the caller's verified roles only. |
| `unit` | `money` (carries a currency) or `count`. |

## 2. Money and rounding
Amounts are decimal strings in events (at most 18 integer and 6 fraction digits). A request names one currency; an event in another currency refuses (no conversion in v0). The result is rounded half-up to the currency's minor units (SAR, AED, EGP, QAR: 2). Credit notes subtract from invoices. An unknown currency refuses.

## 3. How the chat uses it
The model sees `catalog(principal)`: ids, label keys, units and grains the caller may read. It asks for `get(principal, metric_id, params)` by id. The result is a typed object (`value`, `currency`, `watermark`, `event_count`). The model may explain it in words; it never computes, adjusts or re-rounds a number, and a number it writes that is not in a result is a defect. The UI renders the value from the result, not from model text.

## 4. Permissions and tenancy
Permission is checked before any data is read, and again on every cache hit. The tenant comes from the verified principal. The event loader is not trusted: one event with a different `tenant_id` refuses the whole call. Duplicate `event_id`s count once (delivery is at-least-once).

## 5. Caching
Per tenant, keyed by metric id and canonical params, valid while the highest event `sequence` is unchanged; any new event recomputes. Caches never cross tenants. A shared cache and a TTL come with the platform cache (Q-562).

## 6. Refusal codes
`MET-001` unknown metric; `MET-002` permission denied; `MET-003` invalid params; `MET-004` tenant mismatch; `MET-005` currency mismatch; `MET-006` bad event data (malformed amount or time); `MET-007` no verified principal. Messages carry no data; customer text comes from the catalog by code. Every refusal fails closed.

## 7. v0 metrics
`sales.revenue`, `sales.order_count`, `finance.receivables_outstanding` (invoices minus credit notes minus payments, up to the end of the day). Ids match the `metric` enum of `metric.query` in contracts/tool-api.md where one exists; `sales.order_count` counts issued invoices here. `finance.receivables_outstanding` has no listed id (the contract lists `finance.receivables_aging`, a different shape), so it stays and the contract list needs it added (OPR-006 slice 2).

## 8. Assumptions and follow-ups
- Fixtures assume `document.issued` data carries `document_type`, `total`, `currency`, and `payment.created` carries `invoice_id`, `amount`, `currency`. The record-event schema does not carry these yet (Q-670).
- Definitions live in a platform registry in code; Blueprint-parameterised metrics are open (Q-669).
- Follow-ups: dimensions (customer, branch), tax-inclusive versus net revenue, engine-report sources, tenant time zones, shared cache, ar/en catalog strings, wiring into the agent runtime allow-list, report builder (OPR-008), the spec 04 test that the model never outputs an unverified number.
