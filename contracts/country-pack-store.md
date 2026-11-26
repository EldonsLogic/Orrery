# Country pack store: publish record, index and pin

Version: 0.4.0
Status: draft (ADR-0071 Proposed, PR #344 under review)
Owner: eldon (publisher, CMP-038); consumer: partner (loader, CMP-039)

The shared formats between the staff pack publishing workflow (CMP-038) and the country pack loader (CMP-039). Eldon's answer to Q-656 (2026-11-26, on #344) moved them into `contracts/` before CMP-038 is built. The design is [ADR-0071](../docs/decisions/) (Proposed, on the CMP-039 branch); where it is still under review, these schemas follow its revision 2 text and Eldon's answers to Q-652 to Q-657.

| Document | Schema | Writer | Reader |
|---|---|---|---|
| Publish record (payload of a `cpr1.` envelope, `typ: country_pack_version`) | [country-pack-record.schema.json](country-pack-record.schema.json) | CMP-038 publish service | loader |
| Country index (payload of a `cpi1.` envelope, `typ: country_pack_index`) | [country-pack-index.schema.json](country-pack-index.schema.json) | CMP-038 | loader |
| Change record (withdrawal, floor raise, follow-up closure; listed in the index by id, kind and sha256) | [country-pack-change-record.schema.json](country-pack-change-record.schema.json) | CMP-038 | loader (CMP-039 must read it) |
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
4. `signerSignature` format `webauthn.get.v1`: the WebAuthn challenge is the 32 bytes SHA-256(`country-pack-signoff-v1` + LF + the ASCII `statementDigest`), base64url without padding in `clientDataJSON.challenge` (domain separated, ADR-0071 1.8; Eldon's #344 answer). The same rule signs change record sign-offs. Verifying it needs each signer's public credential in the reviewed `trusted_signers.json`; that file's format belongs to the loader (CMP-042) and is not in this contract.
5. Change records (withdrawal, floor raise, follow-up closure) are defined by [country-pack-change-record.schema.json](country-pack-change-record.schema.json): `id`, `kind`, `countryCode`, `target` (`{version}` or, for a closure, `{publishId}`), `reasonRef`, `baseIndexSeq`, `baseIndexDigest`, `statementDigest`, `requestedBy`, `recordedAt` and the same two `signOffs` as a publish (one `market_accountant`, one `founder`, different people, different step-ups, each signed over `statementDigest`, per-signer signatures in production). The statement is the digest of the canonical JSON of `{op: "pack_change", countryCode, kind, target, reasonRef, baseIndexDigest}`, so a change is bound to the exact index it was proposed against. The index's `changeRecords[].sha256` is the digest of the record's canonical JSON; the next index has `indexSeq` equal to `baseIndexSeq` plus 1. Per market only, no tenant fields. **CMP-039 (the pack loader, PR #344) must read this record**, check its two sign-offs like a publish's, and check that the index change it lists (withdrawal moved, floor raised, follow-up closed) matches `kind` and `target`. A tenant-member actor (`memberRef`) is out of scope for pin approvals. The publisher validates each record against the schema and the rules in `x-validator-rules` before it commits (refusal PP-062).
6. The index carries `predecessorDigest` (digest of the exact payload bytes of the previous index): it refuses two indexes with one `indexSeq` and lets a loader that is behind walk back through the signed index chain to its last verified index, verifying each index and the change records it lists (Eldon's #344 answer). An index need not re-list changes since a loader's last state. A withdrawal clears that version's open follow-up in the same record.
7. The pin adds `v`, `typ`, `auditId` and a structured `approval` (ADR-0071 3.1 has a flat `approvalRef`); `approval.ref` is that reference. `changedBy` is `{actorKind, subject, tokenId}`: the actor is staff or a service, never a tenant member, so `memberRef` does not apply; staff subjects go only to the platform security stream, never a tenant audit (#316 decision 2).
8. A repo pin uses approval `repo_draft` and cannot be a `republish`.
9. Identifiers: `publishId` is a ULID; `tenantId`, `kid`, refs and staff subjects are opaque strings with conservative patterns. Change them in review if the registry or identity system uses other formats.
10. The 7-day verified cache (Q-654), the audit write-through refusal (Q-656), the accountant roster (Q-653) and SEC-008's `AuditStore` are loader and registry behaviour; they shape no field here beyond `auditId`.
11. Packs carry no dated values (Q-657); nothing here adds one.
12. **Republish of an urgent version (#344 re-review L2):** a publish for a version whose urgent record still has its `publishId` in the index's `followUpOpen` is refused (fail closed, PP-063) until a follow-up closure record closes that follow-up. `followUpOpen` therefore only ever holds ids of published records, and no `supersedes` swap can drop one. A withdrawal of that version still clears the follow-up in its own record (assumption 6).
13. **Owners (#344 re-review L3):** `minIndexSeq`, the repo pin, the cohort and the `check_upgrade` caller belong to Eldon's lane (control-plane), under the tenant version pin row (Q-677), plan row CMP-047. The loader (CMP-039) reads them; it does not write them.

## Changelog
- 0.4.0 (CMP-038 slice 4): assumption 12 (republish of an urgent version with an open follow-up is refused, PP-063) and assumption 13 (owners of the pin fields); no schema change, backward compatible.- 0.1.0 (CMP-038 slice 1): first draft of the record, index, pin and common schemas, with examples and negative examples.
- 0.3.0 (CMP-038 slice 4): adopts the partner's domain-separated WebAuthn challenge (Eldon's #344 answer, Q-656); not backward compatible for any `signerSignature` made over the raw digest (none exist, major is 0). Documents `predecessorDigest` as the chain a behind loader walks. Schema `$id`s stay at 0.1.0 (description-only change).
- 0.2.0 (CMP-038 slice 4): change record body and schema (assumption 5 replaced); minor, backward compatible for existing records, indexes and pins.
