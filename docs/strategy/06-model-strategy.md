# 06 - Model strategy and cost math

Date: 2026-11-04. **All token prices below are ASSUMPTIONS, not verified rate cards**: replace with the providers' current published prices before using these numbers in a deck. Exchange rate SAR 3.75/USD (peg). Usage volumes are ASSUMPTIONS to be replaced by pilot telemetry.

## Strategy
1. **Gateway from day one** (e.g. LiteLLM or our own thin router; verify the gateway's licence before adoption: not checked). One interface, per-tenant budgets, caching, fallbacks, region routing, full logging.
2. **Tiering by task, not by customer choice:** frontier model for interview, mapping, Blueprint planning and diff explanation (low volume, high stakes); small/fast model for run-time chat and routine agents; deterministic code for anything that has a rule.
3. **Arabic eval set before model commitments.** 100 prompts at start, growing: Gulf and MSA dialect, mixed Arabic/English, accounting terms, Hijri dates, number formats. Model choice is the one that passes our eval at the lowest cost per task.
4. **No self-hosting yet.** Revisit on triggers below.
5. **Two-founder reality:** different models for coding is fine; the gateway and eval harness are what keep product behaviour model-independent.

## Cost math (ASSUMPTION rate card: frontier $5 in / $25 out per M tokens; mid $3 / $15; small $0.80 / $4)
**Build time, per client (once):**
- Interview ~60 turns: 1.2M in, 0.06M out. Source mapping/migration: 3M in, 0.3M out. Blueprint compile and validate loops: 2M in, 0.4M out. Simulation/test generation: 2M in, 0.3M out. Total 8.2M in, 1.06M out.
- Cost = 8.2 x $5 + 1.06 x $25 = $41 + $26.5 = **~$68**. Allow 5x for retries and long documents: ~$340 = SAR ~1,270.
- Against a SAR 20-60K setup fee, build-time inference is 2-6%. **The cost of the build is human QA time, not tokens.**

**Run time, per company per month (typical):**
- Chat: 15 users x 10 turns/day x 22 days = 3,300 turns; 6k in + 0.5k out each on the small model: 19.8M x $0.80 = $15.8; 1.65M x $4 = $6.6; **$22.4**.
- Agents (e.g. invoice/bill extraction, matching): 500 documents x 15k in + 1k out on a mid model: 7.5M x $3 = $22.5; 0.5M x $15 = $7.5; **$30**.
- Total **~$52/month (~SAR 197)**. With prompt caching and routing maybe $25-80; a heavy tenant at 3x is ~$157.
- Read this blunt: **inference alone for a typical tenant roughly equals the whole monthly price of a Wafeq Premium plan (SAR 199).** We cannot compete in the SAR 99-199 band. Free-form per-user AI in an "unlimited users" plan is a margin leak without caps (`07`).

**Gross margin by price (ASSUMPTION COGS: AI $52 + infra $40 + support $50 = ~$142/mo):**
| Subscription | USD/mo | Gross margin |
|---|---|---|
| SAR 1,000 | 267 | ~47% |
| SAR 2,500 | 667 | ~79% |
| SAR 3,500 | 933 | ~85% |
| SAR 5,000 | 1,333 | ~89% |
Software-margin target (>75%) needs roughly SAR 2.5K+/month or tighter AI cost. This is the quantitative reason the price must be anchored on outcome, not on accounting-app rivals.

## Cost controls
Per-tenant monthly AI budget with owner alerts and hard cap; routing to the cheapest model that passes eval; aggressive prompt caching; deterministic fast paths (reports, lookups) with no model; batch for non-urgent agent work; summarise histories; usage metering visible in the control plane.

## Customers choosing models (original idea)
**Change: hide models from customers.** Owners buy outcomes; a model picker adds support, breaks evals and invites blame for quality. Show a **cost preview only for heavy jobs** (bulk migration, month simulation) expressed in "AI actions", not tokens. Later: bring-your-own-key and model choice for enterprise/dedicated tenants.

## Self-hosted open-weight (Kimi and others): later, with triggers
- Rough break-even (ESTIMATE): one 8-GPU node at ~$2 per GPU-hour is ~$11.7K/month; at ~$52 API spend per tenant that is ~225 tenants before ops, redundancy (x2) and quality gap, so **realistically 450+ tenants**.
- **Triggers to revisit:** (a) >300 active tenants; (b) a PDPL/NCA reading that forbids sending data to foreign APIs for KSA; (c) a large client demanding in-premises AI; (d) open Arabic-capable models passing our eval within a few points of frontier at the task level.
- Cautions: sovereignty optics of model origin for Saudi buyers (to test, not assert); licence of each weights release; Arabic quality of specific open models is UNVERIFIED (Jais, ALLaM, Qwen families not benchmarked here).
