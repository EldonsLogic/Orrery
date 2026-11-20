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
`Decision` (approved or changes_requested, note required for changes) and `Comment` are immutable records bound to the tenant and the digest of the exact Blueprint.

**Digest (canonical form).** SHA-256 of the Blueprint JSON without `meta.buildState` (the control-plane mirror, so a state transition never stales a sign-off), with sorted keys, compact separators, non-ASCII kept, no NaN or Infinity, UTF-8 (`view.canonical`, pinned by a test). `meta.revision` and `meta.id` are bound. The digest is representation-sensitive (`50000` and `"50000"` differ): that only stales decisions, never the other way. NaN, lone surrogates and absurd nesting are refused with `ACV-BP-002`.

**Rules.** Follow BPL-019 sign-off: human signer only, tenant-bound, `accountant` role, a signer who also holds the owner role is refused (`ACV-SO-010`, Q-373), caller-supplied clock with 5-minute skew and a 2000 to 2099 range, append-only. Per digest and section: the first decision is free; a `changes_requested` may follow an `approved` (a rejection beats an approval); nothing follows a `changes_requested`; a second `approved` is refused. The writer validates the record with the same check the reader uses.

**Reading is fail-closed per record.** Records of another tenant refuse the whole read. A malformed record (non-clean note or comment text, impossible date, wrong types), a decision on a section that cannot be signed, an out-of-order or duplicate decision, or a repeated comment id is quarantined: skipped, counted in `overall.quarantined`, never rendered, and the view still builds. Recovery of quarantined rows is an operations task on the store.

**Stale history.** Records bound to an earlier digest are not counted, but stay visible in `history` (marked `stale`), and a `changes_requested` with no newer decision on that section is shown as `signOff.openChangeRequest` and listed in `overall.openChangeRequests`, so a trivial edit cannot hide an objection and its note.

**Overall.** `approved` only when every section is signable and approved. When chart of accounts or posting rules are not in the Blueprint (Q-370) the best state is `approved_signable_only`, with `overall.notReviewed` listing them. DSC-009 and BPL-020 must not treat that as a ledger sign-off until Q-370 closes. `evidenceOnly` is always true; nothing here moves a build state.

**Threshold units.** Guard values are read as major units of the company currency (country default currency when omitted, `currencySource`). Money fields (also through `relation.field`, and each item of `in`/`not_in`) become integer minor units; percent fields basis points; a float on any other field is refused; a number on a field whose type cannot be resolved is `unknown_unit` (the screen shows a warning). Q-372 stays open until the Blueprint types the guard unit.

Persistence needs unique keys on (tenant, digest, section, sequence) for decisions and (tenant, comment_id) for comments, and should assign comment ids itself. Untrusted text is flagged per field (`untrustedFields`, `untrustedText`); the screen escapes it and isolates it with `<bdi>`. `Signer` duplicates the simulator's type until Q-371 gives one verified-principal type and fixes the `accountant` role id.

## Follow-up (not in this slice)
Web screen under `web/app/src/` following the DSC-007 viewer (`components/blueprint/`): render `build_review` output, merge `labels.json` into `messages/{ar,en}.json`, logical CSS properties and tokens only, escape all `untrustedText` values. Needs the gateway route that builds `Signer` from identity claims and a store for records (Q-371, Q-372).
