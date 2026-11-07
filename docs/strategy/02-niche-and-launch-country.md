# 02 - Recommended niche and launch country

Date: 2026-11-04. Status: RECOMMENDATION. The founder said launch country can wait; this gives a default and the triggers that would flip it.

## Launch country: KSA first for customers
Reasons (evidence in research files):
- **Demand is forced and dated.** ZATCA Phase 2 now reaches essentially all VAT-registered firms; Wave 25 (SAR 187,500 threshold, integration by 2027-02-01) pulls small firms in (03-regulations; 02-market §1.5, SECONDARY).
- **Bigger target pool.** ~109k KSA vs ~58k UAE firms with 10-200 staff (ESTIMATE, 02 §1.3). The UAE count is the weaker number.
- **Arabic matters more.** Owners in KSA are more likely to want Arabic-first; our differentiator is weakest in English-first Dubai.
- **ZATCA reuse exists** (ERPGulf MIT app, 04 §4.5). UAE has no open-source e-invoicing app and needs an accredited provider partner anyway.
- **Investor fit.** Raed, Sanabil/500, STV, Shorooq are mostly Riyadh/Dubai; Raed led Wafeq (05-investors).

Why not UAE first: UAE e-invoicing is not live until 2027, dates conflict, and it depends on an accredited provider integration we do not control. UAE is the second market (July 2027 go-live wave for smaller firms is the opening).

Counter-arguments we must respect:
- A UAE entity is easy; KSA entity/licence and MISA terminology are unclear (05 §entity, UNVERIFIED). The Dubai championship prize and Hub71 both need a UAE footprint.
- Pilot A's country is unknown. **If Pilot A is in the UAE, do not force KSA for the pilot.** Pick the first paying customer's country, but build for KSA compliance first.

Recommended setup (pending lawyer): operate from a UAE entity, sell to KSA firms, host KSA tenants in-Kingdom. Whether a UAE entity may contract and invoice KSA clients, and whether we need Saudi VAT registration, is UNVERIFIED: ask counsel.

Flip triggers: Pilot A and 3 warm leads are UAE; ZATCA tooling cost exceeds the spike estimate; counsel says KSA presence is mandatory before first revenue.

## Niche: trading and distribution firms, 10-100 staff (lead hypothesis)
Profile: wholesale/import-export/distribution, 1-5 branches, credit sales, inventory, multi-currency purchases, VAT, WhatsApp-driven ordering.

Why (02 §Five implications, all hypotheses until interviews):
1. High invoice count per firm, so compliance pain is high and daily.
2. The incumbent cost is partner implementation + upgrades, not licence (SAR 45-150k year 1 vs ~SAR 11k licence).
3. The needed modules are standard (sales, purchasing, inventory, AR/AP, VAT, light HR): the engine's strongest area, so the component library can cover most of a build.
4. Accountant/VAT consultant referral channel is reachable.
5. **Pilot B (an Odoo-using ecommerce publisher) is a trading/inventory shape**, so it doubles as proof of the niche and the Odoo-migration pitch.

Second niche (hold, do not build for yet): service firms with payroll-heavy operations (facility management, manpower supply), where WPS/GOSI/Saudization matter. It needs the payroll component, which is the weakest area of the seed (HRMS Arabic 33%).

Rejected for now: retail/F&B (Foodics, Rewaa, Qoyod, POS-first vendors), clinics (regulatory interfaces), manufacturing (BOM/costing depth), e-commerce platforms as customers (Zid/Salla own that channel).

## Kill criteria (set before interviews)
Drop or change the niche if, after 25 interviews: fewer than 8 describe a current ERP/compliance pain they would pay to fix; fewer than 5 would pay at SAR 2K+/month; or the accountant veto appears in more than half.

## Making the venture math work (02-market §1.4 says SOM ~$1.8M ARR)
- Target ACV $10K+ (subscription SAR 2.5-3.5K/mo plus setup), not $4.8K.
- Show the path to a second wave: GCC (UAE, then Bahrain/Oman/Kuwait), a payments or financing line, and ecosystem add-ons (landing pages, marketing tracking).
- Investors will ask for a SOM above $10M ARR in 5 years; at ACV $10K that means ~1,000 customers, ~8% of the niche SAM (12.5k firms, ESTIMATE). Plausible only with channel partners.

## Update (2026-11-06)
Egypt is a third operating market alongside KSA and UAE (founder requirement, ADR-0015). Launch order stays KSA, UAE, Egypt; this document's KSA-first analysis is unchanged and Egypt is research needed.

## Update 2026-11-07 (founder, ADR-0024)
The launch order in this file (KSA first, UAE second, Egypt third) is superseded: phase 1 operates in KSA, UAE, Egypt and Qatar with no fixed order, because the founder's first leads are in Qatar and the founders also want Egypt in phase 1. The niche (trading and distribution) stays a lead hypothesis and the first template, not a restriction: later templates follow the leads. Qatar and Egypt facts are research needed.
