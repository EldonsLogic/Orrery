# ADR-0056: Golden-path engine mapping, complete unmapped list and engine-authoritative computed fields

Status: Proposed
Owner: eldon
Approved by: pending

## Context
The golden-path engine mapping example (contracts/examples/engine-mapping-golden-path.json, ADR-0030) listed no `unmapped` fields, and mapped `sales_invoice.outstanding_amount` as a plain field although the Blueprint computes it from `total_amount` and `paid_amount`. The purchasing mapping (BPL-034, ADR-0055) already follows the stricter rules. Plan row BPL-035.

## Decision
Example version 0.1.0 to 0.2.0 (0.x minor; the schema is unchanged, the example now carries data the schema already allowed).
- Every Blueprint field of a mapped entity is either mapped or listed in `unmapped` with a reason (36 fields).
- A Blueprint-computed field is mapped only with `computed.authority: engine`. `outstanding_amount` needs `paid_amount`, which needs the payment entity, so both move to `unmapped` until the payment path is mapped.
- Existing engine field names stay (unit_price to rate and the rest, verified by the partner's bench run). The notes on the two `unit_price` fields require the bench to check the discount path (rate versus price_list_rate).

## Alternatives rejected
- Add a computed block for outstanding_amount with a payment input: the payment entity is not mapped, so the inputs would not exist.
- Rename unit_price to price_list_rate: contradicts the verified bench run.

## Consequences
The two completeness checks added by BPL-034 widen from the purchasing example to all examples once BPL-034 merges (one line). ERP-022 should record the discount-path result on the bench.

## Supersedes
none
