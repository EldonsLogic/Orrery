# ADR-0024: Four phase-1 markets, no fixed launch order

Status: Accepted
Owner: eldon
Approved by: Eldon (founder decision, 2026-11-07; first leads are in Qatar, Egypt confirmed for phase 1)

## Context
ADR-0012 (D-P2-2) recorded KSA first and UAE second, and ADR-0015 added Egypt third with "launch order KSA, UAE, Egypt". That order came from the Phase 2 research recommendation, built on the original brief ("Launch country: KSA and/or UAE"), and was approved as written. The founder now states the reality: phase 1 operates in Saudi Arabia, the UAE, Egypt and Qatar, and the first two leads are in Qatar. The partner (a cofounder) questioned the KSA-first wording.

## Decision
- Phase 1 operates in four markets: Saudi Arabia (SA), the UAE (AE), Egypt (EG) and Qatar (QA).
- There is no fixed launch order. Which market goes live first is decided by lead readiness and compliance readiness (verified research, country pack built), recorded in a log or ADR when it matters, never assumed in rules or code.
- Egypt and Qatar regulations are research needed. No Qatar or Egypt fact enters the product without a source and access date; placeholders are marked UNVERIFIED.
- Each market is a country pack (ADR-0015). Qatar gets its own research, pack and counsel scope. Hosting and identity-store questions (Q-9, Q-14) now cover four countries.
- The niche (trading and distribution) is the lead hypothesis and the first template, not a restriction. Later templates follow the leads; any niche is served through templates and components, never client-specific code (ADR-0008).
- The Blueprint contract already allows country code QA; its descriptions now name SA, AE, EG and QA.

## Alternatives rejected
- Keep KSA first and add Qatar later: contradicts the founder's leads and would hold the rules and code to a false order.
- Treat all four as one build wave with equal completeness now: Egypt and Qatar rules are unresearched; the pack for each is built when its research is verified.

## Consequences
- Rules, agent instructions and docs say four markets and no launch order (RULES 29, AGENTS.md, START-HERE, PRD, overview).
- Plan: Qatar research and pack rows, Egypt research and pack moved earlier, counsel and entity scope cover Qatar, Qatar go-to-market assessment (CMP-030, CMP-031, GTM-019, LEG-003, LEG-008, LEG-010, CMP-027, CMP-028, GTM-017).
- Code defaults and the template instantiator accept QA with UNVERIFIED placeholders.
- Counsel and hosting choices must cover Qatar before any Qatar customer data is stored.

## Supersedes
The launch order in ADR-0012 (D-P2-2) and ADR-0015. The rest of both ADRs stands.
