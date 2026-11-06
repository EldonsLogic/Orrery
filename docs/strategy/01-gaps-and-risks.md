# 01 - Biggest gaps and risks in the idea

Date: 2026-11-04. Evidence base: `docs/research/01-05`. Labels: ESTIMATE / ASSUMPTION / UNVERIFIED as in the research. Blunt by design.

## Contradictions inside the brief itself
1. **"Every business function" vs two founders.** The end state is a full ERP; the launch must be one niche, 3-4 modules. If we say yes to everything, we become Odoo with a chatbot.
2. **"Full compliance, non-negotiable" vs starting at zero.** Incumbents (Qoyod, Wafeq, Zoho, Odoo) already ship ZATCA Phase 2 (01-competitors §E). We either reuse a compliance core someone else maintains, or we spend our first six months re-deriving ZATCA.
3. **"One shared multi-tenant engine" vs the seed we like.** Frappe is one database per tenant (04-open-source §4.3, detail UNVERIFIED). That is fine, even better for PDPL, but the phrase must be redefined as "one shared codebase and component library", not "one shared schema".
4. **"Unlimited users, tokens included" vs AI cost.** Inference grows with usage, not with seats. See `06-model-strategy.md`.
5. **"Product, not software house" vs "we build the first clients ourselves".** The second sentence is how the first becomes false. See `08-product-vs-software-house.md`.

## Ranked risks (highest first)
| # | Risk | Why it is real | What would change my mind | Mitigation |
|---|------|----------------|---------------------------|------------|
| 1 | **Owners do not want to "build an ERP"; they want a problem gone.** Chat-built software is our story, not their demand. | No buyer evidence exists (02-market §2 is all UNVERIFIED). Vibe-coding builders already own the "describe it" narrative (01-competitors A6). | 20-30 interviews where owners volunteer to pay for the outcome, not the novelty. | Sell "compliant and running in X weeks, changes by chat", not "build your own ERP". Lead with the pain: ZATCA, Odoo upgrade bills, Excel. |
| 2 | **Price anchor collision.** Wafeq SAR 99-199/mo, Odoo ~SAR 11k/yr for 15 users; our hypothesis is SAR 2-5K/mo (10-25x Wafeq). | 01-competitors §E3; 02-market §3. | Willingness-to-pay interviews showing owners compare us to partner retainers, not accounting apps. | Price against implementation + retainer, never against accounting apps. We cannot win below ~SAR 1.5K/mo (see 06, 07). |
| 3 | **Compliance liability.** A wrong generated invoice fines the customer and kills trust. | ZATCA signing/QR/hash chain; UAE ASP flow; both are ongoing work (03-regulations, 01-competitors §C8). | Counsel confirms which certifications we need as a vendor (03 "vendor vs client" table). | Compliance logic only in certified, versioned, frozen components; AI may not alter it. |
| 4 | **The accountant's veto.** In owner-led firms the external accountant often shortlists (UNVERIFIED). | Qoyod/Wafeq/Zoho are accountant-friendly (01 §E2). | Interviews showing owners decide without accountant input. | Accountant role/view from day one; recruit accountants as a channel. |
| 5 | **Venture scale.** SOM ~$1.8M ARR in 3 years at $4.8K ACV (ESTIMATE, 02 §1.4). | Assumptions are unsourced (60% of small firms 10+ staff; 25% adoption). | Higher real ACV or a second revenue line (payments, GCC). | See `02-niche-and-launch.md`: ACV must be $10K+ and GCC expansion must be in the story. |
| 6 | **Software-house drift.** First clients pull us into bespoke work. | Pilot B-style migrations are custom by nature. | Autonomy metrics rising per client (08). | Hard rules + metrics + contract IP clause. |
| 7 | **Ledger correctness in an AI-coded codebase.** Two founders, different models, accounting bugs are existential. | The seed recommendation avoids writing the GL for this reason (04). | Spike shows ERPNext cannot meet needs. | Keep the ledger in the mature engine; property tests; humans approve all posting logic changes. |
| 8 | **Arabic LLM quality for accounting terms and dialects.** Untested by us (01 §E6). | No evidence found either way. | Our own Arabic eval set (06). | Build the eval set first; refuse to ship flows below threshold. |
| 9 | **PDPL / hosting / cross-border LLM calls.** Not verified (03 lists rows UNVERIFIED). | Financial data of Saudi firms sent to a model API. | Lawyer reading of PDPL transfer rules. | In-region tenant hosting, minimal-context prompts, regional model endpoints where available (05). |
| 10 | **Funded locals add AI first.** Rewaa $45M, Foodics $170M+, Wafeq $7.5M (01 §E4). | They own distribution. | Their shipped (not announced) AI. | Win on breadth + compliance + onboarding speed, not on a chat widget. |
| 11 | **Our own research is thin in places.** Vendor claims, search snippets, several UNVERIFIED regulation rows. | See each file's caveats. | n/a | Re-verify before they drive scope; lawyer pass; treat numbers as ranges. |

## What is genuinely strong
- Compliance deadlines create dated, non-discretionary demand: ZATCA Wave 25 (from 2027-02-01, SECONDARY) and UAE e-invoicing (2027, dates conflict).
- Odoo's verifiable grievances (upgrade breakage, partner lock-in, partner-priced customisation) match an upgrade-safe, config-not-code design (02 §4).
- No competitor found offers Arabic conversational ERP setup (weak evidence, 01 §F2).
- Build-time token cost is trivial (06): the scarce resource is human QA, which the platform can attack.

## Top 5 things to do before spending months building
1. 20-30 owner/accountant interviews in the chosen niche (willingness to pay, who vetoes).
2. Two-week technical spike (see `04-architecture-and-seed.md`).
3. Lawyer pass on the UNVERIFIED regulation rows and the vendor-certification question.
4. Arabic eval set v0 (100 prompts) and a model bake-off.
5. Sign Pilot A as a paid pilot with an IP clause that allows anonymised blueprint reuse.
