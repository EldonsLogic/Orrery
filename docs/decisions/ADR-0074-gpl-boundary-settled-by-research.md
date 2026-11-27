# ADR-0074: GPL boundary settled by research; counsel only before we convey

Status: Proposed
Owner: eldon
Approved by: Eldon (founder, 2026-11-27, in session); partner pending on this PR

## Context
G1 requires "Counsel has answered the GPL boundary and vendor-certification questions in writing" ([GATES.md](../GATES.md)). LEG-003, engaging counsel, is still in progress, and LEG-006 depends on it. The partner noted on the module amendment that the GPL point was being treated as settled when it was not.

[gpl-saas-boundary.md](../research/gpl-saas-boundary.md) answers the question from primary sources, each labelled and dated 2026-11-27:
- GPL-3.0 section 0 says network interaction without transferring a copy is not conveying.
- Section 2 allows running, modifying and propagating works we do not convey without conditions.
- The FSF FAQ and Frappe staff agree.
- The four markets' copyright laws do not read "making available" in a way that adds a duty, because GPL-3.0 already permits it.

What stays uncertain is listed bluntly in section "What stays uncertain". Only one of those points could create a duty, and only in a model we do not run (SaaS only, ADR-0002, ADR-0029): whether our in-process apps count as derivative works. That duty would arise only if we conveyed a copy.

## Decision
1. For the GPL part of the G1 criterion, accept the research note as the written answer. The G1 line becomes: "The GPL boundary is answered in writing ([gpl-saas-boundary.md](../research/gpl-saas-boundary.md), ADR-0074) and its compliance rules are enforced; counsel has answered the vendor-certification questions in writing."
2. The note's 13 compliance rules become standing rules. Each automatable rule gets a CI check under a plan row before G1 exits:
   - no engine assets or routes reach customers;
   - no engine code in our bundles;
   - an AGPL blocklist in the image build;
   - no "TBD" app licence;
   - business-data-only exports.
3. Counsel is required, as before, before anything that conveys a copy: on-premises, customer-controlled cloud, resellers or white-label, intra-group transfers, or a mobile bundle with engine code. That is LEG-017 plus a new ADR. Counsel is also required for the vendor-certification questions, and for the trademark opinion before brand spend or launch (Q-602). This ADR does not change those.
4. Before G1 exits, decide the licence of our in-process apps (rule 8). The recommendation is GPL-3.0-compatible, kept thin (rule 9).
5. Re-run the research at every engine version bump that changes a licence file, and whenever a market adds open-source case law.

## Alternatives rejected
- Keep the counsel opinion for the GPL part: it adds cost and delay but no duty while we stay SaaS only. Counsel adds the most value at the point we would convey, which point 3 keeps.
- Treat the question as settled with no written record: that is what the partner rightly objected to.

## Consequences
- The G1 GPL item can close once this ADR is accepted and the rule checks exist. LEG-006's dependency on LEG-003 is dropped for the GPL part.
- On-premises and hybrid delivery stay blocked (ADR-0029, LEG-017).
- Add-on apps (Webshop) may be pinned once this ADR is accepted, subject to rule 7 and the licence register.
- New plan rows are needed for the rule checks, and for the in-process app licence (rule 8).

## Supersedes
None. Amends the GPL wording of the G1 criterion in GATES.md.
