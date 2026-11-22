# ADR-0063: Country pack certification records

Status: Proposed
Owner: partner
Approved by: pending Tier 3 founder and cross-model security review
Plan ID: CMP-035

## Context
The founders resolved [Q-560](../open-questions.md) on PR #264: trusted adviser sources need accountant sign-off; certification needs a named accountant for the market and one founder; the loader must match pack status to the component manifest and name the reviewer. [ADR-0059](ADR-0059-draft-country-packs-in-sandbox.md) preserves the sandbox/test exception and records these production requirements. CMP-034 currently refuses all secondary evidence and trusts self-declared pack status.

## Decision
- Record `certification.accountant` (`name`, `market`, `signOffRef`) and `certification.founder` (`eldon` or `partner`) in the pack's existing `evidence.json`. Keep the reviewer in `manifest.json.certification.reviewedBy`, following [ADR-0034](ADR-0034-reviewed-level-needs-a-named-reviewer.md). The [framework](../compliance/country-pack-framework.md#certification-record-production-only) defines the format and synthetic example.
- In production, require this sign-off for both `verified_official` and `secondary` evidence, at both `certified` and `regulated`. Refuse blank/wrongly typed fields, the wrong market, missing founder approval, a status/manifest-level mismatch or an unnamed reviewer. Bind both companions to the pack's identity and exact version; refuse missing, unreadable or malformed records.
- Preserve the existing status floor, refusal of `unverified` and `testOnly`, strict environment selection, and no fallback past the latest refused version. Read certification companions only in production; sandbox/test remain synthetic-data-only under ADR-0059, enforced by the caller.

## Security and consequences
Deployment must supply trusted, reviewed pack files. These deterministic checks validate recorded approvals; they cannot establish accountant qualifications or authenticate a sign-off or founder identity. The publishing founder must verify those against the referenced evidence. Confidential material stays outside the public repo. No customer input or company override can supply certification records.

No contract changes, statutory maths, fact relabelling or promotion of shipped packs. Per-fact evidence tests and pinned source labels remain unchanged. A separate module holds companion checks to keep them isolated from override merging. Tier 3 line-by-line review and a different-model security review are required before merge; neither is claimed complete here.

## Alternatives rejected
- Add fields to pack.json or the component contract: unnecessary schema changes; evidence already lives beside the pack.
- Duplicate the reviewer in evidence.json: creates two reviewer records that could disagree.
- Apply certification checks in sandbox/test: would undo the accepted ADR-0059 exception.
