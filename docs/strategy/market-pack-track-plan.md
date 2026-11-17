# Market-pack track plan

Status: accepted
Owner: eldon

Implements [ADR-0026](../decisions/ADR-0026-phased-delivery-and-market-pack-track.md) and [ADR-0024](../decisions/ADR-0024-four-phase-1-markets.md): four markets (Saudi Arabia, the UAE, Egypt, Qatar), no fixed launch order, Qatar the intended first pilot, the other packs a managed parallel track in readiness order. This file fixes owner, capacity and what "right away" means. Change it by a PR; no one needs to approve a change that stays inside these rules.

## What "right away" means
A pack starts as soon as its entry conditions are true, not on a date and not behind another market:
1. Its research row is done and verified from official sources (Saudi: CMP-001 and CMP-006; Egypt: CMP-027; Qatar: CMP-030; UAE: CMP-001 rows for the UAE). Unverified rules stay `unset` in the pack.
2. The country pack framework (CMP-021) is done.
3. The owner has capacity (below).

Nothing is promised before that. A pack never waits for another market's pack, and no pack blocks the Qatar pilot.

## Owner and capacity
| Pack | Research row (owner) | Build row (owner) | Notes |
|---|---|---|---|
| Qatar | CMP-030 (eldon) | CMP-031 (partner) | Pilot is confirmed only by readiness (ADR-0024): verified research, built pack, the lead, an accountant, hosting and data-transfer position, all before real data |
| Saudi Arabia | CMP-001 (eldon) | CMP-029 with the UAE pack (partner) | ZATCA Phase 1 component exists (CMP-003); Phase 2 and the Saudi sandbox are release criteria for a Saudi pilot, not for another market |
| UAE | CMP-001 (eldon) | CMP-029 (partner) | UAE e-invoicing is a separate rule set; do not reuse Saudi rules |
| Egypt | CMP-027 (eldon) | CMP-028 (partner) | All rows start UNVERIFIED; researched before built |

Capacity rule: at most two packs are in active build at the same time (one per founder lane's builder). A third pack starts only when one of the two reaches its release checklist. Research is separate: it may run for all four at once, because it produces documents, not code. Priority when more than two are ready: Qatar first if its entry conditions are met, otherwise the pack whose research is verified first.

## Country release checklist
Every pack follows the template in CMP-032 (legal and accounting scope, e-invoicing, data processing, evidence, accountant review, operational controls). Until CMP-032 exists, a pack is not released. Common minimums, all market-independent:
- No real customer data before the pack's own review (ADR-0026).
- Every statutory rate, rule and period in the pack has an official source with URL and access date, or is `unset` and blocks the feature that needs it.
- Ledger, tax, e-invoice and payroll logic is deterministic and meets the four ADR-0031 conditions.
- Retention and deletion periods follow [data-retention.md](../security/data-retention.md) for that market once counsel has confirmed them (LEG-003).
- An accountant has reviewed the tax maths before Phase 2 (LEG-019).

## Review
Revisit this plan at each phase exit (RULES 48): which packs are active, who owns them, whether the capacity limit still fits.
