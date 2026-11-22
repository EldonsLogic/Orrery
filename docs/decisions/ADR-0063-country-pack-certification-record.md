# ADR-0063: Country pack certification records

Status: Proposed
Owner: partner
Approved by: pending Tier 3 founder and cross-model security review
Plan ID: CMP-035

## Context
The founders resolved [Q-560](../open-questions.md) on PR #264: trusted adviser sources need accountant sign-off; certification needs a named accountant for the market and one founder; the loader must match pack status to the component manifest and name the reviewer. [ADR-0059](ADR-0059-draft-country-packs-in-sandbox.md) preserves the sandbox/test exception and records these production requirements. CMP-034 currently refuses all secondary evidence and trusts self-declared pack status.

## Decision
- Amend [ADR-0059](ADR-0059-draft-country-packs-in-sandbox.md) Decision 2's production `verified_official` requirement: `secondary` is also eligible only under the recorded accountant and founder approvals below, implementing its Decision 3. Every other part of ADR-0059 stands, including the sandbox/test exception.
- Record `certification.accountant` (`name`, `market`, `signOffRef`) and `certification.founder` (`eldon` or `partner`) in the pack's existing `evidence.json`. Keep the reviewer in `manifest.json.certification.reviewedBy`, following [ADR-0034](ADR-0034-reviewed-level-needs-a-named-reviewer.md). The [framework](../compliance/country-pack-framework.md#certification-record-production-only) defines the format and synthetic example.
- The certification key set is closed: `certification` permits exactly `accountant` and `founder`; `accountant` permits exactly `name`, `market` and `signOffRef`. All are required; refuse any unknown key, including `revoked`. Accountant names, sign-off references and reviewer entries must contain a letter or digit after NFKC normalization and removal of Unicode `Cf` characters; reviewer entries must also satisfy the component contract's GitHub login grammar.
- In production, require this sign-off for both `verified_official` and `secondary` evidence, at both `certified` and `regulated`. Refuse blank/wrongly typed fields, the wrong market, missing founder approval, a status/manifest-level mismatch or an unnamed reviewer. Validate the entire companion manifest against the component contract, including formats, and refuse owner self-review case-insensitively (ADR-0034). Missing validation dependencies or an unavailable/invalid contract fail closed. Bind both companions to the pack's identity and exact version; refuse missing, unreadable or malformed records.
- In production, the evidence lock set is the union of `tax`, `eInvoicing`, `payrollHooks` and the pack's `overridesPolicy.lockedPaths`; policy locale paths are relative to `localeDefaults`. A pack cannot reduce that minimum set. Every leaf value beneath each locked path present in the pack requires at least one fact with a known status other than `UNVERIFIED`, naming that leaf or an ancestor. Walk objects; treat whole arrays (including empty arrays), scalars and nulls as leaves, matching today's shipped evidence files. Indexed array facts alone cannot cover the whole array.
- Refuse any `UNVERIFIED` fact on a locked path, an ancestor or a descendant, even when another fact provides accepted coverage. Refuse every fact path that does not exist in the pack, including paths outside locked areas; fact paths use full pack-root dotted paths, unlike locale-relative policy paths. Missing or unusable fact records also fail closed.
- A `SECONDARY` fact overlapping a locked path in either direction requires at least one read source with an access date; validate all its sources using the shipped-pack tests' source rule (HTTPS URL, ISO access date no later than today, or `read: false` with a note and no date; unread-note backstop). Share evidence labels, leaf traversal, path resolution, coverage and source validation with those tests. Accountant sign-off never relabels a fact. The reviewed `SOURCED_LABELS` snapshots remain unchanged.
- Preserve the existing status floor, refusal of `unverified` and `testOnly`, strict environment selection, and no fallback past the latest refused version. Read certification companions only in production; sandbox/test remain synthetic-data-only under ADR-0059, enforced by the caller.

## Security and consequences
Deployment must supply trusted, reviewed pack files. These deterministic checks validate recorded approvals; they cannot establish accountant qualifications or authenticate a sign-off or founder identity. The publishing founder must verify those against the referenced evidence. Confidential material stays outside the public repo. No customer input or company override can supply certification records.

No contract changes, statutory maths, fact relabelling or promotion of shipped packs. Per-fact evidence tests and pinned source labels remain in force. Separate modules hold companion checks and shared evidence traversal to keep them isolated from override merging. Tier 3 line-by-line review and a different-model security review are required before merge; neither is claimed complete here.

## Alternatives rejected
- Add fields to pack.json or the component contract: unnecessary schema changes; evidence already lives beside the pack.
- Duplicate the reviewer in evidence.json: creates two reviewer records that could disagree.
- Apply certification checks in sandbox/test: would undo the accepted ADR-0059 exception.
