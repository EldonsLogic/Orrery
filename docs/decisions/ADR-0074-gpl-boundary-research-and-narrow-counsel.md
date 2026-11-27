# ADR-0074: GPL boundary for SaaS-only delivery answered by research plus a narrow counsel opinion; counsel before anything that conveys a copy

Status: Proposed
Owner: eldon
Approved by: Partner: option C chosen in writing on PR #407, 2026-11-28. Eldon: written acceptance of this reworked text (option C) on PR #407, 2026-11-28. Accepted by both founders on merge.

## Context
G1 requires "Counsel has answered the GPL boundary and vendor-certification questions in writing" ([GATES.md](../GATES.md), [phase-exit-criteria.json](../specs/phase-exit-criteria.json) G1-5). LEG-003, engaging counsel, is still in progress, and LEG-006 depends on it. The partner noted on the module amendment that the GPL point was being treated as settled when it was not, and reviewed the research on #388.

[gpl-saas-boundary.md](../research/gpl-saas-boundary.md) is our own research, marked NOT legal advice. Its labels are carried here unchanged:
- GPL-3.0 section 0 says "Mere interaction with a user through a computer network, with no transfer of a copy, is not conveying." (CONFIRMED, licence text)
- Section 2 allows making, running and propagating works we do not convey "without conditions". (CONFIRMED, licence text)
- The FSF FAQ agrees (WIDELY HELD). Two posts by a Frappe staff member agree, one opening "I am not a lawyer" (CONFIRMED as quotes; a personal reading, not a Frappe policy).
- The four markets' copyright laws give a "making available" right, which GPL-3.0 already lists as propagation that section 2 permits when no copy is conveyed, so they add no source duty. (INFERENCE, read from unofficial English texts that are UNVERIFIED for official wording)
- Frappe Framework is MIT. ERPNext, HRMS and Webshop are GPL-3.0. (CONFIRMED, GitHub licence API)

What stays uncertain (note, "What stays uncertain", carried over with its labels). Several of these could create a duty or worse:
1. No court anywhere has ruled on GPL and SaaS; no GCC or Egyptian court has applied an open-source licence in our searches (UNVERIFIED, absence in searches).
2. Whether our in-process apps are derivative works is unsettled (WIDELY HELD as the FSF view; no court has adopted it). It binds the day we convey.
3. **Written-form rules: no valid licence means no right to run.** If a local court held an unsigned GPL invalid under UAE Art. 9, KSA Art. 11, Egypt Art. 149 or Qatar Art. 8, we would have no permission to run the engine at all, which is worse than a source duty. UAE Art. 12 opens "Without prejudice to the provisions of Article (9)", so it may not cure this. Effect unresolved (INFERENCE).
4. **Hosting providers and contractors.** Section 2 calls handing them copies conveying, allowed only "provided that you comply with the terms of this License in conveying all material for which you do not control copyright", under our direction and control. Whether renting cloud servers hands over a copy, and whether standard cloud terms meet that condition, is INFERENCE.
5. **Intra-group copies** between our own companies in different countries: the FSF says it is for the local copyright law to decide (WIDELY HELD); it could be conveying.
6. **Database dumps.** A raw engine database holds DocType definitions, print formats and report definitions; whether a dump is a copy of engine code is INFERENCE. It could be conveying.
7. Statute texts are unofficial English; the Arabic texts govern (UNVERIFIED for official wording).
8. "GPL-3.0-only" or "or later" is not stated for ERPNext, HRMS and Webshop (UNVERIFIED).
9. Frappe could move future ERPNext versions to AGPL (business risk, INFERENCE).

RULES 33 says regulation facts come from official sources or are labelled UNVERIFIED, and a lawyer confirms before they drive scope. Under this ADR a lawyer does confirm them: counsel's answer on uncertainty 3 has to rest on the official Arabic texts of the cited articles, so no RULES 33 exception is needed.

## Decision
Option C, chosen by the partner in writing on PR #407: the corrected research note answers the GPL boundary for SaaS-only delivery, and counsel gives a narrowed written opinion on the open points only.
1. **Gate.** The G1 line in GATES.md and criterion G1-5 in phase-exit-criteria.json become, together: "The GPL boundary for SaaS-only delivery is answered in writing by gpl-saas-boundary.md and by counsel's written answer on ADR-0074 uncertainties 3 to 6, and its compliance rules are enforced as ADR-0074 defines; counsel has answered the vendor-certification questions in writing."
2. **Narrow counsel opinion.** Counsel answers in writing, per market, uncertainties 3 to 6 (written-form rules, hosting providers and contractors, intra-group copies, database dumps), and in the same answer confirms the official Arabic texts of the articles the note cites: UAE Art. 9 and 12, KSA Art. 11, Egypt Art. 149 and Qatar Art. 8. The statute facts are then confirmed by a lawyer, which closes uncertainty 7 the same way. The question is [counsel-scope-of-work.md](../legal/counsel-scope-of-work.md) Q8, tagged `[LEG-006 | checklist 4 | G1] M`. A counsel opinion can say whether a court in each market would likely hold an unsigned public licence valid, and whether UAE Art. 12 cures Art. 9; that is the point of asking, not a court test. Uncertainties 1, 2, 8 and 9 stay with research and monitoring, not counsel:
   - 1: no opinion can create case law; decision 6 re-runs the research when a market adds open-source case law;
   - 2: it binds only when we convey a copy, which decision 5 already sends to counsel (LEG-017);
   - 8 and 9: rule 10 re-checks the licence at each engine bump.
