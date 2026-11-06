# 07 - Pricing

Date: 2026-11-04. Every number is a hypothesis to test in interviews and pilots (Van Westendorp-style questions plus real quotes). Anchors from research: Wafeq SAR 99-199/mo (fetched, 01 §C2); Odoo Custom US$16.40/user/mo, i.e. ~SAR 11K/yr for 15 users (02 §3, VERIFIED); KSA Odoo partner implementation SAR 45-150K (02 §3, SECONDARY); costs and margins from `06`.

## Position
We are not an accounting app and must not be priced like one. We replace **implementation + partner retainer + upgrades + compliance worry**. Price against SAR 45-150K year-one partner projects, not against SAR 199/month tools.

## Structure (recommended)
1. **Fixed-price setup**, scoped by blueprint complexity, paid in milestones (blueprint approved, simulation passed, go-live):
   - Standard (one entity, 3-4 core modules, up to 5 roles, up to 3 integrations): SAR 20K
   - Plus (multi-branch, inventory, approvals, light payroll): SAR 40K
   - Complex (legacy-ERP migration, many integrations): SAR 60K+
   Pilots: paid, at ~50% of list, in exchange for case-study rights and the anonymised-blueprint reuse clause (`05`). Never free.
2. **Monthly subscription per company, unlimited named users** (owner-led firms hate seat counting; it also removes a reason to share logins):
   - Core SAR 2,000: accounting, sales, purchasing, inventory, ZATCA/e-invoicing, role views
   - Operate SAR 3,500: + HR/payroll, approvals, projects, more agents
   - Scale SAR 5,000+: + multi-entity, advanced reporting, priority support
3. **Included AI budget**, expressed as "AI actions", sized to a fixed inference cost (~$60/month, covers the typical tenant in `06`). Overage in prepaid packs at cost + ~30%. Hard monthly cap and alerts, so a runaway agent cannot eat the margin. **Customers never see tokens.**
4. **Compliance pass-through**: UAE accredited-provider e-invoicing fees shown as a separate line (cost + small margin; provider fees UNVERIFIED).
5. **Annual prepay** discount (~10%); SAR-denominated invoicing; bank transfer and mada/card.

## Why per company with unlimited users
- Matches owner buying logic and the Odoo grievance (cost grows with users).
- Risk: AI usage scales with users. Mitigation is the AI budget and fair-use clauses, not seat counts.

## Tokens: included or separate?
Included within a budget, separate beyond it. Pure pass-through scares owners (see Replit/Bolt/Agentforce metering, 01 §F7); pure unlimited is a margin leak. Model choice stays internal.

## Unit economics sketch (ESTIMATE; Standard tier)
- Subscription SAR 2,500/mo = $667; COGS ~$142; gross margin ~79% (`06`).
- Setup SAR 40K = $10.7K; human build effort 80h x ~$40 = $3.2K, margin ~70% today. Target 20h by client 10 (`08`), margin ~92%.
- ACV (subscription only) $8K; with Operate tier ~$11K. Needs the $10K+ ACV from `02` to reach venture scale.
- Do not model CAC/payback yet: no data. Collect it from the first 5 sales conversations.

## Tests to run
1. Do owners compare us to accounting apps or to partner projects? (If accounting apps, the niche or pitch is wrong.)
2. Willingness to pay at SAR 2K / 3.5K / 5K in the niche.
3. Does unlimited users matter, or would a 25-user cap be accepted?
4. Setup fee tolerance: SAR 20K vs 40K for the same outcome.

## Founder hypothesis check
SAR 20-60K setup and SAR 2-5K/month: **keep as the testing range, with the arithmetic above.** The low end of the subscription range is the floor for software margins; the founders' hypothesis is directionally sound, but only if buyers benchmark against implementation cost.
