# Golden path: one trading sale (draft)

Status: proposed
Owner: eldon
Approved by: pending (the other founder checks it independently; accountant review is required before Phase 2, not before Phase 1A)

The single end-to-end scenario that Phase 0 and Phase 1A prove on the real bench and that Phase 1B asks the builder to reproduce (BPL-028; [../architecture/phased-delivery-and-lanes.md](../architecture/phased-delivery-and-lanes.md)). All data is synthetic. Every accounting expectation below is UNVERIFIED until it is run on the pinned bench and checked by someone other than the author; no accountant has reviewed it yet. Do not copy it into a customer document.

## 1. Scope
In: one company, one warehouse, one stocked item, one customer, one sale that is delivered and invoiced, the ledger and stock effects, role permissions, Arabic and English invoice output, failure and duplicate cases.
Out (later paths): payments, the purchase cycle, returns, any tax (a tax variant is path 2), multi-warehouse, manufacturing, connectors.

## 2. Starting state
| Item | Value |
|---|---|
| Company | Golden Trading Co (synthetic), single company, base currency one fixed currency, no tax on this path |
| Chart of accounts (minimal) | Bank, Accounts receivable, Inventory, Cost of goods sold, Sales, Opening equity |
| Warehouse | W1 |
| Item | ITEM-001, stocked, unit "piece" |
| Opening stock | 100 pieces at cost 10.00, posted once as the opening balance |
| Customer | CUST-001 |
| Selling price | 15.00 per piece (price list) |
| Inventory method | Perpetual (stock movements post to the ledger), moving average cost. UNVERIFIED: confirm the engine default and the setting on the bench |

Opening entry: debit Inventory 1,000.00, credit Opening equity 1,000.00.

## 3. Roles
| Role | May | May not |
|---|---|---|
| Owner | see everything; approve postings | |
| Sales | create the sales order; see prices and customers | see item cost, inventory value or the ledger |
| Warehouse | create the delivery from an order; see quantities | see prices, receivables or the ledger |
| Finance | review and post the invoice; see ledger and reports | change permissions |

Posting the invoice to the ledger is a human action (the human floor, ADR-0027). No agent is involved in this path.

## 4. Steps
1. Sales creates a sales order for 10 pieces of ITEM-001 at 15.00 for CUST-001 (total 150.00).
2. Warehouse creates the delivery for the 10 pieces from W1 against that order and submits it.
3. Finance creates the sales invoice from the delivery (10 pieces, 150.00), reviews it and posts it. The invoice must not move stock again (the stock already moved on the delivery).
4. Reports are run: trial balance, stock balance and stock value, accounts receivable.

## 5. Expected results (to be confirmed on the bench)
**Delivery** (cost 10.00 per piece by moving average): debit Cost of goods sold 100.00, credit Inventory 100.00. Stock W1: 100 to 90 pieces.
**Invoice:** debit Accounts receivable 150.00, credit Sales 150.00.

Trial balance after step 4:
| Account | Debit | Credit |
|---|---|---|
| Inventory | 900.00 | |
| Accounts receivable | 150.00 | |
| Cost of goods sold | 100.00 | |
| Sales | | 150.00 |
| Opening equity | | 1,000.00 |
| **Total** | **1,150.00** | **1,150.00** |

Tie-outs: stock value of ITEM-001 (90 x 10.00 = 900.00) equals the Inventory account; accounts receivable ageing equals the receivable account (150.00); order total, invoice preview, printed invoice, ledger and receivable report all show 150.00.

## 6. Permission checks
- Sales opening the ledger, the item cost or the stock value report is denied, in the screen, the report, an export and the chat.
- Warehouse seeing selling prices or receivables is denied the same way.
- A sales user asking the chat for cost of goods or margin gets a refusal, not a partial figure; an aggregate (total cost) is refused too.
- Everything fails closed when a role or policy cannot be evaluated.

## 7. Failure and duplicate cases
1. Submit the delivery twice (double click, retry): exactly one stock movement and one posting.
2. Interrupt between the delivery and the invoice, then recover: no duplicate, no orphan posting, the state is visible.
3. Deliver more than the stock on hand: a clear error, nothing posted.
4. Invoice more than was delivered: blocked.
5. Cancel the posted invoice: correcting entries, not edited history.
6. Discount variant: the same sale with a 10 percent document discount gives 135.00 everywhere (order, preview, printed invoice, ledger, receivable report). This catches totals that disagree between a preview and the ledger.

## 8. Documents and language
The invoice prints in Arabic and English with the same figures; a native Arabic speaker reviews the output. The print format for this path must be country-neutral (it must not depend on any single country's e-invoicing work).

## 9. Independent check (Phase 1A, E1A-2)
Someone other than the author recomputes the trial balance by hand from section 2 and compares it with the bench's reports. The other founder reviews with a different model than the author. The accountant reviews this spec before Phase 2 and signs off the live opening balances then (LEG-019). A discrepancy means the spec or the engine setting is wrong: record it, fix the cause, run again.

## 10. Open questions for the bench
- Does the pinned engine post stock to the ledger by default on delivery, or does it need the perpetual setting?
- Does invoicing a delivered order avoid a second stock movement by default?
- Which valuation method is the default for ITEM-001?
