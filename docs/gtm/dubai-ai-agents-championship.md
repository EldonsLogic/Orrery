# Dubai Create AI Agents Championship: agent choice and plan (GTM-004)

Status: draft. Owner: eldon. Plan row: GTM-004 (G1). Access date for every source below: 2026-11-21.
Labels: VERIFIED = read on the official page today; REPORTED = press or aggregator only; UNVERIFIED = not found.
Related: [../research/02-market-and-customer.md](../research/02-market-and-customer.md) section 5, [../research/05-investors.md](../research/05-investors.md) section 3, [../fundraising/investor-shortlist.md](../fundraising/investor-shortlist.md) row 13, decision 2026-11-04 in [../strategy/decisions.md](../strategy/decisions.md) (founder will enter; agent open).

## 1. What the championship is
| Item | Finding | Status | Source |
|---|---|---|---|
| Organiser | Dubai Chamber of Digital Economy (DCDE), part of Dubai Chambers | VERIFIED | https://www.dubaichamberdigital.com/en/create-ai-agents |
| Launch | 7 Oct 2026; successor to the Create Apps Championship | VERIFIED (launch date on page) | same |
| Eligibility | Anyone, any location; solo or teams up to 6, each member registers individually; free to enter; self-funded build; idea, prototype or early MVP; agent must be original, not copied from a repository, not already fully commercialised; existing businesses may enter a new agent or capability | VERIFIED | same |
| Tracks | Best Societal, Best Personal, Best Business, Best Youth (lead under 21) AI Agent | VERIFIED | same |
| Deadlines | Registration closes "Jan 2027" on the page; prototype, pitch deck and demo video due Jan 2027 with 24 semi-finalists named; semi-final pitch day Mar 2027 (12 finalists); grand final first week of May 2027. No exact days. | VERIFIED month only | same |
| Conflict on close date | Our earlier notes say registration closes Dec 2026 (press/aggregators); the official page now says Jan 2027. Assume the earlier date until DCDE confirms in writing. | CONFLICT, UNVERIFIED day | [../research/02-market-and-customer.md](../research/02-market-and-customer.md); WhatsApp +971 800 242 6237 (official contact) |
| Prizes | USD 150,000 grant per category winner (AED 550,000 per press); one winner also titled Dubai AI Agent of the Year with extra funding, amount not on page (press: AED 1M) | VERIFIED (USD), REPORTED (AED, extra) | page; https://www.khaleejtimes.com/uae/sheikh-hamdan-launch-create-ai-agents-championship-prizes |
| Judging | Independent jury, investors, industry experts; "predetermined criteria", no published rubric; page stresses customer need, business potential, measurable impact | rubric UNVERIFIED | page; terms s3.1 |
| Submission | Prototype, pitch deck, demo video; English only; multiple submissions allowed; finalists show a fully working agent live on stage; must protect personal, confidential and organisational data | VERIFIED | page |
| IP | Participant keeps IP (s5.1); DCDE gets a non-exclusive, royalty-free licence to use, reproduce and display the agents for promotion (s5.2) | VERIFIED | https://www.dubaichamberdigital.com/en/create-ai-agents-register-your-interest |
| Equity | Not mentioned; prizes described as funding. Whether the grant carries conditions beyond the terms page: UNVERIFIED | UNVERIFIED | same |
| Prize collection | Winners, incl. businesses licensed outside Dubai, must set up or hold a Dubai company with a valid trade licence to receive funds (s1.3); no licence needed to enter (s1.1); prize non-transferable, no cash redemption (s4.3) | VERIFIED | same |
| Other terms | Finalists attend in person in Dubai and pass security clearance (s9); jury may reject entries without reasons, decisions final and non-challengeable (s3.2, s3.3); DCDE may keep all submitted files (s10.3); content must comply with UAE law (s2.5); full T&Cs linked to https://www.dubaichambers.com/terms-and-conditions (not read) | VERIFIED (summary); full T&Cs UNVERIFIED | register page |

