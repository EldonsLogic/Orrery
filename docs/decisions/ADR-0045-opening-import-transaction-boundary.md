# ADR-0045: Opening import identity and transaction boundary

Status: Proposed
Owner: partner
Approved by: pending; Tier 3 cross-model, security and Eldon line-by-line review

## Context

ERP-013 consumes read-only DSC-011 rows and DSC-019 quarantine reports. Opening
balances fall inside [ADR-0031](ADR-0031-rigid-zone-code-authorship.md). Existing
adapter operations include independent commits and configuration changes; wrapping
those operations in a new journal cannot establish atomic financial imports.
[ADR-0027](ADR-0027-human-floor-action-policy-and-agent-authority.md) and
[ADR-0028](ADR-0028-recoverable-journaled-change-apply.md) remain Proposed; this
implementation does not accept or broaden them.

## Decision

Keep validation/preview pure and inject a server-owned `ImportBackend` into the
importer. Never expose role or backend selection in input. Apply authenticates a
human for the exact tenant/company, checks the approved hash, and writes records
and a unique tenant/batch journal in one backend transaction. All financial sums
use bounded exact Decimal arithmetic; stock comparison uses ADR-0033 half-up
rounding without changing source values. Canonical approval includes source
report, context, rows and precision. The complete DSC-019 report is mandatory;
quarantine and unresolved owner review block every write.

The delivered SQLite backend is explicitly an offline reference implementation,
using the adapter's durable-store pattern. It proves local transaction rollback,
restart idempotency and competing-writer exclusion. It does not create native
ledger postings or imply live engine transaction guarantees. No public endpoint,
role grant, schema contract or provisioning behavior is changed.

## Alternatives rejected

- Separate journal and business databases: crash between commits can double-post.
- Replay existing independently committing configuration operations: cannot roll
  back the complete batch.
- Adopt only accepted rows or duplicate suggestions: silently alters the source.
- Implicit simulated fallback: conceals an unavailable runtime.

## Consequences

ERP-013's implementation PR is Tier 3. Cross-model/security and Eldon's human
line-by-line review remain mandatory. Production wiring must supply and verify a
native transactional writer, live account/link permission checks, reconciled
stock/subledger/control posting and the approval lifecycle before customer use.
The reference tests are synthetic regressions, not official conformance vectors.
Arabic strings remain explicitly unreviewed pending ADR-0033 review.

## Supersedes

None.
