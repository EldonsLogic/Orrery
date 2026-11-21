# Session log: zatca-app-adr

Date: 2026-11-18
Author: partner
Tool and model: claude-code / opus-5.5
Plan IDs: CMP-033

## Summary
Drafted ADR-0037 (Proposed): the founder's hybrid decision for ZATCA Phase 2. Vendor the ERPGulf app's pure-Python core (key and CSR generation, UBL builders, canonicalisation, hashing, signing, TLV). Rebuild the hash chain and counter, the clearance and reporting outbox and all engine hooks. The ADR adds the CMP-004 constraint checklist, the code placement, upstream fix tracking, reviewer notes and open questions. No code. CMP-033 stays `doing` until the partner accepts.

## Files touched
- `docs/decisions/ADR-0037-zatca-phase-2-vendor-core-rebuild-state.md`: new ADR, Proposed.
- `docs/decisions/INDEX.md`: added the ADR-0037 row. ADR-0036 is taken by open PR #120.
- `docs/compliance/zatca-erpgulf-evaluation.md`: one-line link to ADR-0037 in section 5.
- `docs/PLAN.md`: CMP-033 `todo` -> `doing`.

## Evidence gathered
- Upstream licence re-checked: MIT via the GitHub API and `LICENSE` (accessed 2026-11-18). Upstream `main` head is `015eaf80b7d2a910c73a2eca553bbafa1410dbfa` (2026-11-16). Tag `v3.0.1` is `d906ba7`.
- Read seven upstream files at that commit through `gh api`, without running them. Function names and line numbers in the ADR come from that read.
- New findings beyond CMP-002, all recorded in the ADR's Reviewer notes:
  - The "pure" functions read keys and documents from engine records.
  - The XML builders recompute VAT and use a non-standard `custom_round`, which conflicts with ADR-0031.
  - `get_tlv_for_value` measures string length in characters, not UTF-8 bytes, which breaks Arabic values.
  - The ICV is derived from the invoice name's digits.
  - Private keys are stored as unencrypted PEM in document fields.

## Model and prompt (ADR-0031 condition 4, for the record; this PR has no rigid-zone code)
Model: Claude Opus 5.5 in Claude Code. Brief: "Plan row CMP-033: write the decision ADR for the ERPGulf ZATCA app. The founder's proposed decision is the hybrid: vendor the pure-Python core, rebuild everything that touches state. Write it up faithfully, put any disagreement in Reviewer notes, and state the code placement, upstream fix tracking, CMP-004 constraints and open questions. Status Proposed."

## Decisions
- ADR-0037 proposed. It waits for the partner's acceptance and the other founder's review (Tier 2, ADR-0035).

## Tokens or cost
Unknown.

## Next step
- Partner: accept or amend ADR-0037 and answer its five open questions. Then mark CMP-033 `done`.
- Then the vendoring import PR with PROVENANCE.md, followed by CMP-004.
