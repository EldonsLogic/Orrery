# Session log: cmp-033-zatca-adr-amendments

Date: 2026-11-18
Author: partner
Tool and model: antigravity / gemini-4-hydrogen
Plan IDs: CMP-033

## Summary
Merged `origin/main`, renumbered the ZATCA Phase 2 ADR from `ADR-0037` to `ADR-0042` (`ADR-0037` is taken on `main`, `0038`–`0041` by `#128`, `#129`, `#144`, `#126`), recorded the founder's pilot-only fallback signer policy as a dated note, and addressed all 11 findings from the cross-model review on PR #124.

## Changes made
- Renamed `docs/decisions/ADR-0037-zatca-phase-2-vendor-core-rebuild-state.md` to `docs/decisions/ADR-0042-zatca-phase-2-vendor-core-rebuild-state.md` and updated `docs/decisions/INDEX.md` and `docs/compliance/zatca-erpgulf-evaluation.md`.
- Updated `CMP-004` dependencies in `docs/PLAN.md` to `CMP-003,CMP-033,SEC-002` (separating G1 `SEC-002` sandbox custody from G3 `SEC-011` production custody).
- Closed Open Question 2 in `ADR-0042`: prohibited vendoring upstream tax/total arithmetic (`xml_tax_data.py` and `create_xml_final_part.py`) and dropped `csr_configuration.py` sandbox `TST` defaults, `createxml_advance.py`/`advance_payment.py` (out of G1), and upstream `get_tlv_for_value`.
- Added explicit `Sales Invoice` vs immutable `ZATCA Submission` state machine (B2B clearance hold vs B2C reporting rectification), EGS unit resolution + `"0"` genesis PIH, final-`on_submit` row-lock placement, immutable `signed_xml` outbox replay + `202`/`303`/`409` handling, UTC 24h anchor + post-24h late reporting, official ZATCA SDK offline validator gate (C14N 1.1, DOM `<xades:SignedProperties>` hash, QR Tags 1–9), mixed licence / `docs/legal/licence-register.md` rules, tightened concurrency/no-I/O test checklist, and updated upstream line citations.
- Appended `## Dated notes` (`2026-11-18`): fallback in-process signer key allowed for the first pilot only (encrypted at rest, readable only by the signer process, replaced before G3), while `CMP-004` must test a non-exportable KMS/HSM key.

## Verification
- Ran `python3 scripts/check_docs.py`, `python3 scripts/check_repo_hygiene.py`, `python3 scripts/scan_secrets.py --all`, `python3 scripts/check_lanes.py --base origin/main --head HEAD --actor partner`, and `python3 scripts/check_pr_trail.py --base origin/main --head HEAD`.