Not a lawyer. Counsel (LEG-003) should read the full T&Cs before anything is submitted.

## 2. Recommendation: one narrow agent
**Enter the "Owner Interview agent": a draft-only agent that interviews an owner-led trading company in Arabic or English, starting from a template, and produces a Blueprint draft, a gap list and a scoped quote for a human to approve.**

Why this one:
- Strongest showcase of the product's front door (interview, draft a Blueprint) and the Best Business criteria (measurable value: hours of consultant discovery replaced, checkable output).
- Fits AGENTS.md: it writes no ledger, tax, e-invoice or payroll logic (principle 3); output is a draft, `draft` to `owner_approved` stays human (DSC-009); numbers in the quote come from code, words from the model (principle 6); runs on synthetic data only (DAT-009, ADR-0018); untrusted-content handling for pasted or uploaded documents (SEC-003, SEC-014).
- Engine invisible: the demo shows the Blueprint viewer and the draft, never the engine (ADR-0016). The entry must not name Frappe or ERPNext in deck, video or UI.
- Mostly built already: DSC-001, DSC-002, DSC-004, DSC-005, DSC-006, DSC-007, DSC-008, DSC-019 are `done`; OPR-010 chat is `done`. Effort is packaging, an eval-backed demo path and a clean Arabic/English script, within the ~2-week cap in decision D-P2-10.

Eligibility risk and framing: "not already fully commercialised". The platform is not on the market (current gate G0), and we enter the interview agent as a new capability, not the ERP builder or a live product. Do not present customers, pricing or a launched service. Confirm with DCDE (see section 7).

Rejected options:
| Option | Why not |
|---|---|
| Draft-only Operate agent (approvals, reports) | Needs OPR-004..008 (`todo`); a live ERP behind it drags in the engine and ledger paths. |
| ZATCA-ready invoice agent | Closest to tax and e-invoice logic; AI-written compliance would break principle 3 and invite a certification question (LEG-007). |
| Whole platform | Likely ineligible as a commercialised product; too big for the cap. |
| Messy-data cleaner (DSC-019 alone) | Strong, but narrower story and weaker Arabic-owner appeal; keep as a demo segment, not the entry. |

## 3. Gate-based plan (no dates; dependencies are plan IDs)
Proposed new plan rows (the founder or partner adds them to docs/PLAN.md; none is created by this note). Owner eldon, lane per scripts/lanes.json. Numbers are placeholders.
| Step | Work | Depends | Gate |
|---|---|---|---|
| A | GTM-004: this note accepted, agent chosen, ADR recording the choice | none | G1 |
| B | Written confirmation from DCDE of the registration close day and of the "not commercialised" reading; request full T&Cs | A | G1 |
| C | Register (each team member individually); free; no licence needed | B | G1 |
| D | New row: demo path "interview to Blueprint draft to gap list to quote", Arabic and English, synthetic trading company only | DSC-005, DSC-004, DSC-006, DSC-007, DSC-008, DAT-009 | G1 |
| E | New row: eval set for the demo (QA-002 Arabic set plus 10 interview transcripts; pass bar stated before running) | QA-001, QA-002, D | G1 |
| F | New row: injection check on the demo inputs (uploaded document attempts to redirect the agent) | SEC-003, SEC-014, D | G1 |
| G | New row: English pitch deck and 3-minute demo video, claims limited to VERIFIED figures ([figure-sources.md](figure-sources.md)) | E, F | G1 |
| H | Submit prototype, deck and video; keep a copy of what was submitted | G, B | G1 |
| I | If a semi-finalist: live-stage reliability pass (cached fallback transcript, no live dependence on one model route) | H | G1 |
| J | If a finalist: Dubai entity and trade licence route, counsel review of grant conditions | LEG-003, LEG-010, LEG-011, H | G2 |
Dependence rule: every step above is Eldon's lane, so no row depends on the partner's open rows (ADR-0025). Step D reuses `done` rows only. Any change to `apps/` code needs a plan row for the current gate; the founder decision of 2026-11-04 said no code for now, so D needs an explicit go from the founder.

