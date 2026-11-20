# Accountant review view (DSC-016)

Status: draft. Slice built: the view-model and sign-off service in `services/discovery/accountant_view/`. Not built: the web screen (see Follow-up).

## What the accountant sees
Six read-only sections taken from the Blueprint 0.4.0, in this order: chart of accounts, tax and VAT, e-invoicing, approval thresholds, posting rules, document numbering. The owner edits the Blueprint (DSC-004, DSC-009); the accountant never edits it.

| Section | Source in the Blueprint | Signable |
|---|---|---|
| Chart of accounts | none in 0.4.0; shows the country pack reference | no (`not_in_blueprint`) |
| Tax and VAT | `compliance.vat`, `company.vatNumber`, `compliance.countryPack` | yes |
| E-invoicing | `compliance.eInvoicing` | yes |
| Approval thresholds | `approvals[]`; money conditions converted to integer minor units in `company.locale.currency` | yes (also when empty) |
| Posting rules | none in 0.4.0; shows components that implement entities | no (`not_in_blueprint`) |
| Numbering | `entities[].numbering`; document entities without numbering are flagged | yes |

## Recording
`Decision` (approved or changes_requested, note required for changes) and `Comment` are immutable records bound to the tenant and the SHA-256 digest of the exact Blueprint. Rules follow BPL-019 sign-off: human signer only, tenant-bound, `accountant` role, caller-supplied clock with 5-minute skew limit, append-only, final per (digest, section), stale when the Blueprint changes, stored records validated and fail closed. Persistence needs unique keys on (tenant, digest, section) and on comment id.

Authority: the result is evidence for the owner approval flow (DSC-009) and BPL-020 (ADR-0027, human floor). `overall.evidenceOnly` is always true; nothing here moves a build state. Because a sign-off records a human accounting decision, the PR is Tier 3 for the approval-authority path (see PR).

## Follow-up (not in this slice)
Web screen under `web/app/src/` following the DSC-007 viewer (`components/blueprint/`): render `build_review` output, merge `labels.json` into `messages/{ar,en}.json`, logical CSS properties and tokens only, escape all `untrustedText` values. Needs the gateway route that builds `Signer` from identity claims and a store for records (Q-371, Q-372).
