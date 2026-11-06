# End-to-end journey

Status: draft
Owner: eldon

States follow the build states: draft -> owner_approved -> team_reviewed (HUMAN GATE) -> built_in_sandbox -> simulated -> live. Screens are detailed in [app-screens.md](app-screens.md); website steps in [website.md](website.md). Failure copy follows [../brand/06-voice-tone.md](../brand/06-voice-tone.md): say what is missing and what happens next.

| # | Step | Screen | User action | System action | Failure states and handling |
|---|---|---|---|---|---|
| 1 | Landing | Website home / solutions page | Reads, picks language, clicks "Start" or "Book a demo" | Serves AR/EN page, consent banner, records consented analytics only | Slow page or blocked scripts: page works without heavy JS; analytics declined: nothing tracked |
| 2 | Sign up | Sign-up flow | Enters email or phone, OTP, company name, country, CR number, VAT number (optional at this step), accepts terms and privacy | Verifies OTP, creates account and trial tenant record (state: trial), stores consent record | OTP not received (resend, switch channel, rate limit shown); duplicate CR/VAT (offer sign-in or contact us); unsupported country (waitlist); CR/VAT format invalid (inline error) |
| 3 | Discovery chat | Home / chat, mode "discover" | Describes the business in Arabic or English, or picks the trading and distribution template and corrects it | AI interviews or shows the draft template Blueprint; stores answers as structured Blueprint fields; shows progress | Model unavailable (fallback provider, then "saved, continue later"); off-topic or abusive input (redirect); owner unsure (offer template); AI budget hit (message with next step) |
| 4 | Connect sources | Connect sources | Uploads Excel/CSV/PDF/photos, connects Odoo (API key or export), forwards email/WhatsApp documents | Stores files per tenant, scans, parses; reads are read-only; extracted content treated as untrusted data | Malware flag (file rejected); unreadable scan (ask for a better copy); Odoo auth fails (show the exact step); partial import (show what was and was not read) |
| 5 | Gap questions | Chat with gap list | Answers questions on missing data (e.g. branches, credit terms, VAT status) | Gap analysis compares sources to Blueprint needs, asks targeted questions, flags needs no component covers (candidate components) | Contradictory sources (ask owner which is right); uncovered need (marked "to be built by our team", affects quote) |
| 6 | Blueprint draft | Blueprint viewer | Reviews visual map of entities, workflows, roles, approvals, reports, integrations, compliance profile, branding; edits by chat or form; approves | Validates against schema; blocks approval on validation errors; state -> owner_approved on approval | Validation failure (list of exact fields); owner leaves it unapproved (draft saved, reminder) |
| 7 | Quote | Quote and plan | Reviews setup fee, plan, AI budget; accepts or asks for changes | Prices from Blueprint complexity per [pricing.md](pricing.md); records acceptance | Out-of-range scope (route to a human); price disputed (contact) |
| 8 | Team review (HUMAN GATE) | Owner sees "In review"; team sees review queue | Owner answers reviewer questions; reviewer approves, edits or rejects | Reviewer checks Blueprint, compliance profile, component choices, risks; state -> team_reviewed. No build before this | Reviewer rejects (owner gets reasons and next step); backlog (status shown honestly); Blueprint changed after review (review restarts for the diff) |
| 9 | Build in sandbox | Build progress | Watches progress; no required action | Compiler turns Blueprint into engine configuration; provisions sandbox tenant; installs certified components; missing components go through the component factory; state -> built_in_sandbox | Compile error (blocked, team notified, owner told what and when); component not yet certified (build waits, scope updated); provisioning failure (retry, rollback, alert) |
| 10 | Simulation | Simulation report | Reviews the report on a replayed month of own data; marks differences as expected or wrong | Replays the month through the sandbox, compares totals (stock, AR/AP, VAT) with source data, lists mismatches; state -> simulated when accepted | Mismatches above tolerance (list with causes, fix, re-run); insufficient data (ask for more, or run on sample data and say so) |
| 11 | Go-live | Go-live checklist | Confirms checklist: opening balances, users and roles, ZATCA onboarding (CSID) per device/unit, branding, backups verified, training | Cut-over: opening balances loaded, production tenant activated; compliance onboarding checked; state -> live | Item incomplete (blocked with the exact item); ZATCA onboarding fails (error shown, no invoicing go-live); rollback available during cut-over window |
| 12 | Operate | Home / chat (modes ask, act, change), role dashboards, approval inbox | Daily work; asks, acts, approves, requests changes | Intent router routes to ask/act/change; actions go through the typed tool API with the user's permissions; changes go through Blueprint diff, preview, approval, apply, rollback; scheduled agents run within budgets | Action denied by role (say who can approve); AI budget exhausted (explain, offer pack); change touches the rigid zone (refused, routed to the team); regulation change (notice and rollout, see [../compliance/regulation-watch.md](../compliance/regulation-watch.md)) |
| 13 | Offboard | Settings > Data export | Requests export or deletion | Exports database, CSV, documents; deletes after confirmation and retention checks; state -> exported / deleted | Retention hold (explain the legal retention); export too large (async link); SLAs are TBD ([../security/hosting-rules.md](../security/hosting-rules.md)) |

## Notes
- Steps 3-6 may loop. The owner can stop and resume at any time.
- Free-first: all features unlocked at first; entitlements and metering run from day one ([pricing.md](pricing.md)).
- Pilot variations: [pilots.md](pilots.md).

## Calendar and week in the journey (added)
- Step 2 (sign up): the country chosen (KSA, UAE, Egypt) sets defaults for calendar, week, holidays, time zone, number system and compliance pack. Failure: unsupported country goes to waitlist.
- Step 3-6 (discovery, Blueprint): the chat confirms the defaults in plain language ("Your weekend is Friday and Saturday. Correct?") and records them in the Blueprint; the owner can change them.
- Step 10 (simulation): periods, working days and holidays follow the company settings.
- Step 11 (go-live): checklist item "calendar, week, holidays and fiscal year confirmed" (owner/admin).
- Step 12 (operate): changes through Settings > Company calendar and week or by chat (change mode), with preview and audit; effective-dated.
Specs: [../architecture/country-packs.md](../architecture/country-packs.md), [../architecture/calendars-and-locale.md](../architecture/calendars-and-locale.md).
