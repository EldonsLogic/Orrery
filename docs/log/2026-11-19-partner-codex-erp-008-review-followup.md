# Session log: erp-008-review-followup

Date: 2026-11-19
Author: partner
Tool and model: codex / gpt-6.1-sol
Plan IDs: ERP-008

## Summary
Closed remaining ERP-008 review gaps: external-store conflict is explicitly gated by Q-274, versioned sync uses a fresh authoritative snapshot, agent create/write restrictions and negative cases match the draft-only boundary.

## Files touched
- docs/decisions/ADR-0039-role-and-permission-mapping.md: clarified Proposed supersession and apply/sync fence.
- docs/architecture/role-and-permission-mapping.md: corrected transition metadata and added DENY-47/48.
- docs/open-questions.md: Q-274 requires founder resolution before implementation.

## Decisions
- ADR-0039 remains Proposed; ERP-008 stays doing and requires implementation plus bench evidence. No accepted ADR edited.
- Verification: check_docs.py, check_repo_hygiene.py, check_lanes.py (base origin/main, actor sayegh9), scan_secrets.py. DENY cases are design specifications, not runtime results.

## Tokens or cost
Unknown or approximate, if known.

## Next step
ERP-008: Eldon to resolve Q-274 and confirm existing ALP wording edits; independent security re-review and contract follow-ups before implementation.
