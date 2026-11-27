# Open-source tools for module gaps (LEG-006 research)

Status: draft
Owner: eldon

Research only, not legal advice. Access date for every source: **2026-11-27**. Sources are numbered `[Sn]` and listed in section 14 with full URLs. Labels: **CONFIRMED** (read from the primary source or the GitHub API today), **WIDELY HELD** (commonly reported, not re-read today), **INFERENCE** (our reasoning), **UNVERIFIED** (not checked or could not be checked). GitHub numbers are API snapshots from 2026-11-27. Contributor counts were not measured (the API returns them only in headers that this tool cannot read): UNVERIFIED for every row.

Inputs not read: ADR-0076 (module list, branch `gov-078-module-scope`), ADR-0080 and the AGPL forbidden table (PR #400) and `docs/research/gpl-saas-boundary.md` are not in this checkout, and this session had no git access. The rules below are applied as the brief states them: AGPL, SSPL, BSL and source-available licences rejected by default; GPL only inside the engine, never conveyed, never for payroll or zakat logic; our business logic lives in our own services. Gaps are the ten in the brief, not checked against ADR-0076.

## 1. Bottom line

Four gaps have a good permissive pick: **Chatwoot** (MIT core) as a separate inbox service, **MJML + GrapesJS** (MIT, BSD-3) for email rendering and editing, **dnd-kit + FullCalendar standard + SVAR React Gantt core** (MIT) for boards, calendars and Gantt, and **Apache Superset** (Apache-2.0) if we need a BI layer. Payments orchestration is weak: **Juspay Hyperswitch** (Apache-2.0) has no Moyasar, Tap, HyperPay or PayTabs connector in its source tree today, so we would write those adapters ourselves either way; thin Python adapters in our own service are the cheaper path. **We found no open-source corporate zakat engine** (ZATCA zakat base) that meets our rules; the only Frappe zakat app is AGPL. **We found no permissive Gulf payroll library** (GOSI, Mudad, UAE SIF); the free options are Odoo modules (AGPL or LGPL) or paid apps. Zakat and payroll file logic stay ours to build, deterministic and in our services. Marketing automation has no clean pick: Mautic is GPL-3.0 (PHP), listmonk is AGPL, Dittofeed's multi-tenancy is closed source. For POS, every Frappe POS front end we checked is GPL-3.0 inside the engine. "Not found in our search" is not proof that none exists.

## 2. Summary table

Build time saved is a rough INFERENCE in engineer-weeks, against building the same scope from scratch.

| # | Gap | Best pick | Licence | Fit | Verdict | Time saved (INFERENCE) |
|---|---|---|---|---|---|---|
| 1 | Omnichannel inbox | Chatwoot (community, no `enterprise/`) | MIT outside `enterprise/` | Ruby service over API; our React UI or its dashboard | Consider (strong) | 12 to 20 wk |
| 2 | Email builder and render | MJML (render) + GrapesJS with MJML preset (editor); React Email for system mail | MIT, BSD-3, MIT | Embedded JS libraries | Adopt MJML and React Email; consider GrapesJS | 6 to 10 wk |
| 3 | Email sending | Bring your own provider; Postal only if self-hosting is required | Postal MIT | Ruby service | Consider later (BYO first) | 0 now; 3 to 6 wk if self-host |
| 4 | Payments orchestration | Own thin adapters; Hyperswitch as option | Hyperswitch Apache-2.0; gateway SDKs MIT or none | Rust service vs Python adapters | Reject Hyperswitch for now | 0 to 2 wk |
| 5 | Boards, timeline, calendar | dnd-kit, FullCalendar standard, SVAR React Gantt core | MIT; FullCalendar premium is commercial | Embedded React | Adopt | 6 to 10 wk |
| 6 | Zakat | None found that meets rules | (frappe-zakat AGPL) | n/a | Build ourselves | 0 |
| 7 | Gulf payroll files | None found that meets rules; HRMS gratuity rules for UAE EOS | HRMS GPL-3.0 (in engine) | Our service for files and maths | Build ourselves | 0 to 1 wk |
| 8 | POS front end | Deferred; POS Awesome forks are GPL-3.0 | GPL-3.0 | Inside engine (Vue) | Reject for now (CMP-050 open) | n/a |
| 9 | ZATCA and UAE helpers | ERPGulf (already used); phax peppol-uae for PINT AE checks | MIT; Apache-2.0 | Java service for validation | Consider phax for tests | 1 to 3 wk |
| 10 | Marketing automation | None clean; GrowthBook core for A/B | GrowthBook MIT outside `enterprise/` | TS service | Consider GrowthBook; reject Mautic, listmonk | 2 to 4 wk (A/B only) |
| 11 | Other: BI, e-sign, rich text | Superset; Tiptap; e-sign none | Apache-2.0; MIT; Documenso and DocuSeal AGPL | Service; embedded | Consider; adopt; reject | varies |

## 3. Gap 1: omnichannel inbox

**ERPNext core.** No shared inbox for WhatsApp, Instagram, Messenger or SMS (INFERENCE from the module list of ERPNext v15; not re-read today). Frappe Helpdesk and Frappe CRM are **AGPL-3.0** [S30, S31] CONFIRMED: rejected. `frappe_whatsapp` reports no SPDX licence (NOASSERTION), last push 2026-08-04 [S32] CONFIRMED; licence text UNVERIFIED.

**Chatwoot** [S1 to S6]
- Licence: CONFIRMED. MIT Expat for everything outside `enterprise/`; `enterprise/` needs a paid seat-based licence for production [S2, S3b]. GitHub SPDX reads NOASSERTION because of the split [S1].
- Paid tiers (self-hosted): custom roles, SLA policies, SSO, audit logs and Captain AI are paid; sources disagree on which tier [S5] UNVERIFIED in detail. Our assignment logic can live in our service over the API, so we need no paid feature (INFERENCE).
- Stack: Ruby on Rails, Postgres, Redis [S1] (language CONFIRMED; stack WIDELY HELD). Integration: separately deployed service, called over its REST and Platform APIs; our React screens or its own dashboard behind our gateway.
- Channels: website, Facebook, Instagram, WhatsApp (Cloud, Twilio, 360Dialog), SMS (Twilio, Bandwidth), email, Telegram, Line, TikTok, API [S4] CONFIRMED.
- Arabic/RTL: vendor says the widget and agent dashboard support RTL and Arabic [S6] (vendor claim); test before relying on it.
- Multi-tenancy: accounts within one install; Platform APIs create and manage accounts and users on self-hosted installs [S7] CONFIRMED. Isolation strength between accounts: advisory GHSA-x288-jh8j-348c (2026-07) was a cross-account resource transfer [S3] CONFIRMED, so one shared install per region is a real tenancy risk (INFERENCE).
- Health: 40,684 stars, pushed 2026-11-27, releases v4.20.1 (2026-11-20), v4.20.0, v4.19.x, v4.18.0 (2026-09-18): roughly monthly [S1, S3a] CONFIRMED. Four published advisories, including a critical SQL injection (2025-01) and a high one (2026-05) [S3] CONFIRMED.
- Production users: not sourced (UNVERIFIED).
- Covers: channels, shared inbox, assignment, canned replies, contacts. We still build: link to ERP customers, AI drafting through our gateway, our own UI if we hide the product, tenancy wrapper.
- Risks: vendor moves features into `enterprise/`; the engine-invisibility rule applies to it too (its name must not show to customers) (INFERENCE); Ruby is a new runtime for us.
- **Verdict: consider (strong).** Best-covered channel set at MIT; run one install per region, or per large tenant, and keep `enterprise/` disabled.

Others checked: Rocket.Chat (MIT outside `ee/` and `apps/meteor/ee/`) [S8] CONFIRMED, chat-first, omnichannel features partly in `ee/` (UNVERIFIED); consider only if Chatwoot fails. erxes: **AGPL-3.0** with `-ee` plugins and an anti-competing-SaaS clause [S9] CONFIRMED: reject.

## 4. Gap 2: email builder and rendering

**ERPNext core.** Frappe has Email Templates, Newsletters and Email Campaign with a rich-text editor; no drag-and-drop block builder (INFERENCE, not re-read today).

| Tool | Licence | Health | RTL | Verdict |
|---|---|---|---|---|
| MJML | MIT [S10] CONFIRMED | 18,308 stars; v5.4.1 2026-09-10, v6.0.0-alpha.1 2026-10-09 [S10, S11] | Root `dir` attribute and section `direction="rtl"` per repo docs [S12] (secondary index, UNVERIFIED on the official page) | Adopt (render in a Node step or via `mrml` in Rust) |
| GrapesJS core | BSD-3-Clause (`packages/core/LICENSE`) [S13] CONFIRMED; SPDX NOASSERTION at repo root | 26,437 stars; v0.23.9 2026-11-03, releases every few weeks [S14] | UNVERIFIED | Consider; the editor; vendor also sells a commercial Studio SDK (WIDELY HELD) |
| React Email | MIT [S15] CONFIRMED | 20,015 stars; pushed 2026-11-27 | `dir="rtl"` on the HTML element is plain JSX (INFERENCE) | Adopt for system mail (code templates, not user-built) |
| Easy-Email editor | MIT [S16] CONFIRMED | 2,990 stars; last push 2026-08-13; no GitHub releases [S16, S17] | UNVERIFIED | Reject for now: slow, small; the vendor sells a Pro edition (WIDELY HELD) |

Integration: embedded JS in `web/app` for the editor; MJML compile in a small Node or Rust step in our service; templates stored per tenant. Still to build: template library in Arabic and English, merge fields from ERP data, i18n, tokens, preview. Unlayer and Beefree are proprietary (WIDELY HELD): excluded.

## 5. Gap 3: email sending and deliverability

**ERPNext core.** Sends through a configured SMTP account; no MTA, IP warm-up or bounce analytics (INFERENCE).

- **Postal**: MIT [S18] CONFIRMED; Ruby; 16,986 stars; 3.5.0 (2026-11-20), 3.4.0 (2026-11-16), 3.3.7 (2026-06-03) [S19] CONFIRMED; two advisories, one high (2026-03) [S20] CONFIRMED. Has organisations and mail servers per org (WIDELY HELD). Self-hosting means dedicated IPs, reputation, warm-up and abuse handling: an operations job, not code.
- **KumoMTA**: Apache-2.0, Rust, 591 stars [S21] CONFIRMED. High-volume MTA, no tenant UI. Consider only at scale.
- **Stalwart**: GitHub API reports no licence [S22]; it is reported as AGPL-3.0 plus a proprietary enterprise licence (WIDELY HELD, UNVERIFIED today). Excluded.
- **Verdict:** bring-your-own provider first (tenant's own SMTP or a provider account), behind an adapter in our service. Gulf-region availability of providers: UNVERIFIED. Revisit Postal only if a data-residency rule forces in-region sending.

## 6. Gap 4: payments orchestration

**ERPNext core.** Payment Request and Payment Gateway doctypes; the MIT `frappe/payments` app [S29] CONFIRMED adds global gateways (Stripe, PayPal, Razorpay and others, WIDELY HELD). No Gulf gateway in it (UNVERIFIED).

- **Juspay Hyperswitch**: Apache-2.0, Rust, 45,933 stars, releases every two to three weeks (v1.131.0 2026-11-25) [S23, S24] CONFIRMED. Six advisories published 2026-11-05, including forged webhook status for unsigned connectors (high) and SSRF [S25] CONFIRMED. The connector folder on `main` has `checkout`, `noon`, `amazonpay`, `mpgs`, `etisalat`, `aci`, `stripe`, but **no `moyasar`, `tap`, `hyperpay`, `paytabs` or `payfort`** [S26] CONFIRMED (folder listing, read in three parts). A vendor marketing page lists HyperPay as an integration [S27] UNVERIFIED in code. HyperPay is reported to run on the ACI/OPPWA platform, so the `aci` connector might reach it (INFERENCE, UNVERIFIED).
- **Gateway SDKs.** Moyasar: server SDKs (python, node, ruby, php, dotnet) are **archived** (MIT); active ones are mobile and a Medusa plugin [S28] CONFIRMED. Tap: MIT mobile card SDKs; no Python or Node server SDK seen in the visible listing [S28a] CONFIRMED (partial listing). PayTabs: the `paytabscom` org returned 404 [S28b]; SDKs and licences UNVERIFIED. HyperPay SDK licences: UNVERIFIED.
- **Verdict:** reject Hyperswitch for now (a heavy Rust and Postgres stack that does not cover the four gateways; webhook-trust advisories touch money). Build one small Python adapter per gateway on their REST APIs in our service, behind one internal interface. Revisit Hyperswitch if we add many global gateways or card vaulting. Card data handling (PCI scope) needs its own security review (INFERENCE).

## 7. Gap 5: boards, timeline and calendar

**ERPNext core.** Projects and Tasks with Kanban, Gantt (frappe-gantt) and Calendar views in Desk (WIDELY HELD). Desk is hidden from customers (ADR-0016), so we need React views over the same data.

| Library | Licence | Health | RTL | Verdict |
|---|---|---|---|---|
| dnd-kit | MIT [S33] CONFIRMED | 17,833 stars; pushed 2026-10-31 | UNVERIFIED | Adopt for boards |
| Pragmatic drag and drop (Atlassian) | Apache-2.0 [S34, S35] CONFIRMED | 12,802 stars; pushed 2026-11-26 | UNVERIFIED | Consider (alternative) |
| FullCalendar standard | MIT for non-premium plugins; premium (resource timeline, scheduler) is commercial, or AGPLv3 for qualifying projects [S36, S37] CONFIRMED | 20,797 stars; pushed 2026-11-12 | `direction: 'rtl'` built in, documented for Arabic [S38] CONFIRMED | Adopt standard only; never install premium plugins |
| SVAR React Gantt | MIT core; PRO edition is paid (critical path, baselines, auto-scheduling, working calendars, export) [S39, S40] | 220 stars; pushed 2026-11-17 | UNVERIFIED | Consider; test RTL first |
| frappe-gantt | MIT [S41] CONFIRMED | 6,163 stars; last push 2026-06-18 | UNVERIFIED | Consider (plain JS, not React) |
| Schedule-X | MIT [S42] CONFIRMED | 2,614 stars | UNVERIFIED | Consider (calendar alternative) |

DHTMLX Gantt and Bryntum are GPL or commercial (WIDELY HELD): excluded. Still to build: views bound to our API, tokens and themes, i18n, keyboard and accessibility, RTL mirroring tests.

## 8. Gap 6: zakat

**ERPNext core.** No zakat module (INFERENCE; an integrator article says the zakat base needs custom work [S43]). Plan rows CMP-013 and CMP-025 cover it.

Found: `lavaloon-eg/frappe-zakat`, **AGPL-3.0**, 5 stars, last push 2025-05-04 [S44] CONFIRMED: rejected. Personal zakat calculators (OpenZakat, zakatrs in Rust, ZakatFlow which is AGPL-3.0) [S45] target individuals, not the ZATCA corporate zakat base; their licences and accuracy UNVERIFIED. None implements ZATCA's zakat base or declaration as far as we found. ZATCA publishes the rules and guidelines [S46].

**Verdict: build ourselves**, deterministic, in our service, with a Saudi accountant's test cases. Zakat logic may not be GPL or AGPL by the brief's rule. Not found in our search is not proof that none exists.

## 9. Gap 7: Gulf payroll (GOSI, Mudad/WPS, UAE SIF, end of service)

**ERPNext core.** Frappe HRMS (GPL-3.0, in the register) has payroll, salary structures and Gratuity Rules; at setup it can add three standard UAE gratuity rules (limited and unlimited contracts); no Saudi default seen [S47] CONFIRMED for UAE, UNVERIFIED for KSA. No GOSI or SIF file output (INFERENCE).

Found: no permissive standalone library for GOSI, Mudad or UAE SIF. Odoo modules exist (Cybrosys `uae_wps_report` AGPL-3 or LGPL-3 by version; others LGPL-3 or proprietary OPL-1, often paid) [S48] (listing data, UNVERIFIED in code); Open HRMS GOSI is AGPL-3 [S49]. A commercial ERPNext GOSI and Mudad app exists, licence unknown [S49a] UNVERIFIED. Odoo code would not run in our stack anyway.

**Conflict to flag:** any GPL Frappe payroll app loads inside the engine, so its maths would sit inside the GPL process. That conflicts with ADR-0080 (business logic in our services) and with the brief's rule that payroll logic is never GPL. **Verdict: build ourselves**: GOSI rates, WPS/Mudad and SIF file writers and the Saudi end-of-service maths in our Python service, reading payroll results from the engine over the API. File specs must come from MOHRE, Mudad and GOSI official documents (UNVERIFIED here; CMP-015, CMP-016).

## 10. Gap 8: POS front end

**ERPNext core.** Has a POS page and POS Invoice (WIDELY HELD). Hidden Desk means a customer-facing POS screen is needed later.

- POS Awesome (ucraft): **GPL-3.0**, last push 2024-08-12: unmaintained [S50] CONFIRMED.
- POS-Awesome-V15 (defendicon): GPL-3.0, 121 stars, pushed 2026-11-25, Vue and Vuetify [S51] CONFIRMED.
- ERPGulf POS-Awesome-KSA: GPL-3.0, 2 stars, last push 2026-01-14; README claims Saudi integration and ZATCA Phase 2 [S52] CONFIRMED (claim is the vendor's, not tested). ERPGulf also lists GPos, an offline POS backend [S53] UNVERIFIED.
- Offline QR before clearance is a forum claim [S54] UNVERIFIED.

**Verdict: reject for now.** POS is deferred; all options are GPL Vue apps inside the engine, outside our React stack. When CMP-050 starts, identify the Saudi POS app and check ZATCA simplified-invoice rules from ZATCA directly.

## 11. Gap 9: ZATCA and UAE e-invoicing helpers

- ERPGulf `zatca_erpgulf`: MIT, already in the register.
- `mqqz/fatoority`: Apache-2.0, Rust, 5 stars, pushed 2026-11-18, ZATCA Phase 1 and 2 toolkit [S55] CONFIRMED. Too small to depend on; consider as a cross-check in tests.
- `fatoora-einvoice` (PyPI): last release 2023-08-19, licence unconfirmed [S56] UNVERIFIED: reject.
- UAE: PINT AE Billing v1.0.4 is published by the UAE Peppol Authority [S57] CONFIRMED. `phax/peppol-uae` is Apache-2.0, Java 17, with Schematron validation for TDD documents [S58] (secondary index, UNVERIFIED on the repo); `phax/phive-rules` reports NOASSERTION [S59]. **Verdict: consider** as a validation service in CI and pre-submission checks, not in the ledger path. Odoo UAE validator is proprietary [S58].

## 12. Gap 10: marketing automation (segments, journeys, A/B)

**ERPNext core.** Email Campaign and Newsletter only; no journeys or A/B (INFERENCE).

| Tool | Licence | Notes | Verdict |
|---|---|---|---|
| Mautic | GPL-3.0 (LICENSE.txt) [S60, S61] CONFIRMED | PHP; 11,129 stars; single-tenant per install (WIDELY HELD) | Reject by rule (GPL outside engine); founders may ask counsel about an unmodified separate service |
| listmonk | AGPL-3.0 [S62] CONFIRMED | Go; 24,487 stars | Reject |
| Dittofeed | MIT [S63] CONFIRMED | Multi-tenancy, embedding and white-label are in a closed-source edition [S64]; releases are alphas (v0.24.0-alpha.21, 2026-10-04) [S65] | Reject (tenancy is paid, pre-1.0) |
| GrowthBook | MIT outside three `enterprise` folders [S66, S67] CONFIRMED | TS; 8,665 stars; feature flags and A/B | Consider for A/B only, enterprise folders disabled |

Still to build: segments (queries over ERP data in our service), journeys (a step engine in our service), consent and unsubscribe, WhatsApp templates via the inbox. Laudspeaker and others: not checked (UNVERIFIED).

## 13. Gap 11: other items

- **BI and dashboards:** Apache Superset, Apache-2.0, 75,715 stars [S68] CONFIRMED: consider as a separate service; RTL and tenancy UNVERIFIED. Metabase is AGPL (WIDELY HELD): reject. Frappe Insights is AGPL (04-open-source.md).
- **E-signature:** Documenso AGPL-3.0 [S69], DocuSeal AGPL-3.0 [S70] CONFIRMED: reject; use a provider API or build.
- **Rich text (notes, email body, comments):** Tiptap core MIT, 39,155 stars [S71] CONFIRMED: adopt; paid cloud extensions not used (WIDELY HELD).
- Module items in ADR-0076 not listed here: not checked (UNVERIFIED).

## 14. Sources (all accessed 2026-11-27)

- S1 https://api.github.com/repos/chatwoot/chatwoot
- S2 https://raw.githubusercontent.com/chatwoot/chatwoot/develop/LICENSE
- S3 https://api.github.com/repos/chatwoot/chatwoot/security-advisories ; S3a https://api.github.com/repos/chatwoot/chatwoot/releases
- S3b https://raw.githubusercontent.com/chatwoot/chatwoot/develop/enterprise/LICENSE
- S4 https://developers.chatwoot.com/self-hosted/supported-features
- S5 https://chatwoot.com/pricing/self-hosted-plans ; https://developers.chatwoot.com/self-hosted/enterprise-edition
- S6 https://www.chatwoot.com/features/multilingual ; https://developers.chatwoot.com/contributing-guide/translation-guidelines
- S7 https://developers.chatwoot.com/api-reference/introduction
- S8 https://raw.githubusercontent.com/RocketChat/Rocket.Chat/develop/LICENSE
- S9 https://raw.githubusercontent.com/erxes/erxes/main/LICENSE.md
- S10 https://api.github.com/repos/mjmlio/mjml ; S11 https://api.github.com/repos/mjmlio/mjml/releases
- S12 https://docsearch.algolia.com/mcp/docs/repo/mjmlio/mjml ; https://caniemail.com/features/html-dir
- S13 https://raw.githubusercontent.com/GrapesJS/grapesjs/dev/packages/core/LICENSE ; S14 https://api.github.com/repos/GrapesJS/grapesjs/releases
- S15 https://api.github.com/repos/resend/react-email
- S16 https://api.github.com/repos/zalify/easy-email-editor ; S17 https://api.github.com/repos/zalify/easy-email-editor/releases
- S18 https://api.github.com/repos/postalserver/postal ; S19 .../postal/releases ; S20 .../postal/security-advisories
- S21 https://api.github.com/repos/KumoCorp/kumomta ; S22 https://api.github.com/repos/stalwartlabs/stalwart
- S23 https://api.github.com/repos/juspay/hyperswitch ; S24 .../hyperswitch/releases ; S25 .../hyperswitch/security-advisories
- S26 https://api.github.com/repos/juspay/hyperswitch/contents/crates/hyperswitch_connectors/src/connectors
- S27 https://hyperswitch.io/integrations/hyperpay
- S28 https://api.github.com/orgs/moyasar/repos ; S28a https://api.github.com/orgs/Tap-Payments/repos ; S28b https://api.github.com/orgs/paytabscom/repos (404)
- S29 https://api.github.com/repos/frappe/payments ; S30 https://api.github.com/repos/frappe/crm ; S31 https://api.github.com/repos/frappe/helpdesk ; S32 https://api.github.com/repos/shridarpatil/frappe_whatsapp
- S33 https://api.github.com/repos/clauderic/dnd-kit ; S34 https://api.github.com/repos/atlassian/pragmatic-drag-and-drop ; S35 https://raw.githubusercontent.com/atlassian/pragmatic-drag-and-drop/main/LICENSE
- S36 https://api.github.com/repos/fullcalendar/fullcalendar ; S37 https://fullcalendar.io/license ; S38 https://fullcalendar.io/docs/direction
- S39 https://api.github.com/repos/svar-widgets/react-gantt ; S40 https://svar.dev/react/gantt/pricing ; https://svar.dev/blog/react-gantt-pro-2-4-released/
- S41 https://api.github.com/repos/frappe/gantt ; S42 https://api.github.com/repos/schedule-x/schedule-x
- S43 https://clefincode.com/blog/global-digital-vibes/en/erpnext-customization-for-uae-and-ksa-compliance
- S44 https://api.github.com/repos/lavaloon-eg/frappe-zakat ; https://cloud.frappe.io/marketplace/apps/frappe_zakat
- S45 https://github.com/mohamedazimal27/OpenZakat ; https://github.com/IRedDragonICY/zakatrs ; https://github.com/naheed/zakah
- S46 https://zatca.gov.sa/en/HelpCenter/guidelines/Documents/Zakat-General-Guideline-Zakat-Collection-1445AH.pdf
- S47 https://docs.frappe.io/hr/gratuity-rule
- S48 https://apps.odoo.com/apps/modules/17.0/uae_wps_report ; https://apps.odoo.com/apps/modules/18.0/bb_uae_wps_sif
- S49 https://apps.odoo.com/apps/modules/16.0/saudi_gosi/ ; S49a https://ecosire.com/apps/erpnext/erpnext-ksa-gosi-mudad-payroll
- S50 https://api.github.com/repos/ucraft-com/POS-Awesome ; S51 https://api.github.com/repos/defendicon/POS-Awesome-V15 ; S52 https://api.github.com/repos/ERPGulf/POS-Awesome-KSA ; S53 https://github.com/erpgulf
- S54 https://discuss.frappe.io/t/announcing-the-launch-of-the-saudi-zatca-2-e-invoicing-app-on-frappecloud/124111?page=8
- S55 https://api.github.com/repos/mqqz/fatoority ; S56 https://pypi.org/project/fatoora-einvoice
- S57 https://docs.peppol.eu/poac/ae/pint-ae/ ; S58 https://awesome.ecosyste.ms/projects/github.com%2Fphax%2Fpeppol-uae ; https://apps.odoo.com/apps/modules/17.0/uae_einvoice_validator ; S59 https://api.github.com/repos/phax/phive-rules
- S60 https://api.github.com/repos/mautic/mautic ; S61 https://raw.githubusercontent.com/mautic/mautic/7.x/LICENSE.txt ; S62 https://api.github.com/repos/knadh/listmonk
- S63 https://raw.githubusercontent.com/dittofeed/dittofeed/main/LICENSE ; S64 https://raw.githubusercontent.com/dittofeed/dittofeed/main/README.md ; https://docs.dittofeed.com/dittofeed-ee.md ; S65 https://api.github.com/repos/dittofeed/dittofeed/releases
- S66 https://api.github.com/repos/growthbook/growthbook ; S67 https://raw.githubusercontent.com/growthbook/growthbook/main/LICENSE
- S68 https://api.github.com/repos/apache/superset ; S69 https://api.github.com/repos/documenso/documenso ; S70 https://api.github.com/repos/docusealco/docuseal ; S71 https://api.github.com/repos/ueberdosis/tiptap

## 15. Decisions for the founders

1. **Inbox:** adopt Chatwoot community as a separate service (one install per region, `enterprise/` off), or build our own inbox? Also: our own React UI on its API (more work, fully hidden) or its dashboard re-skinned?
2. **Mautic and other GPL services:** keep the rule "GPL only inside the engine" for separate services too, or ask counsel (LEG-006) whether an unmodified GPL service over the network is acceptable? Default here: reject.
3. **Payments:** confirm own Python adapters per Gulf gateway over Hyperswitch; open a security review for webhook verification and card-data scope.
4. **Email sending:** confirm bring-your-own provider for v1; does any market's data-residency rule force in-region sending?
5. **Zakat and payroll:** confirm build-ourselves in our services, and fund a Saudi accountant and a payroll specialist for test cases and official file specs.
6. **Calendar and Gantt:** accept the rule "FullCalendar standard only, no premium plugins" and SVAR core only; record both in the licence register when installed.
7. **Before any adoption:** read ADR-0076, ADR-0080 and #400 against this note (not read in this session) and add register rows.
