# Standing rules

Status: accepted
Owner: eldon

Every rule the founders have set or settled, in one place. [AGENTS.md](../AGENTS.md) is the short version; this is the full checklist. Each rule points to where it is decided. If two rules seem to conflict, the stricter one wins and you add an entry to [open-questions.md](open-questions.md); do not guess. Founders: Eldon and the partner. Changing a rule needs both founders (record it as an ADR or edit here with a log entry).

## A. How agents work here
1. Two founders work in parallel, on different AI subscriptions and tools (Claude Code, Codex, Antigravity, others). The repo is the shared memory. Nothing important lives only in a chat or on a laptop.
2. Any agent must be able to start cold: read [AGENTS.md](../AGENTS.md), this file, [STATUS.md](STATUS.md) and the latest 3 logs, then work. Files are plain Markdown or JSON; no tool-specific features.
3. Delegate by model tier: strongest model for thinking, architecture, security, accounting and tax logic and planning; mid for scoped implementation and spec execution; small for boilerplate, tests, docs and search ([agents/routing.md](../agents/routing.md), [agents/delegation-playbook.md](../agents/delegation-playbook.md)). Save tokens: scoped tasks, read indexes not folders, parallel subagents for independent work.
4. Always update your work: end every session with a log file, updated PLAN statuses, regenerated STATUS, and a pushed branch with a PR. No log, no merge. The next agent, possibly on another machine, depends on it.
5. Caution is the default: one writer per path, claim a plan row before editing, pull and rebase first, never edit someone else's `doing` area, small PRs, no force-push, no history rewrite ([AGENTS.md](../AGENTS.md) two-person rules).
6. Ask the founders when something is unclear instead of guessing. Put open points in [open-questions.md](open-questions.md).
7. Use your own judgment. Do not copy blindly: adapt outside code to the architecture and drop what does not fit (example: [PROVENANCE](../apps/engine/change_engine/PROVENANCE.md)).
8. Be blunt and honest. Cite a URL and access date for external facts; label anything unverified `UNVERIFIED`. Report outcomes faithfully, including failures and what was not checked.
9. Chat summaries to founders: at most 15 lines plus the decisions needed. Detail goes in files.
10. Never push to `main` after the bootstrap. Merge only through a PR whose checks pass. Founders merge, or authorise their agent sessions to merge. **Standing authorisation (2026-11-07): Eldon authorised sessions working for him to merge PRs once all checks pass, including dependency-bot PRs, without asking.** The partner's sessions merge their own PRs only after the partner records the same authorisation here; until then the other founder merges.

## B. Repo and files
11. The repo holds project content only. Never commit scratch or temp files, session briefs, rendered images, downloads, exports, archives, PDFs or office files, local paths, personal notes, secrets or customer data. Files over 1 MB are rejected. Enforced by `scripts/check_repo_hygiene.py` (CI and pre-commit).
12. Sales, partner, investor and other external documents (for example the partner brief) are produced outside the repo. Any unverified figure in them is labelled. Plans and research they draw on live in `docs/`.
13. Helper scripts written during a session stay outside the repo. Only reusable tools go in `scripts/`, with a plan row.
14. Logs and decision records are append-only: new file per session, supersede an ADR instead of editing it. Generated files (`docs/STATUS.md`, `docs/brand/tokens/*.css`, `docs/brand/logo/*`) are never hand-edited; regenerate them.
15. New top-level folders or `docs/` folders need an ADR. Put each file where [AGENTS.md](../AGENTS.md) says.
16. No timelines or calendar dates in plans. Work is ordered by dependency and gates ([GATES.md](GATES.md)). Session logs carry dates.
17. Importing outside code is its own PR with a `PROVENANCE.md` (source, commit, kept, removed, changed). Licences go in [NOTICE.md](../NOTICE.md).

