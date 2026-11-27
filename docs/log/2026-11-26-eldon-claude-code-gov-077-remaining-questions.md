# Session log: gov-077-remaining-questions

Date: 2026-11-26
Author: eldon
Tool and model: claude-code (Claude Opus 5.5)
Plan IDs: GOV-077

## Summary
Eldon asked for every remaining open question to be answered (2026-11-26). This session goes through the partner, shared and unassigned rows in `docs/open-questions.md` (Q-3 and Q-214 are skipped because they are handled separately) and the open items in `docs/strategy/open-questions.md`. Engineering rows get the safest option, consistent with AGENTS.md, the accepted ADRs and Eldon's answers in #370 to #372 and on #335, #336, #344 and #355. Founder decisions and research items are not edited; they go to Eldon as a separate list outside the repo. Stacked on #372.

Counts:
- `docs/open-questions.md`, 52 open rows: 31 answered with the safest option, 4 founder decisions (Q-9, Q-129, Q-295, Q-479) and 17 research items (Q-8, Q-11, Q-267, Q-552, Q-615 to Q-626, Q-628). None was already settled.
- `docs/strategy/open-questions.md`, 11 open items: 5 marked resolved (items 3, 6 and 11, plus items 4 and 8 in part), 4 founder decisions (items 1, 2, 10, and the entity part of item 4) and 3 research items (items 5, 9, 12).

## For the partner
Eldon's delegated answers to your rows (prefix `ANSWERED 2026-11-26 (Eldon, delegated to Claude Opus 5.5; safest option)`, ending "Partner to confirm."; owners unchanged). Please confirm or object on the PR:
- Partner-owned: Q-6, Q-15, Q-24, Q-26, Q-27, Q-176, Q-303, Q-310, Q-474, Q-475, Q-476, Q-477, Q-478, Q-515, Q-517, Q-550, Q-551, Q-553, Q-554, Q-555, Q-556, Q-557, Q-559.
- Shared (`both`): Q-135, Q-300, Q-309, Q-311, Q-516, Q-519, Q-558.
- Unassigned: Q-2 (answered, no confirmation line).
- Q-478 and Q-551 keep the fail-closed refusal until the market accountant approves a treatment. Q-555 restricts back-dated stock entries under Q-23.
- Your partner-owned accountant and ZATCA rows (Q-8, Q-267, Q-552, Q-615 to Q-626, Q-628) are left open as research items.

## Files touched
- `docs/open-questions.md`: 31 rows answered.
- `docs/strategy/open-questions.md`: items 3, 4, 6, 8 and 11 marked resolved or partly resolved, with evidence.
- `docs/PLAN.md`: GOV-077 (doing) and four partner `todo` rows from the answers: ERP-040 (pin manifest, Q-26), ERP-041 (stock and import input guards, Q-555 to Q-557), PLT-035 (gateway stream pass-through and caller context, Q-176 and Q-300 b), CMP-046 (UAE tax invoice mode, Q-553). Existing rows reused: ERP-038 (Q-475), ERP-039 (Q-311), ERP-032 (Q-558 d), INF-016 (Q-474).

## Decisions
- No ADR. The answers say "needs ADR" where one is needed (Q-309 event store, Q-27 v16 move, Q-516 recording, Q-519 downloads). Proposed ADRs they lean on (ADR-0039, ADR-0042, ADR-0043, ADR-0051, ADR-0052) stay Proposed.

## Tokens or cost
Unknown.

## Next step
Partner confirms or objects to his rows on the PR. Eldon takes the founder list. The research items go to the market accountant, counsel and official ZATCA, FTA and ETA sources.

## Founder answers added

Eldon's founder answers of 2026-11-26 (second batch), recorded as given:

- Q-9 and Q-129 (hosting): one major cloud using its in-country regions, plus a local provider only where it has none.
- SOQ-10 (GTM-002): wait for a clickable demo before the 20-30 buyer and accountant interviews.
- Q-295 (engine NDA): never named outside the founders, except the open-source notices page ADR-0016 already allows.
- SOQ-4 (LEG-010, entity): one UAE entity first, serving all four markets; confirm it can invoice Saudi clients before signing.
- SOQ-1 (Pilot A): the current lead fits the trading and distribution niche; they are Pilot A.
- Q-479 (invoice accent): remove the accent rule from the v1 branded tax invoice; revisit in a brand review.
- SOQ-2 (Pilot B): closed; Pilot A is the Odoo company, so no separate Pilot B.

## Research answers added

Eldon answers for both founders: the 44 trailing "Partner to confirm." notes now read "(Eldon answered for both founders.)". Four rows keep a narrower "Partner to confirm ..." clause (adapter side, gateway), left as written.

Research items answered (21), with sources in each row:
- From official sources (14): Q-267, Q-552, Q-553 (UAE Art. 59 contents), Q-615, Q-616, Q-617, Q-618, Q-619, Q-620, Q-623, Q-624, Q-626, Q-628, plus strategy item 5 (organiser page; no rubric published). Sources: ZATCA May 2026 guidelines, the Submit VAT Return user guide, the 2023 Arabic return guide, the XML Implementation Standard, the E-Invoicing Implementation Resolution Annex 2, the ZATCA E-Invoicing Detailed Guideline (PDF provided by Eldon) and the MoF consolidated Cabinet Decision 52/2017.
- Safe defaults pending the accountant or counsel (7): Q-8, Q-11, Q-621, Q-622, Q-625; strategy items 9 and 12 pending official confirmation (item 12's UAE e-invoicing dates are confirmed from Ministerial Decision 244 of 2025).

Accountant checks to add to the CPA review:
1. KSA return: purchase-side adjustment sign and whether the portal accepts negative sales adjustments (Q-617); exactly SAR 15,000 correction boundary and the portal's stale 5,000 hint (Q-620); first and stub tax periods (Q-621); column for prior-period purchase notes and late Art. 49(8) claims (Q-622, Q-626); evidence for Box 5 exempt sales without XML (Q-628); current consolidated Arabic regulations (Q-625).
2. KSA e-invoice: approve the import, reverse-charge and restricted-input workflows and the sandbox case list (Q-267); which XML level ERP-016 uses for the invoice discount and the Arabic label (Q-552).
3. Chart of accounts and standard per market, full IFRS or IFRS for SMEs per tenant (Q-8).
4. Egypt: ETA e-invoice and e-receipt obligation per tenant, VAT rate table, payroll rates, PDPL executive regulations (Q-11, with counsel).
5. UAE: confirm the Art. 59 field list for the CMP-046 layout and the AED 10,000 simplified-invoice limit.
6. Counsel (not the accountant): LEG-006, LEG-007, LEG-011, LEG-012 points in strategy item 9; GOSI, WPS and PDPL dates in item 12.
