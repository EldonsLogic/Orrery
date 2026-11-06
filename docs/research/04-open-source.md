# 04 - Open-source seed review

Access date for every URL and API call below: 2026-11-04. Evidence types: `gh api` (GitHub API), raw license files fetched from GitHub, shallow clones (frappe, erpnext, hrms; read only, nothing run) in a temporary local folder (not kept), and web search. Commit hashes are for the shallow clones. Anything not directly verified is marked UNVERIFIED. This is research, not legal advice: have counsel read the licenses before committing.

## 0. Headline findings

1. **Your fork `sayegh9/open-mercato` adds nothing.** `gh api repos/open-mercato/open-mercato/compare/main...sayegh9:main` returns `ahead_by: 0, behind_by: 13`. 0 stars and 0 forks. It is an unmodified mirror, 13 commits behind upstream (https://github.com/sayegh9/open-mercato).
2. **NocoBase is a hard no.** Its license (https://raw.githubusercontent.com/NocoBase/nocobase/main/LICENSE.txt, updated 2026-02-24) §5.4 and §7.4 forbid providing "any form of no-code, zero-code, low-code, AI platform SaaS/PaaS products to the public" using the original or modified software. That is exactly your product. Hypothesis "license unclear": overturned, it is clear and prohibitive. The repo has no LICENSE file on its `v3-develop` default branch and GitHub reports no license.
3. **Frappe Framework is MIT and now ships a native agent framework and MCP server.** Verified in the clone at `frappe/frappe/mcp/` (file header "License: MIT") and `frappe/frappe/flow/` (doctypes Flow Agent, Flow Tool, Flow Skill, Flow Knowledge Base, Flow Run, Flow Session...). Both sit on `develop` (commit 16ad066, 2026-11-04). Whether they are in the `v16.55.2` stable release is UNVERIFIED.
4. **ERPNext is GPL-3.0 (no network clause).** Running it as SaaS does not trigger source disclosure. Distributing it, or a derivative, does. Hypothesis ERPNext Arabic ~89%, Frappe ~67%, HRMS ~33%: all three confirmed by measurement (section 3).
5. **Open Mercato hypothesis mostly confirmed.** Core is MIT. The commercial `packages/enterprise` holds exactly `sso`, `record_locks`, `agent_orchestrator` plus `security` and `system_status_overlays`. No general ledger, no Arabic locale. One extra finding: the README says uncertified deployments "should not go to production" and that enterprise subscription tiers are revenue-based. That is sales positioning, not a license term. The MIT license text does not impose it.
6. **Twenty is AGPLv3 plus enterprise-licensed files plus MIT toolkit packages plus an application exception.** It is not "AGPL only". CRM only, no ledger. Arabic strings 99.9% / 100% translated.
7. **n8n and NocoDB: confirmed Sustainable Use License.** Activepieces: confirmed MIT outside `packages/ee`.

## 1. License obligations for a commercial multi-tenant SaaS

| Project | License (read from file) | SaaS obligation | Source |
|---|---|---|---|
| Open Mercato core | MIT, (c) 2025-2026 Open Mercato contributors | Keep the copyright notice. Nothing else. | https://raw.githubusercontent.com/open-mercato/open-mercato/main/LICENSE |
| Open Mercato `packages/enterprise` | Proprietary. "Not allowed without a commercial license: use in production, any commercial purpose, redistribute, modify, derive from, or generate new features based on this package." Only non-production developer evaluation is free. | Cannot be used. You would have to build SSO, locking and agent orchestration yourself. Do not let an AI assistant "reimplement from" those files either, given the "generate new features based on" clause. | https://raw.githubusercontent.com/open-mercato/open-mercato/main/packages/enterprise/LICENSE.md ; spec folder `.ai/specs/enterprise/` has the same terms (https://raw.githubusercontent.com/open-mercato/open-mercato/main/.ai/specs/LICENSE.md) |
| Twenty | LICENSE file: (1) files marked `/* @license Enterprise */` are commercial, production use needs an Enterprise subscription "for the correct number of hosts and seats"; (2) some packages are MIT (CLI, twenty-sdk, twenty-client-sdk, create-twenty-app, twenty-shared, twenty-ui, `packages/twenty-apps`); (3) the rest is AGPLv3 with a "Twenty Application Exception" (section 7 permission). | AGPL section 13: if you modify the server, you must offer the modified source to every network user. The exception lets separately built "Applications" that only talk through the published APIs, webhooks, manifest format, logic functions and front components stay proprietary. A fork of the core that merges your ERP engine into it would be AGPL. | https://raw.githubusercontent.com/twentyhq/twenty/HEAD/LICENSE (lines 1-40 and 725-750) |
| Frappe Framework | MIT, (c) 2016-2021 Frappe Technologies | Keep the notice. No other obligations. | `frappe/LICENSE` in clone, commit 16ad066 |
| ERPNext | GPL-3.0 | No AGPL network clause. SaaS use does not force disclosure. Distributing a modified copy (customer-installed, on-premise, white-label package) forces GPL for that distribution. Careful: shipping your engine plus ERPNext code into customers' hands is conveying. | `erpnext/license.txt` in clone, commit ce76c29 |
| ERPNext trademark | "ERPNext" name and logo require Frappe's permission as part of any product, company, service or domain name. Non-commercial projects only get a grant. Commercial users may refer to ERPNext descriptively but not in a product name, domain or advertising (including AdWords). | Do not brand the product "ERPNext-anything". Rename. | `erpnext/TRADEMARK_POLICY.md` in clone |
| HRMS | GPL-3.0 (`hrms/license.txt`) | Same as ERPNext. | clone commit 159548f |
| Frappe Books | AGPL-3.0 (GitHub metadata). Desktop, single-user app. | Not a server SaaS candidate. | https://github.com/frappe/books |
| Frappe Insights | AGPL-3.0 (GitHub metadata) | Network clause applies if modified. | https://github.com/frappe/insights |
| Frappe Builder | MIT (GitHub metadata) | Safe to reuse. | https://github.com/frappe/builder |
| lavaloon-eg/ksa_compliance | AGPL-3.0 (first line of `LICENSE` is "GNU AFFERO GENERAL PUBLIC LICENSE Version 3") | Frappe apps are loaded into one process; treat the app as AGPL. If you modify it and offer it over a network you must publish your modified version of that app to its users. Isolating it as an optional, separately deployed app limits blast radius. Counsel question: does your engine become a "covered work" if it dynamically loads it? Assume it can. | https://raw.githubusercontent.com/lavaloon-eg/ksa_compliance/HEAD/LICENSE |
| ERPGulf/zatca_erpgulf | MIT. Note: the file header reads "Copyright (c) 2024 ERPGulf" in `LICENSE`; the README has no license text. Hypothesis confirmed. | Safe to fork and embed. Keep the notice. | https://raw.githubusercontent.com/ERPGulf/zatca_erpgulf/HEAD/LICENSE |
| Odoo Community | LGPL-3.0 ("Odoo is published under the GNU LESSER GENERAL PUBLIC LICENSE, Version 3"). Odoo Enterprise is separate proprietary code, not in the repo. | No network clause. LGPL allows linking from proprietary code but you must allow replacement of the LGPL part and publish modifications of LGPL files if distributed. Odoo's own LICENSE text does not give extra module-exception wording (my read; counsel to confirm how "module" separation works). Odoo trademark rules: UNVERIFIED. | https://raw.githubusercontent.com/odoo/odoo/19.0/LICENSE |
| Dolibarr | GPL-3.0 | Like ERPNext. | https://github.com/Dolibarr/dolibarr (COPYING header GPLv3) |
| Apache OFBiz | Apache-2.0 | Permissive, notices only. | https://raw.githubusercontent.com/apache/ofbiz-framework/trunk/LICENSE |
| metasfresh | GPL-2.0 per `LICENSE.md` | Distribution triggers GPL. No network clause. | https://raw.githubusercontent.com/metasfresh/metasfresh/master/LICENSE.md |
| Tryton | GPL-3.0 (`trytond/LICENSE`) | Same as ERPNext. | https://raw.githubusercontent.com/tryton/tryton/main/trytond/LICENSE |
| Akaunting | Business Source License (MariaDB BSL text; Licensor Akaunting, Inc.). Additional Use Grant forbids production use beyond 2 users / 1 company / 1000 invoices, among other limits. | Cannot run commercially as a platform. | https://raw.githubusercontent.com/akaunting/akaunting/HEAD/LICENSE.txt (first 15 lines read; full conversion date not read) |
| Invoice Ninja | Elastic License 2.0 | "You may not provide the software to third parties as a hosted or managed service." Direct ban. | https://raw.githubusercontent.com/invoiceninja/invoiceninja/HEAD/LICENSE |
| NocoBase | NocoBase License Agreement (not OSI). §5.2 no removing branding except top-left logo; §5.4 and §7.4 no "no-code, zero-code, low-code, AI platform SaaS/PaaS" to the public, including with a paid commercial license; §7.3 no selling developer tools built on it. | Prohibited for your business model, even licensed. | https://raw.githubusercontent.com/NocoBase/nocobase/main/LICENSE.txt |
| n8n | Sustainable Use License 1.0; files with `.ee.` are under a separate Enterprise License. | Confirmed: internal business use only, cannot be sold or hosted as a service to others (SUL text; I read the header and structure, not every clause). | https://raw.githubusercontent.com/n8n-io/n8n/HEAD/LICENSE.md |
| NocoDB | Sustainable Use License, updated 2026-01-29, applies to `master` and `develop`. | Same as n8n. Hypothesis confirmed. | https://raw.githubusercontent.com/nocodb/nocodb/HEAD/LICENSE.md |
| Activepieces | MIT for everything outside `packages/ee/` and `packages/server/api/src/app/ee`. EE directory under a commercial subscription license. | Core and pieces usable under MIT. Do not copy EE. Hypothesis confirmed. | https://raw.githubusercontent.com/activepieces/activepieces/HEAD/LICENSE ; EE license in `packages/ee/LICENSE` |
| Medusa | MIT except Enterprise Edition materials listed in `ENTERPRISE-LICENSE.md` | Commerce only. | https://raw.githubusercontent.com/medusajs/medusa/HEAD/LICENSE ; https://raw.githubusercontent.com/medusajs/medusa/develop/ENTERPRISE-LICENSE.md |
| Hasura graphql-engine | Apache-2.0 (GitHub metadata); Hasura v3 DDN is a separate product, UNVERIFIED which parts are open. | Metadata-engine pattern only. | https://github.com/hasura/graphql-engine |
| Beancount / Fava | Beancount GPL-2.0; Fava MIT | Beancount is single-file plain text accounting, not multi-tenant DB. GPL-2.0 library. | https://github.com/beancount/beancount ; https://github.com/beancount/fava |
| Formance Ledger | No LICENSE file in the repo tree (checked `git/trees/main?recursive=1`); GitHub reports none. License is UNVERIFIED. | Do not adopt until the license is pinned down in writing. | https://github.com/formancehq/ledger |
| Blnk Finance | Apache-2.0 (`LICENSE.md`) | Permissive. Ledger/balance engine, not a double-entry chart-of-accounts product. | https://raw.githubusercontent.com/blnkfinance/blnk/main/LICENSE.md |
| Lambda ERP | Apache-2.0 (GitHub metadata) | 41 stars, prototype. | https://github.com/lambdadevelopment/lambda-erp |
| Axelor Open Platform | GitHub reports "other"; license text not read, UNVERIFIED. | - | https://github.com/axelor/axelor-open-platform |

Key rule of thumb for your model: AGPL/GPL code that stays server-side but is modified is a problem only for AGPL (network) or for anything you distribute. MIT, Apache and LGPL pieces are the safe base. ELv2, SUL, BSL and NocoBase's agreement are non-starters.

## 2. Activity snapshot (GitHub API, 2026-11-04)

| Repo | Stars | Last push | Latest release | Contributors |
|---|---|---|---|---|
| frappe/frappe | 11,051 | 2026-11-04 | v16.55.2 (2026-11-04) | ~1,089 |
| frappe/erpnext | 40,922 | 2026-11-04 | v15.124.5 (2026-11-04) | ~958 |
| frappe/hrms | 9,018 | 2026-11-04 | v15.64.8 (2026-11-04) | ~279 |
| frappe/books | 5,007 | 2026-10-02 | - | - |
| frappe/insights | 1,033 | 2026-11-04 | - | - |
| frappe/builder | 2,466 | 2026-11-04 | - | - |
| open-mercato/open-mercato | 1,905 stars, 484 forks | 2026-11-04 | v0.9.0 (2026-10-09), pre-1.0 | ~161; at least 100 commits in the last 30 days |
| sayegh9/open-mercato (fork) | 0 | 2026-11-03 | mirror, 13 behind | - |
| twentyhq/twenty | 60,426 | 2026-11-04 | twenty/v2.55.0 (2026-11-03) | ~791 |
| odoo/odoo | 55,539 | 2026-11-04 | `19.0` branch head 2026-11-04; a `20.0` branch exists | - |
| Dolibarr | 7,831 | 2026-11-04 | 24.0.1 (2026-09-07) | - |
| Apache OFBiz | 1,148 | 2026-11-04 | - | - |
| metasfresh | 2,463 | 2026-11-04 | - | - |
| Tryton (monorepo) | 240 (mirror) | 2026-11-02 | - | - |
| Akaunting | 10,276 | 2026-11-04 | 3.3.0 (2026-10-27) | - |
| Activepieces | 25,368 | 2026-11-04 | - | - |
| n8n | 209,549 | 2026-11-04 | - | - |
| Medusa | 37,079 | 2026-11-04 | - | - |
| lavaloon-eg/ksa_compliance | 93 | 2026-10-27 (last commit 2026-10-23) | 0.62.0 tag; latest GitHub release 0.7.0 is older, tags are the real cadence | ~12 |
| ERPGulf/zatca_erpgulf | 64 | 2026-10-26 | v3.0.1 (2026-07-22) | ~8 |

Source for all rows: `gh repo view <repo> --json ...` and `gh api repos/<repo>/releases/latest`, 2026-11-04. Contributor counts are approximate (Link-header page counts).

## 3. Arabic / RTL completeness (measured)

Method: parsed `.po` files, counted non-empty `msgstr` over total non-header `msgid`, excluding fuzzy. The counting script is not kept in the repo (it only parsed the files).

| Item | Translated / total | % |
|---|---|---|
| ERPNext `erpnext/locale/ar.po` | 10,979 / 12,370 | **88.8%** (hypothesis ~89%: confirmed) |
| Frappe `frappe/locale/ar.po` | 6,009 / 9,026 | **66.6%** (hypothesis ~67%: confirmed) |
| HRMS `hrms/locale/ar.po` | 746 / 2,252 | **33.1%** (hypothesis ~33%: confirmed) |
| Twenty front `ar-SA.po` | 5,691 / 5,698 | 99.9% |
| Twenty server `ar-SA.po` | 3,102 / 3,102 | 100% |
| Odoo 19 `base` ar.po | 6,569 / 6,569 | 100% |
| Odoo 19 `account` ar.po | 3,165 / 3,180 | 99.5% |
| Odoo 19 `sale` ar.po | 857 / 864 | 99.2% |
| Odoo 19 `l10n_sa_edi` ar.po | 182 / 210 | 86.7% |
| Dolibarr `ar_SA` (line count proxy: `main.lang` 1,445 vs en 1,448; `bills.lang` 784 vs 785) | - | ~99.8% by keys present; does not catch strings left in English |
| Open Mercato | locales are `de, en, es, ko, pl` only (74 files each) | **0%** Arabic (hypothesis confirmed) |

Caveats: translated is not the same as good. Twenty and Odoo percentages come from crowd or vendor workflows; I did not read quality. RTL layout: Frappe has RTL asset bundles (`assets-rtl.json` handling in `frappe/utils/__init__.py`, line 994, plus RTL SCSS), so desk RTL exists and is mature. Twenty RTL at app level: UNVERIFIED (I only found `dir="rtl"` in UI component stories and docs; check in a browser). Odoo RTL is mature and widely deployed in the Gulf: UNVERIFIED by me beyond the translations.

Why this matters: Arabic-first owners chatting in Arabic means the AI must generate labels and messages in Arabic. For an engine you own, that is your own i18n layer regardless. HRMS at 33% is the real gap for payroll screens.

## 4. Per-candidate deep review

### 4.1 Open Mercato (user fork `sayegh9/open-mercato`)
- **Fork delta:** none (ahead 0, behind 13). Use upstream, not the fork, or re-sync. https://github.com/sayegh9/open-mercato
- **What it is:** TypeScript monorepo, "AI-Engineering Foundation Framework", multi-tenancy, RBAC, events, `AGENTS.md`/`CLAUDE.md` conventions for coding agents. v0.9.0, 1.9k stars. https://github.com/open-mercato/open-mercato
- **Modules in core (tree listing, 2026-11-04):** auth, directory (tenants/orgs), customers, catalog, sales, wms, workflows, business_rules, entities (custom entities), query_index, translations, dictionaries, webhooks, scheduler, search, `ai-assistant` package (MIT), data_sync, integrations (Stripe, InPost, Akeneo), plus many channel packages. https://github.com/open-mercato/open-mercato/tree/main/packages
- **Accounting:** `sales/data/entities.ts` defines orders, quotes, shipments, returns, `SalesInvoice`, `SalesCreditMemo`, `SalesPayment`, `SalesPaymentAllocation`, `SalesTaxRate`, `SalesDocumentSequence`. No accounts, journals, ledger or fiscal periods. **No general ledger: hypothesis confirmed.** No payroll, no HR beyond `staff`/`planner`. Multi-tenant: yes (directory module). Multi-company/entity consolidation: no.
- **Commercial only:** `packages/enterprise` = `agent_orchestrator`, `record_locks`, `sso`, `security`, `system_status_overlays`. Hypothesis confirmed.
- **Compliance:** none for ZATCA/UAE found in tree (search for zatca/fiscal/ledger names returned nothing relevant).
- **AI/metadata fit:** good. Custom entities, workflows, business rules, an MIT MCP/AI-assistant package, and repo conventions designed for agents. Weakness: pre-1.0, young, a single-vendor company (Open Mercato sp. z o.o.), and the commercial layer targets exactly the AI features you want (agent orchestrator).
- **Verdict:** reuse parts / study the module and spec conventions. Do not seed from it for an ERP: you would build the ledger, tax, localization and Arabic yourself, and you would sit next to a vendor selling the agent layer.

### 4.2 Twenty
- **What it is:** TypeScript (NestJS + React) CRM with a mature metadata engine (object-metadata, field-metadata, flat-entity caches, agents, MCP server metadata modules under `packages/twenty-server/src/engine/metadata-modules/`), workflows, AI agents, an app platform (SDK, front components, logic functions). https://github.com/twentyhq/twenty
- **License exact obligations:** section 1. Enterprise-marked files unusable in production without subscription; AGPL network clause on the rest; Application Exception allows proprietary apps that interact only through the published APIs/SDK. So the clean pattern is "your ERP as a separate Twenty Application", not "fork the core".
- **Accounting depth:** none (CRM objects: people, companies, opportunities). No GL, no payroll. Per-workspace schema multi-tenancy: yes.
- **Arabic:** 99.9-100% strings; app RTL UNVERIFIED.
- **Fit:** the best-looking open metadata engine for AI generation (objects and fields are data, plus an agent runtime), but you would be extending a CRM and living under AGPL plus a vendor with an enterprise tier that can shift the line.
- **Verdict:** reuse ideas, or MIT packages (`twenty-ui`, `twenty-sdk`, `twenty-shared`). Do not seed from it. Hypothesis "CRM-only AGPLv3" is mostly right, with the three additions above.

### 4.3 Frappe Framework (MIT)
- **What it is:** Python + JS metadata-driven framework. DocTypes (JSON) define schema, forms, lists, permissions, workflows. Clone count: ~368 framework doctype JSON files; ERPNext has ~791.
- **License:** MIT. Cleanest license of any serious candidate with real ERP behind it.
- **AI/metadata suitability:** strongest of the group. Everything is declarative JSON plus hooks, ideal for "AI generates configuration". `frappe/automation_engine`, `frappe/flow` (agents, tools, skills, knowledge base, memory, sessions), `frappe/mcp` (tools: discover, documents, methods), `frappe/studio` (visual app builder) all exist on `develop` at commit 16ad066. Frappe's own `AGENTS.md` and `skills/` folder are written for coding agents.
- **Multi-tenancy model (the big trade-off):** Frappe runs one site per tenant with its own database (bench). That is isolation-by-database, not a single shared multi-tenant engine with a tenant id column. At thousands of tenants this is operationally heavy (migrations per site, per-DB connections). Frappe Cloud exists as the reference operator. This directly conflicts with your "one shared engine" premise; plan for it. (Source: framework architecture, `frappe/` directory layout and my knowledge; no repo file quoted, so treat as UNVERIFIED in detail.)
- **Arabic:** 66.6% strings, RTL assets present.
- **Stack friction:** Python/MariaDB or Postgres, Redis, own bench tooling.
- **Verdict:** seed the framework layer (see ranking).

### 4.4 ERPNext (GPL-3.0) and HRMS (GPL-3.0)
- **Accounting depth (from clone):** `erpnext/accounts/doctype` includes `gl_entry`, `journal_entry`, `payment_ledger_entry`, `period_closing_voucher`, `fiscal_year`, `accounting_dimension`, `cost_center`, `bank_reconciliation_tool`, `exchange_rate_revaluation`, `finance_book`, `budget`, `dunning`, `ledger_merge`, `ledger_health_monitor`. Reports include `balance_sheet`, `profit_and_loss_statement`, `cash_flow`, `trial_balance`, `consolidated_financial_statement`, `consolidated_trial_balance`. Real double-entry GL, multi-company, consolidation, multi-currency. Also stock, manufacturing, assets, subcontracting, projects, selling, buying, POS.
- **Payroll (HRMS):** `hrms/payroll/doctype` has `salary_slip`, `salary_structure`, `payroll_entry`, `gratuity`, `income_tax_slab`, `additional_salary`, `employee_benefit_*`. Gratuity helps UAE EOSB-style logic. I found no WPS/Mudad/GOSI code (grep on `hrms/` returned nothing, but the grep had a shell glob error, so treat as UNVERIFIED and recheck).
- **GCC regional:** ERPNext core regional folder has `united_arab_emirates` (utils.py) and doctypes `uae_vat_settings`, `uae_vat_account`. No Saudi folder: KSA VAT and ZATCA come from third-party apps.
- **Verdict:** reuse as reference/behavioral spec for accounting logic and for GCC rules. GPL-3 means do not copy into a proprietary engine you distribute. As a pure SaaS you can run it unmodified, but you cannot make it *your* engine without GPL obligations if you ever ship it.

### 4.5 ZATCA / UAE compliance apps
- **lavaloon-eg/ksa_compliance:** AGPL-3.0 confirmed. Features per README: ZATCA Phase 1 and Phase 2, simplified and standard invoices, onboarding wizard, automatic ZATCA CLI setup, resend/rejection handling, live and batch modes, multi-company, multi-device, sandbox, QR and XML embedded, compliance check log. Frappe `>=15,<17`. Last commit 2026-10-23, tag 0.62.0. https://github.com/lavaloon-eg/ksa_compliance
- **ERPGulf/zatca_erpgulf:** MIT confirmed. Phase-2 clearance and reporting, credit/debit notes, CSR generation, QR, legacy credit notes, a profit-margin-method skip flag. Frappe `>=14,<17`. Latest release v3.0.1 (2026-07-22), last push 2026-10-26. https://github.com/ERPGulf/zatca_erpgulf
- **Both are tied to Frappe/ERPNext DocTypes.** The reusable part for another engine is the logic (XML build, signing, hash chaining, CSR flow, API calls), and only the MIT one can be lifted freely. Coverage claims are the apps' own; I did not run them against ZATCA's sandbox. UNVERIFIED for fitness against the current ZATCA spec.
- **ZATCA phase timing:** Wave 24 (deadline 2026-06-30) is passed; revenue-band descriptions conflict between sources; Wave 25 headline (threshold SAR 187,500, deadline 2027-02-01) UNVERIFIED. https://www.cleartax.com/sa/zatca-wave24-einvoicing-in-saudi-arabia ; https://www.vatupdate.com/2026/07/09/zatca-phase-2-wave-24-integrate-by-30-june-2026/ . Practical consequence: the market for SMEs with Phase-2 needs is expanding now.
- **UAE e-invoicing:** Ministerial Decision 244 of 2025, PINT AE format, 5-corner model through accredited service providers; voluntary pilot from 2026-07-01; large businesses (AED 50m+) implement by 2027-01-01, others 2027-07-01 (sources disagree on ASP appointment dates; no official page checked). https://www.banqup.com/resources/blog/uae-confirms-phased-e-invoicing-mandate-rollout ; https://ecosio.com/en/blog/the-uae-e-invoicing-mandate/ . No open-source UAE e-invoicing app found. You need an ASP partner either way.
- **Odoo:** `addons/l10n_sa_edi` and `l10n_ae` ship in the Community repo as LGPL-3 (manifest `'license': 'LGPL-3'`), a point for Odoo; completeness of Odoo's ZATCA Phase 2 relative to the other two is UNVERIFIED. https://github.com/odoo/odoo/tree/19.0/addons/l10n_sa_edi

### 4.6 Odoo Community (LGPL-3)
- 55k stars, daily commits, Arabic ~99-100%, KSA/UAE localization in the open repo, strong RTL in practice (UNVERIFIED by me). Accounting in Community covers invoicing, journal entries, chart of accounts, taxes, payments. The full "Accounting" app (`account_accountant`, advanced reports, bank sync UI) is Enterprise. I could not fetch that manifest from the Community repo, which is consistent but not proof.
- Not metadata-first like Frappe (Python models plus XML views, though also declarative). Odoo SA has an Enterprise upsell and strong incentive to resist SaaS resellers. Odoo's licensing history (LGPL since v18 for Community, previously also LGPL) is not something I re-verified.
- **Verdict:** the only mainstream ERP with a weakly copyleft license, which makes it the best "real ERP" base if you refuse GPL. You will still rebuild or license the Enterprise-only pieces.

### 4.7 Others (brief)
- **Dolibarr** (GPL-3): PHP, large module ecosystem, ar_SA ~99.8% keys. Accounting is weaker than ERPNext/Odoo (no deep multi-company consolidation). Not metadata-driven. Not a seed.
- **Apache OFBiz** (Apache-2.0): permissive, deep (accounting, manufacturing) but Java/Ofbiz entity XML, dated UX, 1.1k stars. Considered a reference; not for an AI-native SaaS.
- **metasfresh** (GPL-2): Java/Spring, German-market focused. No.
- **Tryton** (GPL-3): clean modular design, real double-entry, but small community and Python/XML views. A reference for accounting design.
- **Akaunting / Invoice Ninja:** licensing blocks hosting. No.
- **NocoBase:** no, per section 0. **NocoDB / n8n:** no (SUL). 
- **Activepieces:** MIT core, usable as a workflow/automation layer for your tenants. Strong candidate for "automations" part (not an ERP).
- **Medusa:** MIT with EE carve-out. Commerce only.
- **Hasura-style metadata engines:** Apache-2.0 graphql-engine is a pattern/reference for metadata to API, but you would still own business logic.
- **Ledger engines:** Beancount (GPL-2.0) and Fava (MIT) are single-user plain text. Formance Ledger has no discoverable license (UNVERIFIED), single Raft group, programmable ledger. Blnk (Apache-2.0) is a balance/transaction ledger for fintech flows, not a chart-of-accounts ERP ledger. For an owned engine, a Postgres double-entry schema with a Blnk/Medici-like approach is straightforward. Medici (Node, MongoDB, MIT? ) UNVERIFIED, not checked.
- **AI-native ERPs and agent frameworks:** Lambda ERP (Apache-2.0, 41 stars, prototype). Noviz AI for ERPNext and community MCP servers exist (https://discuss.frappe.io/t/free-and-open-source-ai-agent-source-code-for-erpnext/164219). Axelor claims agentic features, license UNVERIFIED (https://axelor.com/agentic-erp/). None is mature. Frappe's built-in `flow`/`mcp` is the strongest first-party signal.

## 5. Ranked recommendation

Assumption: you want to own the engine (proprietary, multi-tenant, AI-generated configuration) and ship KSA/UAE compliance quickly.

1. **Build your own thin engine; use Frappe as a design reference and MIT pieces only; port ERPGulf's MIT ZATCA logic.** Highest effort, cleanest legal and architecture position. Blunt trade-off: you reimplement a GL, tax and payroll core (months, and accounting bugs are expensive) but you own everything, one shared multi-tenant schema, no copyleft contamination, and you control Arabic from day one. Use ERPNext/Tryton as the accounting spec (read, do not copy).
2. **Seed on Frappe Framework (MIT) and ERPNext/HRMS as separate, unmodified or lightly-extended GPL apps (SaaS-only, never distributed).** Fastest path to a working ERP with Arabic (ERPNext 88.8%) and a ready metadata model, plus a native agent/MCP layer. Trade-offs: GPL-3 applies to ERPNext/HRMS (fine for pure SaaS, a trap if you ever ship on-premise); the AGPL ZATCA app forces disclosure of your modifications to that app (use the MIT ERPGulf one); site-per-tenant database model contradicts your "one shared engine" idea and costs ops at scale; HRMS Arabic at 33%; you inherit Frappe's DocType constraints and a "Frappe-looking" product; ERPNext trademark forces a rename; `flow`/`mcp` maturity unverified.
3. **Odoo Community (LGPL-3) as base.** Better license for proprietary extension than GPL, Arabic ~99%, KSA/UAE localizations in the open repo. Trade-offs: advanced accounting is Enterprise-only (my inference), single-tenant per database like Frappe, Odoo SA is the dominant commercial owner and will not welcome a competing SaaS builder, and the XML/Python stack is less friendly to LLM-generated config.
4. **Open Mercato core (MIT) + build the ERP modules.** Right DNA (AI-conventions, multi-tenant, MIT) and a real tenant model, but no ledger, no Arabic, young (v0.9), and the vendor sells SSO, locks and an agent orchestrator separately. You would build accounting, tax, payroll, i18n and RTL on a pre-1.0 base. Reasonable only if you want its TypeScript conventions.
5. **Twenty as a front-end/metadata platform with an ERP "Application" on top.** Interesting for CRM parts and Arabic UI strings, but AGPL core plus enterprise-licensed files and CRM-only data model.
6. **Do not use:** NocoBase (license forbids your business), n8n/NocoDB (SUL), Invoice Ninja (ELv2), Akaunting (BSL).

Reusable standalone parts regardless of seed: Activepieces core (MIT) for automations, Frappe Builder (MIT), `twenty-ui` (MIT), ERPGulf `zatca_erpgulf` (MIT) for ZATCA logic, Blnk (Apache-2.0) as a ledger primitive.

## 6. What I did not verify

- The ZATCA apps were not run; ZATCA phase coverage is their README claim.
- Frappe `flow`/`mcp` presence in the stable v16 release, and their maturity.
- WPS/Mudad/GOSI support in HRMS (grep error; recheck).
- Odoo Enterprise-only accounting split, Odoo Phase-2 ZATCA completeness, Odoo trademark rules.
- Formance, Axelor licenses; Medici.
- Twenty RTL at app level.
- Akaunting BSL change date and grant details beyond the first 15 lines; the full text of n8n's SUL.
- ZATCA Wave 25, UAE ASP deadlines (third-party sources only).
- Frappe site-per-tenant detail is from general knowledge and the repo layout, not a quoted file.
