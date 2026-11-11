# Phased delivery and lanes

Status: proposed
Owner: eldon
Approved by: pending (partner review; see [ADR-0026](../decisions/ADR-0026-phased-delivery-and-market-pack-track.md))

How the product is delivered in proven steps, what each step builds and must prove, how it maps to the readiness gates, and who does what. It follows the founders' product definition and the partner's review responses; it does not change an accepted decision until the ADRs in this PR are accepted. Rules of record: [../../AGENTS.md](../../AGENTS.md), [../RULES.md](../RULES.md), [../GATES.md](../GATES.md). Figures marked HYPOTHESIS are not release gates.

## 1. What we are building (one view)
- An AI-native business operating system for owner-led companies (about 10 to 100 staff) in Saudi Arabia, the UAE, Egypt and Qatar. Not an app builder; a platform configured per business, built for any kind of business through a growing library of components and templates ([../RULES.md](../RULES.md) rules 18 to 20, ADR-0008).
- Two ways to get a system, same tooling and result: **self-build** (chat and visual builder, the owner approves) or **team-assisted** (our team runs the builder with the customer). After go-live the customer changes the system by asking the builder, with owner or admin approval.
- Every user gets a simplified screen for their function and a chat limited to their role and scope. Customers create agents with an autonomy level per agent, always under the human floor ([ADR-0027](../decisions/ADR-0027-human-floor-action-policy-and-agent-authority.md)).
- Deterministic finance on an engine the customer never sees; Arabic first; each market is a country pack ([ADR-0015](../decisions/ADR-0015-country-packs-calendars-locale.md), [ADR-0024](../decisions/ADR-0024-four-phase-1-markets.md)).
- Flat monthly price per organisation is the commercial shape (HYPOTHESIS until measured; pricing lives in [../strategy/](../strategy/)).
- Not in scope now: a general app builder, customer-written code, point of sale and offline use in version one (confirm with the pilot), payroll calculation (file export only), AI-written ledger or tax logic.

## 2. The phases
Each phase closes only after an exit run ([../GATES.md](../GATES.md), RULES 48). Evidence items are listed in [../specs/phase-exit-criteria.json](../specs/phase-exit-criteria.json).

| Phase | Goal | Builds | Proves |
|---|---|---|---|
| **0 Engine proof** | The engine behaves as our documents assume, on a pinned bench | Pinned bench, one site per tenant, gateway in front; six proofs: two-tenant isolation, one reconciled transaction, denied operation on failure, interrupted guarded change with recovery, duplicate-effect prevention, one minimal real Blueprint-component-adapter connection; token metering in the gateway; lead conversations | A pilot is worth planning, and engine limits are known |
| **1A Manual golden system** | One synthetic company configured by hand on the real bench | The agreed golden path: customer, item price, sales order, invoice, ledger and stock effects; versioned Blueprint-to-engine mapping; Arabic invoice print format; role views | Expected ledger and stock results, independently checked |
| **1B Builder reproduction** | The builder reproduces the approved setup | Typed proposals, Blueprint, library v0, guarded publish with diff; one guarded change with recoverable failure; credit note and undo; automatic acceptance test; role-scoped read-only chat; agents on synthetic runs | Reproduction rate over repeated runs; setup time, corrections and AI cost measured |
| **2 Pilot (first market: Qatar)** | A real customer pays and goes live | Before real data: data-handling arrangements, approved location and transfer route, access controls, retention, incident path, named accountant. Before live posting: production environment, tested restore, export and exit, reconciled opening balances, owner and accountant sign-off, support. Cutover (parallel run, open documents and history, training). Online-store connector only if the lead confirms it is needed. At most one draft-only agent | Someone pays; setup repeats; real cost per tenant |
| **3 Repeatability** | A second customer is cheaper and as correct | Second customer on the same shape; services template; fleet upgrades by Blueprint replay; release rings; accountant review screen; self-serve waiting list | Reuse and lower all-in effort without losing correctness |
| **4 Scale** | Growth without proportional staff | Self-serve, billing, abuse controls, richer agent autonomy by separate evidence-based decision, in-country AI options, library growth loop | Targets set from pilot data |

