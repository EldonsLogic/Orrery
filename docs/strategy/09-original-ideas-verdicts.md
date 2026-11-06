# 09 - Verdict on every original idea

Date: 2026-11-04. Keep / Change / Later / Reject, with reasons. None dropped silently.

| # | Idea | Verdict | Reasoning |
|---|------|---------|-----------|
| 1 | Customers choose among many AI models in chat, with cost estimate per request | **Change** (hide models; cost preview only for heavy jobs, in "AI actions"). Model choice **Later** for enterprise/dedicated tenants | Owners buy outcomes; a picker breaks evals, multiplies support and exposes our margin. Inference for a typical tenant is ~SAR 200/mo (`06`), so budgets and routing matter more than choice. |
| 2 | AI logs into the customer's current ERP/tools through a built-in browser to read data ("or not") | **Change.** Prefer API/export/read-only DB connectors (Odoo JSON-RPC/XML-RPC and CSV exports first). **Later**: browser-driven access as a fallback for tools with no API | Credentials, 2FA, ToS, PDPL and fragility risks. Owners should create a read-only service account, never share a personal login; credentials are ephemeral and never stored. Evidence on Odoo extraction details comes in Phase 3. |
| 3 | Hosting: VPS per client vs hybrid vs something else | **Change:** isolated tenant per customer on shared in-country infrastructure (default). **Reject** VPS-per-client. **Later** hybrid and dedicated instances | Margins and ops (`05`). Hybrid triggers GPL distribution issues for the engine (`04`). |
| 4 | Pricing: setup fee + subscription; per company vs per user; tokens separate or included | **Keep with changes:** fixed setup, per-company subscription with unlimited users, tokens hidden inside an "AI actions" budget with caps and overage packs | `07`. Per-seat conflicts with owner psychology; per-token scares owners; unlimited AI is a margin leak. |
| 5 | Self-hosted open-weight models (e.g. Kimi) vs Claude/GPT/Gemini APIs vs customers paying for tokens | **Later** for self-hosting (triggers in `06`). **Keep** APIs behind a gateway now. **Reject** customer-paid tokens as the default | Break-even needs hundreds of tenants; Arabic quality of open models unproven here; a gateway keeps the door open. |
| 6 | Building on open source: start from the listed repos and find better ones | **Keep, with a changed seed:** Frappe + ERPNext as engine (SaaS-only, undistributed), proprietary layers around it, ERPGulf MIT for ZATCA | `04`. Open Mercato, Twenty, NocoBase and others rejected with reasons; reusable MIT parts noted. |
| 7 | Founder collaboration: Notion vs Markdown files in the repo with clear handovers | **Keep Markdown-in-repo as the source of truth**, with GitHub Issues/Projects for tasks. **Reject** Notion as source of truth | Agents read and diff Markdown; Notion drifts from code and adds a second login and sync step. Use Notion only for non-technical notes if wanted. Protocol: `AGENTS.md`, `docs/HANDOFF.md` updated every session, decisions in `docs/strategy/decisions.md`, cross-model PR review, CI gates (Phase 4). |

## Hypotheses from the brief
| Hypothesis | Verdict |
|---|---|
| Real product = AI-led implementation: interview, owner-approved blueprint, compile to configuration, simulate a month, go live | **Confirmed, and it is the product definition** (`03`). The simulation step is the trust-builder; keep it. |
| Generate configuration on one shared multi-tenant engine, not custom code; ledger/tax/audit rigid; agents draft, humans approve | **Confirmed**, with "one engine" redefined as one codebase and component library (`04`). |
| Seed: Frappe + ERPNext + HRMS headless under our Arabic-first interface and AI layer | **Mostly confirmed** with changes: HRMS only as skeleton (Arabic 33%, no GOSI/WPS found), ERPGulf MIT for ZATCA, not AGPL lavaloon, pinned versions, 2-week spike gate. |
| Arabic completion ~89/67/33% (ERPNext/Frappe/HRMS) | **Confirmed** by measurement (04 §3). |
| Open Mercato: commercial SSO/locking/agent orchestrator, no ledger, no Arabic | **Confirmed.** Fork is an unmodified mirror. |
| Twenty: CRM only, AGPLv3, Arabic translated | **Confirmed**, plus enterprise-licensed files and an application exception. |
| NocoBase licence unclear | **Overturned:** clear and prohibits our business model. |
| n8n/NocoDB SUL; Activepieces core MIT | **Confirmed.** |
| Isolated tenant per customer, in-country first; dedicated later | **Confirmed** (`05`). |
| Gateway + Arabic eval set; frontier at build time, small at run time; no self-hosting yet | **Confirmed** (`06`). |
| Fixed setup + per-company subscription with unlimited users + AI credits; SAR 20-60K and 2-5K/mo | **Confirmed as a testing range**; floor logic in `06`-`07`. |

## Extra items I am adding
- Dubai Create AI Agents Championship (registration closes December 2026, prototype January 2027, final May 2027): **Enter with a narrow new agent** (e.g. blueprint-interview or ZATCA-ready invoice agent), not the whole product (fully commercialised products are ineligible); cap effort at ~2 weeks; need a Dubai trade licence to collect a prize (02 §5). Decision is yours.
- Hub71+ AI (Abu Dhabi relocation required, applications close February 2027) and Antler: evaluate after the spike, not before.
