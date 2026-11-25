# Session log: cmp-037-official-sources

Date: 2026-11-23
Author: eldon
Tool and model: claude-code (Opus-class subagent)
Plan IDs: CMP-037

## Summary
Inventoried the official sources behind the four country packs (SA, AE, EG, QA), marked which are machine-readable and how each authority signals changes, found ZATCA's rounding section for Q-601, and proposed a law-change watch as input to CMP-020. Docs only; no pack fact changed.

## Files touched
- docs/research/cmp-037-official-sources.md: new research doc (inventory tables per market, coverage, change signals, Q-601 input, watch proposal).
- docs/PLAN.md: added row CMP-037 (done).
- docs/log/2026-11-23-eldon-claude-code-cmp-037-official-sources.md: this log.

## Decisions
- None. Q-601 stays open: the ZATCA XML Implementation Standard v1.2 (2023-05-19), section 10, specifies half-up rounding; the accountant decides whether that makes `tax.roundingRule` statutory.

## Findings that need an owner
- AE pack evidence does not cite MD 197 of 2026 (amends MD 243), MD 168 of 2026 or Cabinet Decision 173 of 2026, now listed on the MoF e-invoicing page (pack owner).
- SA `tax.filingPeriods`: ZATCA news states monthly filing above SAR 40 million annual supplies, quarterly at or below (lead for the pack row, needs accountant sign-off).
- QA: Minister of Labour Decision 50 of 2026 on WPS (SECONDARY), for G3 payroll.
- Sites that blocked automated fetch need a manual check: sandbox.zatca.gov.sa, laws.boe.gov.sa, gosi.gov.sa, uaelegislation.gov.ae, mohre.gov.ae, almeezan.qa.

## Tokens or cost
Unknown.

## Next step
CMP-020 (partner, G4) can take section 7 as its design input; CMP-036 and Q-601 can cite section 5.
