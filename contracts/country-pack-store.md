# Country pack store: publish record, index and pin

Version: 0.1.0
Status: draft (ADR-0071 Proposed, PR #344 under review)
Owner: eldon (publisher, CMP-038); consumer: partner (loader, CMP-039)

The shared formats between the staff pack publishing workflow (CMP-038) and the country pack loader (CMP-039). Eldon's answer to Q-656 (2026-11-26, on #344) moved them into `contracts/` before CMP-038 is built. The design is [ADR-0071](../docs/decisions/) (Proposed, on the CMP-039 branch); where it is still under review, these schemas follow its revision 2 text and Eldon's answers to Q-652 to Q-657.

| Document | Schema | Writer | Reader |
|---|---|---|---|
| Publish record (payload of a `cpr1.` envelope, `typ: country_pack_version`) | [country-pack-record.schema.json](country-pack-record.schema.json) | CMP-038 publish service | loader |
| Country index (payload of a `cpi1.` envelope, `typ: country_pack_index`) | [country-pack-index.schema.json](country-pack-index.schema.json) | CMP-038 | loader |
| Tenant pin (`typ: country_pack_pin`) | [country-pack-pin.schema.json](country-pack-pin.schema.json) | tenant registry (control plane) | loader, through `PinSource` |
| Shared field formats | [country-pack-common.schema.json](country-pack-common.schema.json) | - | - |

Examples: `examples/country-pack-{record,index,pin}-*.json` must validate; `examples/invalid/country-pack-*.json` must fail (both checked by `scripts/check_contracts.py`). Rules JSON Schema cannot express are listed in each schema's `x-validator-rules`; the record-local ones have a reference check in [tests/test_country_pack_contracts.py](tests/test_country_pack_contracts.py). All data is fictional.

## What the schemas fix
- **Digests:** `sha256:` plus 64 lowercase hex everywhere. `contentDigest` is over the RFC 8785 canonical JSON of `{countryCode, packId, version, files}`, each file hashed over its exact stored bytes (ADR-0071 1.2).
- **Closed file set:** `pack.json`, `manifest.json`, `evidence.json` once each, `strings.json` at most once, each 1 byte to 1 MiB.
- **Two sign-offs:** exactly two, one `market_accountant` and one `founder`, in either order. Different `signerId` values, different MFA assertion refs and `publishedBy` being a signer are validator rules (JSON Schema cannot compare array items).
- **Per-signer signatures (Q-652):** each sign-off may carry `signerSignature`, the signer's own WebAuthn assertion over `statementDigest`. When `keyEnv` is `production` both sign-offs must carry it and `mfa.method` must be `webauthn`; outside production the publisher key alone may publish, as Eldon's answer allows.
- **Urgent changes:** `changeKind: urgent` needs `followUp.required: true` and a `reviewRef`; `scheduled` must have `followUp.required: false` and no `reviewRef`.
- **Index:** `indexSeq` from 1, `predecessorDigest` (null only on the first index; it chains indexes so two different indexes cannot share a sequence), `published`, `withdrawn`, `floor`, `followUpOpen`, `changeRecords`.
- **Pin:** a store pin carries `contentDigest`, `publishId` and `indexSeqAtPin`; a repo pin (sandbox and test only) carries none of them. Rollback needs `founder_rollback` approval (one founder, step-up ref, reason ref; Q-655); every other store pin needs `accountant_boundary` approval naming the accountant-approved point (Q-657). Every pin carries one `auditId` end to end (#316 decision 6).
- **No extra properties** anywhere.

## Assumptions (to confirm in review)
1. Role names follow ADR-0071 1.4: `market_accountant` and `founder` (the CMP-038 row says "accountant").
2. The schemas describe the decoded JSON payloads only. The envelopes (`cpr1.`/`cpi1.`, base64url, ed25519 over a domain string plus the payload bytes, 64 KiB limit, strict parse) stay as ADR-0071 1.5 defines them.
3. The publisher key envelope stays in production alongside the per-signer signatures; per-signer signatures add to it, they do not replace it.
4. `signerSignature` format `webauthn.get.v1`: the WebAuthn challenge is the base64url of the 32 `statementDigest` bytes. Verifying it needs each signer's public credential in the reviewed `trusted_signers.json`; that file's format belongs to the loader (CMP-042) and is not in this contract.
5. Per-signer signatures on change records (withdrawal, floor raise, follow-up closure) are not specified here: the index lists change records by digest, and their body is CMP-038's next slice.
6. The index carries a new field, `predecessorDigest`, which ADR-0071 revision 2 does not have: it answers the review finding that two indexes with the same `indexSeq` must be refused, and matches the brief for this slice.
7. The pin adds `v`, `typ`, `auditId` and a structured `approval` (ADR-0071 3.1 has a flat `approvalRef`); `approval.ref` is that reference. `changedBy` is `{actorKind, subject, tokenId}`: the actor is staff or a service, never a tenant member, so `memberRef` does not apply; staff subjects go only to the platform security stream, never a tenant audit (#316 decision 2).
8. A repo pin uses approval `repo_draft` and cannot be a `republish`.
9. Identifiers: `publishId` is a ULID; `tenantId`, `kid`, refs and staff subjects are opaque strings with conservative patterns. Change them in review if the registry or identity system uses other formats.
10. The 7-day verified cache (Q-654), the audit write-through refusal (Q-656), the accountant roster (Q-653) and SEC-008's `AuditStore` are loader and registry behaviour; they shape no field here beyond `auditId`.
11. Packs carry no dated values (Q-657); nothing here adds one.

## Changelog
- 0.1.0 (CMP-038 slice 1): first draft of the record, index, pin and common schemas, with examples and negative examples.
