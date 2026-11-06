# Decision log

Newest at the bottom. Format: date, decision, why, alternatives rejected, impact.

## 2026-11-04: Customer is owner-led businesses, not corporates or governments
- **Decision:** Target owner-led SMEs whose owners want AI transformation.
- **Why:** Founder decision; faster buying cycles, no procurement bureaucracy, matches chat-first UX.
- **Alternatives rejected:** Corporates and government (long cycles, entrenched SAP/Oracle).
- **Impact / follow-ups:** Niche still to choose in Phase 2.

## 2026-11-04: Middle East first, compliance non-negotiable, launch KSA and/or UAE
- **Decision:** Launch in KSA and/or UAE with full local compliance.
- **Why:** Founder decision; compliance is the moat against generic global tools.
- **Alternatives rejected:** Global-first.
- **Impact / follow-ups:** Phase 2 picks one launch country.

## 2026-11-04: Product, not software house
- **Decision:** We build the first clients ourselves, always through the platform; every build adds reusable components.
- **Why:** Investors need software margins and a real AI product.
- **Alternatives rejected:** Bespoke builds per client.
- **Impact / follow-ups:** Phase 2 defines metrics such as the share of each implementation done by the platform.

## 2026-11-04: Founders work in a cloud-hosted git repo; different models per founder
- **Decision:** Shared repo (GitHub), markdown docs and handovers in the repo; each founder may use a different AI model.
- **Why:** Both founders need access; manage token cost.
- **Alternatives rejected:** Notion as source of truth (to be verified in Phase 2).
- **Impact / follow-ups:** Remote and push setup is done by the founder, not by agents.

## 2026-11-04: No application code until Phase 2 is approved
- **Decision:** Phases 0 to 2 are docs only.
- **Why:** Founder instruction; research and challenge first.
- **Alternatives rejected:** Early prototyping.
- **Impact / follow-ups:** A technical spike is planned inside the 90-day plan (Phase 4).

## 2026-11-04: Pilot A is only a lead; Pilot B kept generic; launch country and niche deferred
- **Decision:** Pilot A has not been contacted yet. Pilot B is treated as a generic Odoo-using ecommerce publisher; Samarkand specifics are out of scope for now. Launch country and entity decided later. The brief's earlier research is treated as unverified hypotheses.
- **Why:** Founder instruction.
- **Alternatives rejected:** None.
- **Impact / follow-ups:** Phase 3 plans discovery for Pilot A from scratch; Phase 2 still recommends a niche and country.

## 2026-11-04: Phase 2 recommendations (all PROPOSED until the founder approves; details in docs/strategy/01-09)
- **D-P2-1 Seed:** Frappe Framework (MIT) + ERPNext core (GPL-3) as rigid engine, SaaS-only and undistributed; proprietary AI layer, Blueprint compiler and Arabic-first UI outside the engine behind an adapter. ERPGulf MIT app for ZATCA; not lavaloon (AGPL). HRMS only as skeleton. **Why:** avoids writing a ledger from scratch; reversible via the adapter. **Rejected:** own engine (agent's #1; slower, accounting risk), Odoo CE, Open Mercato, Twenty, NocoBase. Gated by a 2-week spike. See 04.
- **D-P2-2 Launch country:** KSA first for customers; UAE second (July 2027 wave). Entity setup pending counsel. Flip if Pilot A is UAE. See 02.
- **D-P2-3 Niche:** trading and distribution firms, 10-100 staff (hypothesis; kill criteria after 25 interviews). See 02.
- **D-P2-4 AI-native definition:** conversation compiles to a typed Blueprint; configuration not code; every change is an approved, simulated, reversible diff; scoped agents; evals as an asset. See 03.
- **D-P2-5 Moat:** compounding library + regulatory freshness + corpus, with the engine replaceable. Honest: no moat at zero clients. See 03.
- **D-P2-6 Hosting:** isolated tenant on shared in-country infra; reject VPS per client; hybrid and dedicated later. Data export and anonymised-blueprint reuse clause in contracts. See 05.
- **D-P2-7 Models:** gateway, tiered models, Arabic eval first, models hidden from customers, no self-hosting until triggers. Typical tenant inference ~SAR 200/month (assumed rates). See 06.
- **D-P2-8 Pricing:** fixed setup SAR 20-60K, per-company unlimited-user subscription SAR 2-5K/month, AI-actions budget with caps; floor for software margins ~SAR 2.5K. Hypotheses to test. See 07.
- **D-P2-9 Product discipline:** no client-specific code; autonomy-rate metric and targets; no free pilots. See 08.
- **D-P2-10 Dubai championship:** enter with a narrow new agent, effort capped at ~2 weeks; needs Dubai licence to collect. Founder to decide.
- **D-P2-11 Collaboration:** Markdown in repo is source of truth; GitHub Issues/Projects for tasks; Notion not source of truth.

## 2026-11-04: Founder will enter the Dubai Create AI Agents Championship
- **Decision:** Enter. Agent scope to be chosen (narrow, new capability, not the whole product). Founder also wants no code written for now.
- **Why:** Founder decision; cheap validation and visibility.
- **Alternatives rejected:** Skip.
- **Impact / follow-ups:** Registration closes December 2026; a working prototype is due January 2027, so code will be needed then (decide when). Dubai trade licence needed to collect a prize.