**Market-pack track (parallel, from Phase 2).** Qatar is the intended first pilot market, confirmed by readiness (verified research CMP-030, pack CMP-031, the lead, an accountant, hosting and data-transfer position) before real data; until then it is a hypothesis. The UAE, Saudi Arabia and Egypt packs follow right away in the build, in readiness order, as a managed track: a named owner and capacity limit per active pack, "right away" meaning research and requirements first and a working pack after Phase 1B, and a country release checklist (CMP-032) covering legal and accounting scope, e-invoicing where required, data processing, evidence, accountant review and operational controls. No pack blocks the Qatar pilot and none receives real customer data before its own review. This is consistent with ADR-0024 (no fixed launch order).

## 3. Phase to gate map (proposed)
The repository's gates stay the system of record. Until the founders accept ADR-0026 and GOV-037 edits [../GATES.md](../GATES.md), this map is guidance, not a gate change.

| Phase | Closest gate | Note |
|---|---|---|
| 0 | G1 | Bench, scripted tenant creation, isolation suite. G0 must be closed first (it is current). |
| 1A | G1 | Hand-written Blueprint applies to a fresh tenant; Arabic invoice reviewed |
| 1B | G1 then G2 | Builder path, human review gate |
| 2 | G2, plus the G3 controls that apply before live posting | Real data and live posting are separate checkpoints |
| 3 | G4 | |
| 4 | G5 | |

Gate wording that conflicts with this plan and needs a founder decision (GOV-037):
1. G1 lists "A ZATCA Phase 2 invoice passes the ZATCA sandbox". Proposal: keep it as a Saudi release criterion, and make first-pilot compliance criteria depend on the chosen market, so Qatar is not blocked by another pack.
2. G1 says a Blueprint "applies, diffs and rolls back". Proposal: align with ADR-0028 (recoverable, journaled apply; no universal rollback).
3. G2 says "simulated Blueprint". The one-month simulation is optional, not core.
4. G3 says UAE e-invoicing and payroll shipped or excluded. Proposal: make it per market.
5. The Arabic invoice print format (ERP-007) depends on ZATCA Phase 1 work (CMP-003). The golden path needs a country-neutral print, so that dependency must be split or it contradicts "no pack blocks the Qatar pilot".

## 4. Lanes and who does what
Lane rules: [../ONBOARDING.md](../ONBOARDING.md) section 2, `scripts/lanes.json`, ADR-0025. Every open row has one owner. A row depends on the other founder's row only if that row is in an earlier gate; cross-lane needs are met by interface rows (a contract, a fixture or a fake) a gate earlier. `python3 scripts/check_plan_independence.py` enforces this.

| Phase | Partner lane (engine, runtime, compliance) | Eldon lane (spine, product, operate, web, commercial) |
|---|---|---|
| 0 | ERP-001 bench; ERP-003 scripted tenants; SEC-004 isolation suite; BPL-012 adapter interface; ERP-021 six-proof suite; PLT-025 gateway token metering (`services/gateway/` is the partner lane) | GTM-019 lead conversations; CMP-030 Qatar research; BPL-029 mapping spec (interface, G0); BPL-025 and BPL-026 contracts (draft, recoverable wording per ADR-0028) |
| 1A | ERP-005 core module scope; ERP-014 accounting correctness tests; ERP-022 manual golden system, timed; country-neutral Arabic invoice print (split from ERP-007, see GOV-037) | BPL-028 golden path spec (G0; [golden-path-trading-sale.md](../specs/golden-path-trading-sale.md), checked independently now, accountant before Phase 2); QA-018 acceptance test; role-view definitions |
| 1B | ERP-012 engine adapter; BPL-027 compile and apply through the real adapter | BPL-030 builder reproduction; QA-019 leak canaries; SEC-019 action-policy table; SEC-020 agent role spec; QA-020 optional routing experiment |
| 2 | ERP-023 policy enforcement in the engine; backup and restore drills; opening-balance importer (ERP-013); CMP-031 Qatar pack; CMP-032 market-pack checklist | LEG-019 real-data and live-posting checklists and manual accountant sign-off route; GOV-039 market-pack track plan; OPR-016 optional first agent; OPR-001 to OPR-009 operate path; pricing and pilot terms (GTM, FND) |
| 3 | UAE e-invoicing integration (CMP-011); fleet upgrade by replay (ERP-004 follow-up); second template components (ERP-018) | CMP-009 choose the UAE accredited provider; release rings and accountant review screen (OPR, WEB); self-serve waiting list |
| 4 | Saudi and Egypt packs as readiness allows; region operations | Self-serve billing and identity (PLT, WEB); autonomy decisions; growth loop (BPL-024) |

