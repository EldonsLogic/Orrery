# Session log: sec-018-brand-upload-security

Date: 2026-11-17
Author: eldon
Tool and model: claude
Plan IDs: SEC-018

## Summary
SEC-018: expanded the brand asset upload security spec (259 lines): requirement IDs BAU-001 to BAU-103 (79 table rows) covering type and polyglot checks, limits and decompression bombs, raster re-encoding, SVG sanitising and serving, malware scan and quarantine, per-tenant storage isolation, derived variants, access, audit and rate limits, filenames; 32 attack and test cases; a map to SEC-006, BRD-007, BRD-008, WEB-007 to WEB-009, PLT-017, PLT-018, QA-008. Ten decisions (BD-1 to BD-10) and eight open questions are listed in the document; all numeric limits are proposals.

Evidence quality: only the OWASP File Upload and XXE cheat sheets were verified (neither covers SVG, so applying XXE guidance to SVG is our inference); SVG serving and CSP guidance, browser behaviour, sanitiser mutation resistance and all numbers are UNVERIFIED.

Model and prompt: Claude Sonnet subagent from a scoped brief (one allowed file; requirements, attack cases, sources marked UNVERIFIED when unchecked). Orchestrator checked scope and the doc gate; did not re-verify sources.

## Files touched
- docs/security/brand-asset-upload-security.md: expanded
- docs/PLAN.md: SEC-018 done

## Decisions
- Decisions BD-1 to BD-10 in the document.

## Tokens or cost
Unknown or approximate, if known.

## Next step
SEC-006 enforces this spec; QA-008 turns the attack cases into tests.