3. **Standing rules.** The note's 13 compliance rules become standing rules. A rule is **enforced** when one of these holds, and the `Phase exit: G1` log links the evidence for each of the 13:
   - (a) an automatable rule has a CI check merged on main that runs on every PR as a required check, with a test showing a planted violation fails it;
   - (b) a rule that cannot be automated is a row in the [legal checklist](../legal/checklist.md) with an owner, and the exit log records the evidence that it holds (the clause, the register entry, the infra register line);
   - (c) where the surface a rule protects does not exist yet (for example a customer export service), a check asserts that the surface is absent (no route serves it), and the rule's plan row stays open until the surface exists and (a) holds.
4. **Checks and owners** (plan rows in [PLAN.md](../PLAN.md)):
   - rule 1, no engine assets or routes reach customers: QA-023 (partner), added by PR #400 with ADR-0080;
   - rule 2, no engine code and no GPL or AGPL licence in our shipped bundles: QA-026 (eldon);
   - rule 7, the licence blocklist plus allowlist over apps, pip, npm and container images: QA-027 (eldon, the scanner over our lockfiles and the register) and QA-028 (partner, the engine image build);
   - rule 8, no "TBD" app licence: QA-029 (partner);
   - rule 5, business-data-only exports: QA-030 (eldon);
   - rule 9, thin in-process apps: QA-022 (eldon) and QA-024 (partner), added by PR #400;
   - rules 3, 4, 6, 10, 11, 12 and 13: legal checklist rows under LEG-020 (eldon);
   - rule 8's licence decision for our in-process apps: LEG-021 (eldon), recommendation GPL-3.0-compatible and thin (rule 9).
5. **Counsel stays required**, as before, before anything that conveys a copy: on-premises, customer-controlled cloud, resellers or white-label, intra-group transfers, database dumps to customers, or a mobile or desktop bundle with engine code (LEG-017 plus a new ADR). Counsel is also required for the vendor-certification questions and the trademark opinion before brand spend or launch (Q-602).
6. **Re-run** the research at every engine version bump that changes a licence file, and whenever a market adds open-source case law.

## Alternatives rejected
- B, research replaces counsel for the whole GPL part of G1, with a RULES 33 exception for the unofficial statute texts: it lets unconfirmed statute facts drive scope, and leaves uncertainty 3 (no valid licence means no right to run) without a lawyer's view.
- D, keep the counsel opinion for the whole GPL part: asks counsel about points no opinion can settle (uncertainties 1, 8 and 9) or that bind only when we convey (uncertainty 2), adding cost and delay without reducing risk.
- Treat the question as settled with no written record: that is what the partner rightly objected to.

## Consequences
- The G1 GPL item closes only when this ADR is Accepted, counsel has answered Q8 in writing, and every rule is enforced as decision 3 defines. LEG-006 keeps its dependency on LEG-003.
- On-premises and hybrid delivery stay blocked (ADR-0029, LEG-017).
- Once this ADR is Accepted it removes the GPL hold on add-on apps; it does not by itself release any pin (Webshop and HRMS rows in #392 stay on hold at the partner's request), and any pin stays subject to rule 7 and the licence register.
- Wording reconciled in the same PR: [licence-register.md](../legal/licence-register.md) section 4 item 3, [NOTICE.md](../../NOTICE.md), [engine-adapter.md](../architecture/engine-adapter.md) "Licence boundary", R-013 in [risks.md](../risks.md), [counsel-scope-of-work.md](../legal/counsel-scope-of-work.md) Q8 and legal checklist row 4.
- New plan rows: QA-026 to QA-030, LEG-020, LEG-021.

## Supersedes
[ADR-0002](ADR-0002-seed-engine-frappe-erpnext.md), Consequences line 19 only: "GPL boundary must be reviewed by counsel (LEG-006); hybrid or on-prem is blocked until then (LEG-017)." It becomes: "For SaaS-only delivery the GPL boundary is answered by research and by counsel's written answer on ADR-0074 uncertainties 3 to 6 (LEG-006), with its rules enforced; counsel reviews before anything that conveys a copy, and hybrid or on-prem stays blocked until then (LEG-017)." The rest of ADR-0002 stands, including "never distribute it to customers without legal review". Effective only once this ADR is Accepted.
