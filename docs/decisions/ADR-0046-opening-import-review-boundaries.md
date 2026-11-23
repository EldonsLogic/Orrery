# ADR-0046: Opening import review boundaries

Status: Proposed
Owner: partner
Approved by: pending; Tier 3 security and Eldon line-by-line review

## Context

The PR #202 cross-model review found that caller-supplied DSC-019 evidence could
hide quarantine, batch IDs could bypass opening idempotency, master overwrites
lacked prior-value evidence, and missing subledgers could bypass reconciliation.
This supplements the proposed [ADR-0045](ADR-0045-opening-import-transaction-boundary.md)
without accepting it or changing the rigid-zone human review requirement.

## Decision

Authenticate validate, preview and apply before traversing source data. The
backend supplies a mapped `opening_import` capability and exact tenant/company
scope from its trusted session; request roles never grant authority. Rerun the
read-only DSC-019 deterministic producer on submitted datasets with server-owned
master/opening field mappings, independently of supplied report assertions.
Return at most one safe error, indicating that further errors may be omitted;
bound each accumulating upstream invocation to 250 rows and a conservative
two-million-cell pairwise name comparison budget.

Resolve detail links against the batch and existing company-scoped masters.
Require trial-balance classification to match the resolved Account and refuse
changes to existing account classifications. Nonzero control lines require their
subledger, and subledger rows require the matching control and exact comparison.

Hash referenced master state and prior/next values into the preview. Recompute
inside the write transaction; journal before/after master snapshots alongside
writes. Serialize the opening claim per tenant/company, independent of batch ID
or posting date, including legacy opening records. No reversal/supersede path is
implied. Exact committed retries retain their original confirmation hash and
source digest. Roll back claims, master updates, detail rows and audit together.
Keep only the latest 256 sanitized failure attempts per tenant.

## Consequences

The generic importer no longer knows engine role names. SQLite retains an
explicit offline compatibility mapping for authenticated roles; the native
mapping requested under ADR-0039 is UNVERIFIED (that record is absent from the
checked main branch). [Q-303](../open-questions.md) tracks this and native Opening
Invoice Creation Tool / Journal Entry / Stock Reconciliation wiring. The supplied
backend remains an offline reference, with no ledger-posting claim. ERP-013 stays
doing. Live bulk-import limits and native transaction/link/role behavior require
review and synthetic runtime evidence before customer use.

## Alternatives rejected

- Trust an internally consistent caller report: no provenance or quarantine proof.
- Use batch ID alone: caller retries under new IDs can duplicate opening balances.
- Auto-correct or merge master names: owner review is required upstream.
- Separate audit and business transactions: cannot guarantee verbatim rollback.

## Supersedes

None. Adds review-driven constraints to proposed ADR-0045; neither is accepted.
