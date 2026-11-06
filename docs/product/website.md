# Marketing website

Status: draft
Owner: eldon

Brand: follow [../brand/](../brand/) (tokens, voice, bilingual rules). Logo is a placeholder until the name is cleared. Voice rules: lead with the result, numbers not adjectives; avoid the words listed in [../brand/06-voice-tone.md](../brand/06-voice-tone.md). Code lives in `web/marketing` (empty until gate G1+; see [../PLAN.md](../PLAN.md)).

## Sitemap and content blocks
| Page | Purpose | Content blocks |
|---|---|---|
| Home | Explain the outcome in 10 seconds | Hero (one outcome line + Start / Book demo), "Describe it. We build it. You run it." flow in 3 steps, compliance strip (ZATCA, UAE e-invoicing status labelled accurately), one-month simulation explainer, proof (pilot stories only when real), pricing teaser, FAQ, footer |
| How it works | Show discovery -> Blueprint -> build -> simulate -> go-live -> operate | Step-by-step with screenshots of the real app, human review gate explained, what the AI does and does not do (ledger/tax/e-invoicing are deterministic) |
| Solutions by niche | One page per niche | First: trading and distribution (pains, modules, sample Blueprint, ZATCA); later niches added when real |
| Compliance | Trust through exactness | ZATCA Phase 1/2 status, UAE e-invoicing status, VAT, WPS (later); every claim dated and sourced; "what we do vs what you do" table from [../compliance/country-matrix.md](../compliance/country-matrix.md); no claim marked UNVERIFIED goes live |
| Trust and security centre | Answer security questionnaires | Hosting location per country, tenant isolation, encryption, backups, access policy summary, sub-processor list, AI data handling, incident contact, security.txt, certifications status (honest) |
| Pricing | Show plans | Per [pricing.md](pricing.md); free-first wording while gating is off; SAR first, AED second |
| Resources | Organic and AI-search traffic | Guides (ZATCA waves, VAT basics, leaving Odoo), glossary (AR/EN), templates; each page reviewed for factual accuracy and dated |
| About | Who is behind it | Founders, mission, "product company not a software house" in plain words |
| Contact / Book demo | Lead capture | Form (name, company, country, phone/email, preferred language, size), WhatsApp link, consent checkbox |
| Status | Uptime transparency | Public status page (components, incidents, history); separate host |
| Help centre | Self-service | Searchable bilingual articles, contact |
| Legal pages | Required documents | Terms, privacy, cookie policy, DPA summary, acceptable use, sub-processors, brand asset terms (drafts need counsel, see [../legal/checklist.md](../legal/checklist.md)) |

## Sign-up flow
| Step | Detail |
|---|---|
| 1 Identity | Email or phone, OTP (rate limited, resend, channel switch) |
| 2 Company | Company name (Arabic and English), country (KSA, UAE), CR number, VAT number (optional, required before go-live), city, industry (trading and distribution first), size band |
| 3 Consent | Terms, privacy, PDPL-style purpose notice; separate optional marketing and analytics consents; no pre-ticked boxes |
| 4 Plan | Free-first: all unlocked; show the plan the tenant would be on (entitlements recorded) |
| 5 Done | Lands in discovery chat. Account and tenant record created in state trial |
Failure states: see [journey.md](journey.md) step 2. Which fields are legally required: research needed.

## Language and SEO
- Arabic and English, full RTL layout for Arabic (not a mirror hack); URL structure per language (e.g. /ar/, /en/); `hreflang` pairs plus `x-default`; language switcher on every page; no auto-redirect that blocks crawlers.
- Arabic copy written by a native speaker, not machine translated; all Arabic taglines currently unreviewed ([../brand/06-voice-tone.md](../brand/06-voice-tone.md)).
- Arabic SEO: Arabic keyword research per page (research needed), Arabic titles/descriptions, Arabic structured data, correct `lang` and `dir`.
- AI-search readiness: clear factual pages, FAQ/structured data (schema.org Organization, FAQ, Product), `llms.txt` considered (value UNVERIFIED), dated facts, crawlable HTML (no content only in JS), and a public changelog of compliance status.

## Analytics and consent
Consent banner before any non-essential cookie or tracker; decline is as easy as accept; default off for non-essential; consent stored with timestamp and version; analytics provider choice and where data is processed are open (PDPL position UNVERIFIED, see [../compliance/data-protection-and-residency.md](../compliance/data-protection-and-residency.md)). Prefer cookieless, privacy-first analytics. No personal data in URLs.

## Performance and accessibility
| Requirement | Target |
|---|---|
| Core Web Vitals | Good on mobile for LCP, INP, CLS (thresholds from web.dev, to cite when implemented) |
| Page weight | Budget set per page type at build time; Arabic webfont subset and `font-display` strategy per [../brand/04-typography.md](../brand/04-typography.md) |
| Accessibility | WCAG 2.2 AA target, keyboard use, visible focus, contrast in light and dark, reduced motion, screen-reader tested in Arabic and English |
| Hosting | Static or edge-served where possible; regional latency for KSA and UAE visitors to be tested |
| Security | HTTPS only, HSTS, CSP, no third-party scripts without approval ([../security/hosting-rules.md](../security/hosting-rules.md)) |
| Themes | Light and dark from brand tokens; follows system preference with user override |

## Open points
Domain and name clearance (ADR-0001); who writes Arabic copy; which analytics tool; whether a UAE entity or KSA presence is needed to show prices in SAR (UNVERIFIED).

## Egypt and country selection (added)
- Markets: KSA first, UAE second, Egypt third. Launch order is unchanged; Egypt content goes live only after its country pack and compliance research are done (research needed, [../compliance/country-matrix.md](../compliance/country-matrix.md)).
- Sitemap addition: country pages (KSA, UAE, Egypt) under Compliance and Solutions, each with only verified claims and dates; Egypt page shows "coming soon" with a waitlist until ready.
- Country selection: sign-up step 2 adds a required country choice (KSA, UAE, Egypt/waitlist); it sets defaults for compliance pack, hosting region, currency, calendar, week and holidays, which the company can change later. Site language switcher and country selector are separate. Company ID fields vary by country (CR/VAT for KSA; Egypt identifiers research needed).
- Content blocks per country: e-invoicing status, VAT, language and document rules, hosting location, currency, calendar and work-week defaults.
- SEO: hreflang by language and, where useful, by country (e.g. ar-SA, ar-AE, ar-EG); Egyptian Arabic search terms researched separately.
