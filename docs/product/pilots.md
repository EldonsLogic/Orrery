# Pilots

Status: draft
Owner: eldon

No company details here. Pilot A has not been contacted yet. Pilot B is a generic Odoo-using e-commerce publisher. Pilots are paid (about 50% of list) in exchange for case-study rights and the anonymised-pattern reuse clause ([../strategy/07-pricing.md](../strategy/07-pricing.md), [../strategy/05-hosting-and-data.md](../strategy/05-hosting-and-data.md)). Gate G2 = one real business from discovery to live.

## Pilot A: greenfield lead (not yet contacted)
| Item | Plan |
|---|---|
| Profile hypothesis | Owner-led trading or distribution firm with spreadsheets and basic accounting; country unknown (if UAE, do not force KSA, see [../strategy/02-niche-and-launch-country.md](../strategy/02-niche-and-launch-country.md)) |
| First contact goals | Confirm pain, decision maker, accountant role, willingness to pay a paid pilot, data they can share |
| Discovery checklist | Legal entity and country; CR and VAT status; ZATCA wave or UAE e-invoicing status; branches and warehouses; products and units; price lists; customers and credit terms; suppliers and currencies; invoicing and payment habits; current tools (Excel, WhatsApp, accounting app); staff and who does what; approvals (discounts, payments); reports the owner wants; month-end process; external accountant name and needs; language preference |
| Data to ask for | Last month of invoices, customer and supplier lists, stock list, chart of accounts, bank statement (anonymised or consented), opening balances |
| Success criteria | Blueprint approved by owner; team review passed; sandbox simulation of one month within agreed tolerance; compliant invoices issued; owner uses the chat weekly; owner would pay and refer |
| Reusable output | Becomes the first "trading and distribution" template Blueprint; every component built is registered; gaps logged as candidate components |
| Investor proof | Time from first chat to live; share of build done by the platform vs by humans (autonomy rate, [../strategy/08-product-vs-software-house.md](../strategy/08-product-vs-software-house.md)); paid conversion |

## Pilot B: Odoo-using e-commerce publisher
| Item | Plan |
|---|---|
| Profile hypothesis | E-commerce and publishing business with inventory and orders, running Odoo and finding it limiting (upgrades, customisation cost, partner dependence are the known grievances, [../research/02-market-and-customer.md](../research/02-market-and-customer.md) section 4) |
| Why it matters | Proves migration pitch and the connector framework; trading/inventory shape doubles as niche proof |
| Discovery checklist | Odoo edition and version; hosting (Odoo Online, Odoo.sh, self-hosted); installed apps; custom modules and who maintains them; users and roles; integrations (store platform, payment, shipping, ZATCA module in use?); what limits them; what they must keep; volume of orders, SKUs, partners; accounting entity and fiscal year; opening-balance approach |
| Extract via API/exports | Read-only access via Odoo's external API (read-only user) or exports: partners, products and variants, units and price lists, chart of accounts, taxes and fiscal positions, warehouses and locations, open sales/purchase orders, open invoices and payments (AR/AP), stock on hand, users and groups, custom fields list, automated actions and workflows (as read), report definitions. Exact API methods and field names: research needed (spike) |
| Risks | Odoo custom modules hide logic that is not in data; credentials handling (never store owner's credentials beyond scoped read-only key; revoke after import); data volume; ZATCA history continuity (hash chain across systems: research needed) |
| Success criteria | Import with reconciliation: AR/AP, stock and trial balance match source within tolerance; one month replayed in simulation; cut-over with rollback plan; owner confirms limitations solved |
| Reusable output | Odoo connector and mapping rules (reusable for any Odoo client); "Odoo migration" Blueprint pattern; gap list |
| Investor proof | Migration time and cost vs partner quotes (SAR 45-150K year-one, UNVERIFIED partner pricing); evidence the pipeline works on a real legacy system |

## Both pilots
- Real data stays out of the repo (anonymised samples only).
- Every build runs the full gate: owner_approved -> team_reviewed -> built_in_sandbox -> simulated -> live.
- Record friction in the session log and open questions; no client-specific code.