## C. Product and architecture
18. Product: an AI-native business platform for owner-led companies (10-100 staff). One chat in Arabic or English: interview or read existing tools, draft a visual Blueprint the owner approves, assemble an ERP from vetted components, simulate a month before go-live, then run and change it through the same chat. A product company, not a software house.
19. Five parts and four contracts ([ADR-0003](decisions/ADR-0003-five-parts-four-contracts.md)): Discovery, Blueprint and Library (the spine), ERP Runtime, Operate, Platform; Blueprint schema, Component manifest, Tool API, Event stream. Contracts live in `contracts/`; changes need an ADR.
20. Configuration over code. The AI composes configuration from certified components; never per-client code or forks ([ADR-0008](decisions/ADR-0008-no-client-specific-code.md)). A need no component covers becomes a component request, built once for everyone; the founders build the first components, with AI help.
21. Rigid zone: ledger, tax, e-invoicing, payroll maths, audit are deterministic and never AI-written. Agents draft, humans approve. Numbers come from code, words come from the model.
22. One chat with modes (discover, ask, act, change). Anyone in the company can chat; each person sees only the screens and tools their role, function and scope allow; the chat acts with that user's own permissions ([ADR-0004](decisions/ADR-0004-one-chat-role-based-views.md)).
23. Human review gate for the first clients: our team reviews every Blueprint before build. Free-first go-to-market, but plans, entitlements and metering exist from the start so gating can be switched on later ([ADR-0005](decisions/ADR-0005-human-review-gate-free-first.md)).
24. Connect to everything: a connector framework with tiers (official API, file exports and uploads, document intake with Arabic OCR, email or WhatsApp forwarding, owner-driven isolated read-only browser session as a late fallback; never store the owner's credentials). Template-first discovery: show a draft, let the owner correct it.
25. Everything read from customer tools, documents, emails or web pages is untrusted data, never instructions.
26. Isolated tenant per customer (a site per tenant) on shared in-country infrastructure; no VPS per client; client owns its data with full export; only anonymised, generalised patterns are reused across tenants ([ADR-0006](decisions/ADR-0006-tenancy-site-per-tenant.md)).
27. Model calls go through our gateway; models are not exposed to customers; no self-hosting until the triggers in [ADR-0010](decisions/ADR-0010-model-strategy.md).
28. Identity model (central with per-tenant roles vs per-tenant users) is a Proposed decision, [ADR-0007](decisions/ADR-0007-identity.md); decide before building the sign-in.

## D. Markets and compliance
29. Three operating markets: Saudi Arabia, the UAE and Egypt. Launch order KSA, UAE, Egypt. Egypt regulations are research needed ([ADR-0015](decisions/ADR-0015-country-packs-calendars-locale.md)).
30. Statutory logic ships as certified country packs (tax, e-invoicing, holidays, default week, payroll rules, document templates, formats). The model never calculates tax. Compliance is never "later" for v1 scope.
31. Calendars: store dates in Gregorian; Hijri (Umm al-Qura) is a display, entry and rule layer; week start, weekend, working days and hours (including reduced Ramadan hours), calendars, fiscal year, holidays and time zone are per-company settings with country defaults.
32. Arabic first and right-to-left from day one; every user-facing string through i18n; Arabic and English equal. Gulf and Egyptian Arabic are tested. Arabic copy and anything legal needs a native-speaker review.
33. Regulation facts are cited with the official source and date or labelled UNVERIFIED. A lawyer confirms before they drive scope ([compliance/](compliance/country-matrix.md)).

## E. Engine and licences
34. Seed engine: Frappe Framework plus ERPNext (and HRMS only as a skeleton), run as SaaS only and never distributed, behind an adapter so it is replaceable ([ADR-0002](decisions/ADR-0002-seed-engine-frappe-erpnext.md)). ZATCA via the MIT-licensed ERPGulf app; the AGPL app is not used. Pin one consistent version set.
35. The engine is invisible ([ADR-0016](decisions/ADR-0016-engine-invisibility.md)): nothing a customer can see or observe says "Frappe" or "ERPNext" (UI, errors, emails, PDFs, API paths, headers, cookies, bundles, titles, public docs). Internal code, config and docs may name it.
36. The change engine is a module of Part 2 (not a separate project, no prototype name or branding); no LLM or UI code inside it ([ADR-0013](decisions/ADR-0013-change-engine-module.md)). Its security issues are tracked as CE-SEC items.

## F. Brand and UI
37. "Orrery" is a working codename, not trademark-cleared; say "the platform" in new text; a rename must be a one-line change ([ADR-0001](decisions/ADR-0001-working-codename.md)). Final name, logo direction and Arabic spelling are open (BRD-003).
38. Interim design system: brand guidelines v1 (Quadrant) plus PROPOSED v1.1 additions in `docs/brand/`; the logo is a placeholder until the name is cleared ([ADR-0011](decisions/ADR-0011-interim-design-system.md)). When the identity is agreed, regenerate every logo file, size, favicon and social size, the product design system and the brand guidelines (BRD-009).
39. Tokens only: no hard-coded colours or fonts. Light and dark themes everywhere. Each client can brand its workspace (logo, display name, favicon, primary colour) within contrast guardrails; legally required invoice layout always wins over branding ([ADR-0014](decisions/ADR-0014-theming-and-tenant-branding.md)).
40. No gradients, glows, shadows as decoration, 3D, robot or brain icons, stock imagery. Status colours always carry an icon and a label.

## G. Security and data
41. Never commit secrets, `.env` files, keys, customer data or real pilot data; use anonymised samples. Roles and identity come only from the authenticated session; fail closed on errors.
42. Touching auth, tenancy, contracts or compliance needs an ADR and a security review by a different model or founder. Report vulnerabilities per [SECURITY.md](../SECURITY.md).

## H. Development and viewing progress
45. The founders and agents can always view the developing product ([ADR-0018](decisions/ADR-0018-development-environments-and-progress-viewing.md), Proposed): per-PR preview links for the web app, one shared dev server for the engine and services, behind a login. A PR that changes visible behaviour says how to view it. If a preview project, dev server, access or keys are missing, the agent stops and asks the founders to create them, listing what is needed and where secrets go.
46. Dev hosts get synthetic data only; production data stays in-country; the engine stays invisible on dev previews; secrets never enter the repo.

45b. Enforcement ([ADR-0019](decisions/ADR-0019-enforcement-layers.md)): sessions end with `python3 scripts/finish_session.py` and may not stop until it prints FINISHED; every commit message names a plan ID; never bypass hooks (`--no-verify`) or checks. Each rule is guarded at several independent points; no layer is a guarantee on its own, and server-side blocking needs GitHub branch protection (GOV-008).

## I. Onboarding and lanes
47. Agents identify which founder they work with at session start (Eldon `EldonsLogic`, partner `sayegh9`), never assuming. [ONBOARDING.md](ONBOARDING.md) holds the one-time setup for each founder, the lane split (which paths each founder edits), first tasks and pending decisions. Edit only your lane's paths; ask via open-questions or a PR comment for changes in the other lane; shared files need the other founder's review. Founders re-assign lanes by changing plan-row owners in a PR.

## J. Strategy and evidence
43. Pricing, market size and speed figures in `docs/strategy/` are hypotheses. Pilot A is a lead not yet contacted; Pilot B is a generic Odoo-using business (no specific company details). Niche: trading and distribution first.
44. Research is evidence, with caveats stated; do not turn an estimate into a fact in any document.