Open ownership question for the founders: the Blueprint-to-engine mapping. Proposal: Eldon owns the versioned mapping contract and fixtures (BPL-029, an interface row at G0), the partner owns the real-adapter conformance proof (ERP-021 and ERP-022 at G1). The balance of rows between lanes (the plan is heavy on the Eldon lane) is reviewed in GOV-020.

## 5. The AI layer and the closed loop by phase
- **Phase 0:** gateway skeleton with token metering; evaluation harness started (QA-001).
- **Phase 1A and 1B:** typed proposals only (the model proposes, code validates, a person approves, a guarded publisher applies); bilingual evaluation set; the builder measured against the golden Blueprint; model version pinned and the golden set re-run on any model change; agents tested on synthetic runs.
- **Phase 2:** at most one draft-only agent, with a platform cap, its own least-privilege role, cost cap and kill switch (SEC-020); the core pilot must work with agents off. An optional bounded-decision model can be compared on synthetic data (QA-020), never as a dependency and never with real data until the processing route is approved.
- **Closed loop:** Phase 1 logs every unmet need and manual correction; Phase 2 fixes a gap once, tests it and releases it as a component; Phase 3 adds release rings and verification; Phase 4 runs it weekly. Learning uses structure (diffs, failed validations, unmet-need tags), never customer records.

## 6. How agents work this plan
Orchestrators follow [../../agents/team-protocol.md](../../agents/team-protocol.md) and [../../agents/roles.md](../../agents/roles.md): three to five roles per task, loop observe, plan, execute, verify, record, a different model reviews. Self-improvement of prompts and roles is benchmarked (GOV-038) and never changes approval gates, evaluation rules, lanes or the phase exit check.

## 7. Decisions still open (from the partner's responses)
1. The golden path draft is in [../specs/golden-path-trading-sale.md](../specs/golden-path-trading-sale.md). Open: the other founder's independent check and confirming its engine settings on the bench. No accountant is needed for Phase 1A; the accountant reviews it before Phase 2.
2. Whether the pilot needs an online-store connector, and the manual fallback.
3. Which one draft-only agent, if any, is in the pilot, and its authority.
4. The manual accountant sign-off route before an accountant screen exists (LEG-019).
5. Capacity and ownership for each parallel market pack, and what "right away" means per market (GOV-039).
6. Action-policy detail: initiating versus approving humans, approval binding, behaviour on cancellation and failure (SEC-019).
7. How the gate wording changes (GOV-037) and which rows move.
8. Security and correctness issues reported by the partner are handled through [SECURITY.md](../../SECURITY.md), not described here; they must be verified and fixed on current main before any financial use.

## 8. Evidence and caveats
Panel and partner figures (hours, percentages, prices) are hypotheses. Legal and market facts in the research behind this plan came from secondary summaries and need counsel confirmation; nothing here states a Qatar, UAE, Saudi or Egypt rule as fact. Pilot company details stay outside the repo ([../RULES.md](../RULES.md) rule 12).