## 4. Demo script (about 3 minutes, English with an Arabic segment)
1. Problem (20 s): an owner of a 40-person trading company in the Gulf spends weeks with consultants before any software runs.
2. Arabic chat (60 s): the owner (synthetic persona) answers in Arabic; the agent starts from the trading template, shows the draft, the owner corrects it (DSC-004, DSC-005).
3. Blueprint view (30 s): owner-readable visual Blueprint (DSC-007); the agent marks which items it is unsure of.
4. Messy file (30 s): a synthetic Excel with duplicate Arabic names; quarantine report flags, never corrects (DSC-019).
5. Gap list and quote (20 s): gap against the library, quote with numbers computed by code (DSC-006, DSC-008).
6. Human gate (20 s): the agent stops at `draft`; the accountant view and the owner approve (DSC-016, DSC-009). Say plainly: the agent never posts entries or computes tax.
Backup: pre-recorded run of the same path; synthetic data banner on screen.

## 5. Risks
| Risk | Mitigation |
|---|---|
| Rejected as "already commercialised" or as the whole product | Narrow framing; DCDE confirmation in writing (step B) |
| Registration may close in Dec 2026 (conflict) | Treat Dec as the deadline until DCDE says otherwise |
| Grant requires a Dubai company and licence; non-cash prize | Decide the entity route early (LEG-010); finalists only |
| Terms: DCDE promo licence, file retention, no-reason rejection, security clearance, non-challengeable jury | Counsel read of full T&Cs (LEG-003); submit nothing confidential; synthetic data only |
| Finalists must run a fully working agent live | Eval-backed path, fallback transcript, rehearse |
| Distraction from G1 interviews (GTM-002) | Hard cap about 2 weeks of effort; stop if GTM-002 slips |
| Demo leaks "Frappe" or "ERPNext", or real customer data | Check deck, video and UI strings before submit (ADR-0016, ADR-0018) |
| Name "Orrery" is not cleared | Say "the platform" in deck and video (LEG-008) |
| Claims in the deck unsupported | Only VERIFIED figures; label targets as ours |

## 6. Success measures (set before building)
- Demo path completes on 10 synthetic interviews (5 Arabic, 5 English) without a human fixing the Blueprint draft beyond the planned correction step.
- Zero ledger, tax or payroll values produced by the model in any output.
- Zero engine names visible in any asset.
- Submission accepted by DCDE (receipt kept).

## 7. What the founders must decide
1. Go or no-go to write code for the demo (the 2026-11-04 note said no code for now).
2. Confirm the Owner Interview agent as the entry (or pick another from section 2).
3. Who builds and who pitches (Eldon's lane covers all steps; partner may pitch or review).
4. Whether to ask DCDE the eligibility and deadline questions now (recommended: yes, this week) and who calls.
5. Dubai entity and trade licence route if we win (links to LEG-010); acceptable cost before knowing the result.
6. Approve counsel (LEG-003) reading the full T&Cs, in particular the promotional licence, retention of files and any grant conditions.
7. Effort cap in days and the stop rule against GTM-002.

Questions for DCDE (send in writing): exact registration close day; whether a pre-launch platform with a prototype agent counts as "not fully commercialised"; scoring rubric; grant payment conditions and reporting; whether a team may name a working product brand in the deck.

## Sources (all accessed 2026-11-21)
- https://www.dubaichamberdigital.com/en/create-ai-agents (official page)
- https://www.dubaichamberdigital.com/en/create-ai-agents-register-your-interest (official terms summary)
- https://www.khaleejtimes.com/uae/sheikh-hamdan-launch-create-ai-agents-championship-prizes (press, prizes)
- https://www.thenationalnews.com/news/uae/2026/10/07/dubai-launches-create-ai-agents-championship-with-prize-money-exceeding-dh25m/ (press, launch; listed in search, not read)
