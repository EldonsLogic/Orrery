# Session log: dat-001-classification-retention

Date: 2026-11-16
Author: eldon
Tool and model: claude
Plan IDs: DAT-001

## Summary
Drafted the data classification (five classes C0 to C4 plus a personal-data tag, decision rule, handling matrix, 24-row assignment table) and the retention policy (per-market statutory tables for Saudi Arabia, the UAE, Egypt and Qatar, legal hold, offboarding, backups, AI retention, 12 decisions).

Evidence quality, stated plainly: of 37 statutory rows, 9 are read from official text, 6 from non-official copies of the article, 6 secondary and 16 UNVERIFIED. Qatar has no verified row; payroll and employment-record periods are unverified in all four markets. Unverified rows ship as "unset" and block automatic deletion. Counsel (LEG-003) must confirm the per-country figures before launch; this policy is not legal advice.

Model and prompt: written by a subagent (Fable 5.2) from a scoped brief (two allowed files, required sections, rule that every statutory figure is verified with URL and access date or marked UNVERIFIED). The orchestrator checked scope and ran the doc checks; it did not re-verify the statutory figures.

## Files touched
- docs/security/data-classification.md: expanded
- docs/security/data-retention.md: new
- docs/security/hosting-rules.md, docs/runbooks/README.md: links
- docs/PLAN.md: DAT-001 done

## Decisions
- Founder decisions are listed in both documents (accept C4 and the PD tag; whether C3 may reach a model provider; all offboarding, export, deletion and backup time limits; log and transcript retention; whether counsel confirmation blocks the Qatar pilot).

## Tokens or cost
Unknown or approximate, if known.

## Next step
Update the compliance docs the subagent listed (country-matrix K9/U16/E10, data-protection-and-residency, e-invoicing line 17, research/03, architecture/data.md, ai-layer memory section; U16 "15 years real estate" conflicts with the 7-year text read). Add the numbered open questions to docs/open-questions.md. Add a plan row for data-subject request tooling (find, export, restrict, erase). CMP-001 re-verifies the UNVERIFIED rows; LEG-003 gets counsel.
