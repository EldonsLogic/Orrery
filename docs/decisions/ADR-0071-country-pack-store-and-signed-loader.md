# ADR-0071: The country pack loader reads signed, published pack versions from the pack store, pinned per tenant, and fails closed

Status: Proposed
Owner: partner
Approved by: pending (security review by a different model, then Eldon line by line; RULES 42 because this touches compliance, keys and the audit trail)

Plan ID: CMP-039 (design only; no code until this ADR is reviewed). Interface partner: CMP-038 (staff pack publishing, Eldon). Items marked **(P)** are proposals Eldon can change; the questions are Q-652 to Q-657. Internal document.

## Context
- Today the loader reads `<packs_dir>/<country>/<version>/pack.json` from the repo (`components/compliance/country_pack/loader.py`, `load_country_pack`). In production the go-live gate (CMP-034 to CMP-036; [ADR-0063](ADR-0063-country-pack-certification-record.md), [ADR-0067](ADR-0067-country-pack-production-blockers-and-product-choice.md)) checks the certification records in `manifest.json` and `evidence.json`, which `certification.py` reads again from the same directory (`certification_refusals(pack, directory)`).
- ADR-0063 says plainly that these checks "validate recorded approvals; they cannot establish accountant qualifications or authenticate a sign-off or founder identity". Nothing proves that the files the loader reads are the files the two people approved.
- `environment`, `version` and `allow_unpinned` are caller arguments (`resolve_country_pack`; `components/compliance/company_calendar/settings.py` passes them through). Without a version, `load_country_pack` picks the highest version in the directory.
- CMP-038 (Eldon, G3) builds the publishing workflow: a draft version with evidence, a diff, two sign-offs (a named accountant plus a founder, never the same person, MFA), publish, scheduled tenant upgrades and an urgent path with a mandatory follow-up review. The platform spec gives the tenant registry the pinned pack version and asks for canary and rollback of pack upgrades ([../specs/05-platform.md](../specs/05-platform.md) item 9 and its tenant registry; [../architecture/country-packs.md](../architecture/country-packs.md) compiler step 5 stores the resolved locale with the compiled artifact).
- Signing keys stay in the KMS behind ADR-0038's `Signer` ([ADR-0038](ADR-0038-secrets-management.md) item 2). ADR-0068 (Proposed, PR #309, not on main) uses the same shape for its DDL grant: ed25519 in the KMS, verifier holds public keys by `kid`, canonical JSON payload. Step-up MFA is an MFA sign-in within 300 s; action-bound step-up (F2) and WebAuthn (F1) are not built ([ADR-0047](ADR-0047-mfa-design.md) item 4 and follow-ups).
- Founder decisions on PR #316 (2026-11-25): (1) SEC-008 owns the audit record format and the `AuditStore` port; (3) platform security events go to a separate in-country platform security stream owned by SEC-008, kept out of the tenant audit.
- Lanes: `components/` is the partner's; `services/control-plane/` (publisher, tenant registry) and `contracts/` are Eldon's (`scripts/lanes.json`). ADR-0025: a row never depends on the other founder's row in the same or a later gate.

## Decision

### 0. Words
- **Pack store**: the versioned store CMP-038 writes and the loader reads. Its product and location are CMP-038's choice; the loader sees it only through a read port.
- **Bundle**: the files of one pack version. **Record**: the signed published pack version record. **Index**: the signed per-country list of published, withdrawn and follow-up states plus the floor. **Pin**: the tenant registry's choice of version for one tenant.
- **Site class**: `sandbox`, `test` or `production` (ADR-0059, ADR-0068). **Key environment**: the deployment the signing key belongs to (`production`, `staging`, `dev`; ADR-0018 keeps them separate).

### 1. Interface between CMP-038 (publisher) and CMP-039 (loader)
1.1 **(P) Closed file set.** A bundle is exactly `pack.json`, `manifest.json`, `evidence.json` and, only where the version has one, `strings.json`. No other name, no directories, each file at most 1 MiB, UTF-8 without a byte order mark. The loader refuses a bundle with a missing required file or any extra file (`file_set_invalid`).

1.2 **(P) Content digest over exact bytes, not re-serialised JSON.** For each file, `sha256` over its exact stored bytes. Then `contentDigest = "sha256:" + hex(sha256(C))`, where `C` is the canonical JSON (UTF-8, keys sorted, no insignificant whitespace, integers only) of `{"countryCode", "packId", "version", "files": [{"path", "sha256", "size"}]}` with `files` sorted by `path`. The shipped packs hold no fractional numbers today, but a future rate might; hashing exact bytes avoids any number or Unicode canonicalisation question. The loader reads each file once into memory, hashes those bytes and parses those same bytes; every later check, including the existing gate, runs on the in-memory bundle and never reads the store or a disk path again.

1.3 **(P) Published pack version record** (`typ: country_pack_version`). Every field is required unless marked optional; unknown keys refuse.

| Field | Content |
|---|---|
| `v`, `typ`, `kid` | `1`; `country_pack_version`; the signing key id |
| `keyEnv` | `production`, `staging` or `dev`; must equal the key's environment in the trust file and the loader's deployment |
| `publishId`, `publishedAt`, `publishedBy` | The publish record: ULID; RFC 3339 UTC time the publish service signed; staff subject who triggered the publish, which must be one of the two `signerId`s (so a third person cannot publish what two others approved without being recorded) |
| `packId`, `countryCode`, `componentId`, `version` | as in `pack.json`; must match it byte for byte after parse |
| `contentDigest`, `files` | 1.2 |
| `predecessor` | `{version, contentDigest}` of the previous published version of this pack, or `null` for the first; `version` must be strictly greater by the loader's semver order |
| `changeKind` | `scheduled` or `urgent` |
| `followUp` | `{required: true, reviewRef}` when `urgent`; `{required: false}` otherwise |
| `diffDigest` | `sha256:` of the diff the signers were shown (CMP-038 defines the diff; the loader only binds it) |
| `evidenceRefs` | at least one `{id, sha256}` naming CMP-038 evidence items; the loader checks shape, never fetches |
| `signOffs` | exactly two entries, item 1.4 |

1.4 **(P) Sign-off entry.** `role` (`market_accountant` or `founder`), `signerId` (stable staff identity subject), `signedAt`, `statementDigest`, `mfa: {assertionRef, method, authTime}`; for the accountant also `name` and `market`; for the founder also `founderLogin`. `statementDigest` = `sha256:` of the canonical JSON of `{packId, version, contentDigest, diffDigest, changeKind}`: each person signs off this exact content and diff. `assertionRef` points to the step-up event in the identity audit.

1.5 **(P) Envelope and signature.** Token = `cpr1.` + base64url without padding of the payload + `.` + base64url without padding of the signature. The payload is canonical JSON as in 1.2, at most 64 KiB, parsed strictly: duplicate keys, unknown or missing keys, fractions, exponents, integers outside 0 to 2^53-1 and padding refuse. The ed25519 signature covers the ASCII bytes `country-pack-record-v1\n` followed by the payload bytes, so a signature from another key or record type (for example ADR-0068's grant) cannot verify here. The index (1.6) uses the same envelope with prefix `cpi1.` and domain string `country-pack-index-v1\n`.

1.6 **(P) Country index, floor and withdrawal** (`typ: country_pack_index`, one per key environment and country). Fields: `v`, `typ`, `kid`, `keyEnv`, `countryCode`, `indexSeq` (integer, plus one on every change), `issuedAt`, `published` (list of `{version, contentDigest, publishId}`), `withdrawn` (list of `{version, contentDigest, reasonRef}`), `floor` (lowest version any tenant may be pinned to), `followUpOpen` (list of `publishId`), `changeRecords` (list of `{id, kind, sha256}` for every withdrawal, floor raise and follow-up closure). CMP-038 issues a new index on every publish, withdrawal, floor raise and follow-up closure. A withdrawal, a floor raise and a follow-up closure need the same two-person sign-off as a publish, carried in a signed change record the index lists by id (CMP-038 defines its body; the loader checks only the index). Rules the loader enforces: `withdrawn` entries never leave the list; `floor` never falls; `indexSeq` never falls below the highest it has verified for that country (its high-water mark, kept in the loader's verified state, item 6).

1.7 **(P) Keys.**
- A new KMS ed25519 key, inventory entry "country pack publish signing key"; the SEC-002 owner assigns its `S` number (ADR-0068 proposes `S24` on an unmerged PR, so no number is taken here). Used only through ADR-0038's `Signer`; only CMP-038's publish service workload identity may sign; key administration is a separate identity (SEC2-019). Production, staging and dev keys are separate.
- Verification keys live in a reviewed data file beside the loader, `components/compliance/country_pack/trusted_publish_keys.json` (built by CMP-041), outside every pack version, as ADR-0067 keeps `product_choice_paths.json`. Each entry: `kid`, `keyEnv`, `publicKey`, `status` (`active`, `retired`, `revoked`). Adding a key is a PR with the other founder's review, then a deploy; the store can never add a trusted key. An optional deployment deny-list (configuration, read at start) can only add revocations, so an emergency revocation does not wait for a PR. Where the trust root lives is Q-656.
- Rotation: the new `kid` ships as `active` before the publisher switches; the old key becomes `retired`. A record signed by a retired key still verifies if the current index, signed by an active key, lists its exact `contentDigest` and `publishId`; a retired key never verifies an index.
- Revocation: a `revoked` key verifies nothing, record or index. Versions it signed refuse until CMP-038 re-publishes them under a new key with two fresh sign-offs.
- Key loss (destroyed or unusable private key, not compromise): loads continue, because the public key is in the trust file; publishing stops until a new key ships.
- Test vectors use a throwaway key whose private half is discarded after generation; its `kid` has `keyEnv: dev` and is refused in any other deployment.

1.8 **What the loader can and cannot prove.** With one publisher key, the two sign-offs, their roles and their MFA are the publisher's signed attestation. The loader checks that the attestation is complete and consistent (item 2, step 9) and that the signed content is the content it loads; it cannot prove that two people really signed or that MFA happened. A compromised publish service or key defeats the two-person rule and is a separate threat (T06). Per-signer signatures the loader can verify are Q-652.

1.9 **Loader-side trust data never comes from the store.** `pack.schema.json`, the component manifest contract, the founders map (`scripts/lanes.json`), `product_choice_paths.json`, the registered component providers for `requires`, and the trusted key file come from the deployed code. A published version that needs a provider version the deployment lacks is refused by the existing gate (`go_live_refused`); CMP-038's schedule must only target deployments that carry the provider.

1.10 **(P) Repo-bundled packs** stay for sandbox and test site classes (ADR-0059) and for unit tests. They carry no record. One tenant entry, `resolve_tenant_country_pack(context, company_overrides)` (CMP-044), serves all tenant work: it reads the site class and pin from the registry (item 3) and picks the source itself: a production site class uses the store only; a sandbox or test site class uses the store when pinned to a published version, otherwise the repo packs. The directory functions `load_country_pack` and `resolve_country_pack` refuse `environment="production"` with `unsigned_repo_pack` and stay for sandbox, test and unit tests. Python cannot stop a tenant caller from passing `environment="sandbox"` to the directory function, so CMP-044 moves the existing tenant caller (`components/compliance/company_calendar/settings.py`) to the tenant entry and adds an import guard test that no module outside the package calls the directory functions for tenant work (CMP39-T32). Signing repo packs the same way is rejected below.

### 2. Loader rules (fail closed, in this order)
New refusals raise a `PackStoreRefusal(CountryPackError)` carrying a stable `code`. Existing refusal messages and classes are unchanged (tests pin them); the existing gate's reasons travel inside `go_live_refused`. Codes marked S also emit a platform security event (item 5).

| Step | Check | Code |
|---|---|---|
| 1 | Tenant id from the authenticated context; site class and pin read through `PinSource` from the tenant registry, never from caller arguments. A caller `environment` that differs from the site class refuses; a caller `version` that differs from the pin refuses; `allow_unpinned` and `allow_test_packs` refuse on the store path | `environment_mismatch`, `pin_missing`, `registry_unavailable`, `version_not_pinned`, `unpinned_refused` |
| 2 | Read the verified state; fetch the country index (or the verified cache, item 6) | `verified_state_unavailable`, `store_unavailable` |
| 3 | Index: strict parse, active non-revoked `kid` of this key environment, signature, `countryCode` | `index_malformed`, `key_unknown` S, `key_revoked` S, `key_wrong_environment` S, `signature_invalid` S |
| 4 | Index freshness: `indexSeq` at least the high-water mark and at least the pin's `indexSeqAtPin`, `floor` not lower, no withdrawal dropped; then raise the high-water mark | `index_rollback` S, `floor_regression` S, `withdrawal_reversed` S |
| 5 | Pin `(version, contentDigest, publishId)` is in `published`, not in `withdrawn`, and `version` is at or above `floor` | `pin_digest_mismatch` S, `version_withdrawn`, `version_below_floor` |
| 6 | Fetch record and bundle bytes once; strict parse; `kid` rules of 1.7; signature | `record_missing`, `record_malformed`, `key_*` S, `signature_invalid` S |
| 7 | Record `packId`, `countryCode`, `version`, `keyEnv` equal the pin and the deployment; `publishId` equals the index entry; `predecessor` well formed and lower | `record_mismatch` S, `predecessor_invalid` |
| 8 | Closed file set; per-file hashes; recomputed `contentDigest` equals the record and the pin | `file_set_invalid` S, `content_digest_mismatch` S |
| 9 | Sign-offs: exactly two; one `market_accountant`, one `founder`; different `signerId`; once Q-653 gives a staff-identity-to-founder mapping, the accountant's `signerId` is not a founder's; `publishedBy` is one of the two `signerId`s; `founderLogin` is in the founders map and maps to `evidence.json` `certification.founder`; accountant `name` and `market` equal `evidence.json` `certification.accountant`, and `market` equals the country; `statementDigest` recomputed and equal; `mfa` present with `method` in the allowed set (now `totp`, `webauthn`; Q-652), `authTime` at most 300 s before `signedAt`; every `signedAt` at most `publishedAt`; `publishedAt` not after now plus 30 s | `signoff_count` S, `signoff_same_person` S, `signoff_role` S, `signoff_certification_mismatch` S, `signoff_statement_mismatch` S, `signoff_mfa` S |
| 10 | Parse the in-memory `pack.json` and run `validate_pack` and the existing go-live gate on the in-memory bundle, unchanged in meaning | existing messages inside `go_live_refused` |
| 11 | Write the load audit event write-through (item 5) | `audit_unavailable` |

Production never selects "latest": the only version it loads is the pin. Every check runs on every load, including cache hits. The loader returns the resolved pack plus provenance `{source: store or cache, publishId, contentDigest, kid, indexSeq, urgent, followUpOpen}`.

### 3. Per-tenant pinning
3.1 **(P) The pin lives in the tenant registry** (control plane, Eldon's lane): `tenantId`, `countryCode`, `packId`, `version`, `contentDigest`, `publishId`, `pinSeq` (plus one per change), `indexSeqAtPin` (the index sequence the registry verified when it pinned, a floor for the loader's high-water mark that does not depend on loader state), `changeKind` (`initial`, `upgrade`, `rollback`, `republish` for the same version re-signed under a new key), `changedBy`, `approvalRef`, `changedAt`. Tenants keep the exact version in their compiled artifact as today ([../compliance/country-pack-framework.md](../compliance/country-pack-framework.md) section 5); the registry pin is what the loader trusts. The loader reads it through the `PinSource` port and never writes it. Binding the pin to the digest means a store that serves another record for the same version number refuses (`pin_digest_mismatch`).

3.2 **Upgrade.** The CMP-038 schedule names a country, a target version and tenant cohorts, canary first. For each tenant the registry calls the loader's `check_upgrade(tenant, target)`: the full item 2 checks against the target, then the tenant's current company overrides merged against the target (the existing override rules), then `upgradePolicy`: (P) `compatibilityRange` read as the versions this one may be upgraded from, so it must contain the current version (the schema and the framework do not define its meaning: UNVERIFIED, settled under Q-655), and `migrationRequired: true` (required on a major version by the framework) stops the automatic move until a named migration step exists (not in this ADR). Only on a pass does the registry move the pin and emit a pin event. A failure leaves the pin, records the reason code and alerts.

3.3 **Rollback and downgrade, defined.** A *rollback* is a registry move to a lower version that is in the index, not withdrawn, at or above the floor, passes `check_upgrade`, and carries an approval (who approves is Q-655; (P) one founder with step-up and a written reason). A *downgrade* is anything else that would make a tenant run older content: a pin to a withdrawn or below-floor version, a store serving an older record or index, or a caller asking for a version other than the pin. The loader refuses every downgrade (item 2, steps 1, 4, 5, 7). When an older version must never run again, CMP-038 withdraws it or raises the floor.

3.4 **In-flight periods.** A pin change never applies backwards: the compiler stores the resolved locale with the compiled artifact (country-packs compiler step 5), so a change takes effect at the next compile and apply, and every load event records the version and digest used. The pack schema holds no rates or dated statutory values today: `tax` carries `taxCodesRef`, `filingPeriods` and `roundingRule`; where rates live is outside the pack (UNVERIFIED). Which treatment applies to a supply when a VAT period straddles a rate change (by invoice date, supply date or transitional rule) is a tax fact for each market: UNVERIFIED for Saudi Arabia, the UAE, Egypt and Qatar, routed to the market accountant through CMP-038's evidence. The loader decides none of it. (P) The schedule moves pins only at a boundary the accountant signed off for that change; a law that needs both treatments inside one period needs dated values in the pack, which is a separate schema row (Q-657).

### 4. Urgent changes
The urgent path keeps the full two-person rule: the record says `changeKind: urgent` and `followUp.required: true`, and step 9 applies unchanged. The loader does not refuse an urgent version because its follow-up is open (refusing would block a legal change); every load, upgrade check and pin event carries `urgent: true` and `followUpOpen` from the index. CMP-038 closes the follow-up by a two-person change record that removes the `publishId` from `followUpOpen`; the outcome is either confirmed, or superseded by a new version with a floor raised above the urgent one. Whether an open follow-up stops rollout beyond the canary cohort is Q-657.

### 5. Audit
- Every store-path load, refusal, upgrade check and index advance is an audit event through an `AuditSink` port; SEC-008 owns the format and the store (decision 1 on #316). Events: `country_pack.loaded`, `country_pack.load_refused`, `country_pack.upgrade_checked`, `country_pack.index_advanced`; the registry emits `country_pack.pin_changed`. Fields: tenant, site class, caller service, correlation id, pack id, country, version, `contentDigest`, `publishId`, `kid`, `indexSeq`, source, `urgent`, `followUpOpen`, reason code and step. Never pack contents, never the envelope bytes; a refused envelope is recorded by its sha256.
- Codes marked S in item 2 also go to SEC-008's platform security stream (decision 3 on #316), without tenant content.
- **(P)** Store-path events are written through: if the audit write fails, the load refuses `audit_unavailable` (this is a proposal, not a founder decision). Repo-path loads in sandbox and test log best effort.

### 6. Store outage at load
**(P) Cached last verified version, bounded.** The loader keeps a verified state (behind a `VerifiedState` port): per country the high-water `indexSeq`, the highest floor and every withdrawal it has seen, plus the last verified index and the bundle bytes and record for pinned versions. On a store outage it may serve only the tenant's pinned version, only from the cache, only while the cached index is younger than a configured staleness bound; every item 2 check still runs on the cached bytes against the current trust file and deny-list. No configured bound means no cache: refuse `store_unavailable`. A registry outage always refuses (`pin_missing`), because the pin is never cached. When the loader runs: at compile and apply (compiler step 1 resolves the pack version) and whenever a component resolves pack values for a tenant, as `company_calendar/settings.py` does. Rationale: a tenant already on a verified version should not stop compiling, applying or resolving its calendar because the store blinked, while a withdrawal published during the outage is honoured within the bound. **Verified state failures (P):** an unreadable state or a failed write refuses (`verified_state_unavailable`). The state is durable and shared by all loader instances of a deployment, never per instance. An empty state (a new deployment, or after loss) accepts the first index it verifies (trust on first use), but never one below the pin's `indexSeqAtPin`, so a store rolled back further than the last pin still refuses. The bound and where the state lives are Q-654.

## Threats
| # | Threat | Control | Tests |
|---|---|---|---|
| T01 | Bundle file altered in the store | Exact-bytes digest, closed file set (1.1, 1.2) | CMP39-T05, T06, T07 |
| T02 | Record altered, or forged without the key | ed25519 signature with domain string (1.5) | CMP39-T02, T03 |
| T03 | Replayed old version: an older record or index served for the pinned version | Pin bound to digest; index high-water mark (1.6, 3.1) | CMP39-T12, T13 |
| T04 | Downgrade through the pin or the caller | Floor, withdrawals, pin-only selection, caller arguments refused (2, 3.3) | CMP39-T14, T15, T16, T17 |
| T05 | One compromised signer | Two distinct `signerId`, roles, accountant not a founder, match to `evidence.json`; publisher enforces the same (1.4, 2 step 9) | CMP39-T18 to T22 |
| T06 | Compromised publish service or publish key | Not detectable by the loader (1.8). KMS sign-only for one workload identity; KMS sign log reconciled with CMP-038 publish records (SEC-008, detective); revocation and re-publish; Q-652 | CMP39-T09, T10 |
| T07 | Key loss | Public key in the trust file; loads continue, publish stops (1.7) | CMP39-T11 |
| T08 | Staging or dev key, or another record type, accepted in production | `keyEnv`, per-environment trust entries, domain strings (1.5, 1.7) | CMP39-T04, T08 |
| T09 | Wrong-country or wrong-pack record | Record, pin and index fields compared (2 step 7) | CMP39-T23 |
| T10 | Check-then-read gap (file changed between verify and gate) | One read into memory; gate on the in-memory bundle (1.2) | CMP39-T24 |
| T11 | Repo pack or unsigned bundle used in production | Store path only for the production site class (1.10) | CMP39-T01, T25 |
| T12 | Trust data smuggled in a pack (founders, product-choice list, keys) | Loader-side trust data only (1.9) | CMP39-T26 |
| T13 | Store outage | Bounded verified cache, else refuse (6) | CMP39-T27, T28, T29 |
| T14 | Withdrawal missed during an outage | Staleness bound; withdrawals never leave the cached state (1.6, 6) | CMP39-T28 |
| T15 | Loads hidden from the audit | Write-through, refuse on audit failure (5) | CMP39-T30 |
| T16 | Urgent version used to dodge review | Same sign-off checks; flags carried in every event (4) | CMP39-T31 |
| T17 | Verified state lost or emptied, then a rolled-back store accepted | Durable shared state; unreadable state refuses; `indexSeqAtPin` floor (3.1, 6) | CMP39-T33 |
| T18 | Production tenant loaded through the directory function with a weaker `environment` | One tenant entry; directory functions refuse production; import guard (1.10) | CMP39-T01, T32 |

## Tests the build rows must pass
| ID | Asserts |
|---|---|
| CMP39-T01 | A production site class with no store record for the pin refuses (`record_missing`); a production repo load refuses `unsigned_repo_pack` |
| CMP39-T02 | One flipped byte in the payload or signature refuses `signature_invalid` and emits a security event |
| CMP39-T03 | Envelope parse refuses duplicate keys, unknown or missing keys, fractions, exponents, out-of-range integers, padding and oversize payloads |
| CMP39-T04 | A record signed with the ADR-0068 domain string, or as an index, does not verify as a version record |
| CMP39-T05 | One changed byte in any bundle file refuses `content_digest_mismatch` |
| CMP39-T06 | An extra file, a missing required file, a directory or a byte order mark refuses `file_set_invalid` |
| CMP39-T07 | Shared vectors: the published `contentDigest` and signatures for the sample bundles match byte for byte (the vectors CMP-038 builds against) |
| CMP39-T08 | A `dev` or `staging` key, or a record whose `keyEnv` differs from the deployment, refuses `key_wrong_environment` |
| CMP39-T09 | A revoked key (trust file or deny-list) refuses records and indexes it signed; the deny-list cannot add a key |
| CMP39-T10 | A retired key verifies a record only when an active-key index lists its digest and `publishId`; never an index |
| CMP39-T11 | With the private key gone, loads of already-published versions still pass |
| CMP39-T12 | A record or index entry whose digest or `publishId` differs from the pin (given as input) refuses `pin_digest_mismatch` |
| CMP39-T13 | An index with a lower `indexSeq`, a lower floor or a dropped withdrawal refuses (`index_rollback`, `floor_regression`, `withdrawal_reversed`) |
| CMP39-T14 | A pin to a withdrawn or below-floor version refuses |
| CMP39-T15 | Caller `environment` or `version` different from the registry refuses; `allow_unpinned` and `allow_test_packs` refuse on the store path |
| CMP39-T16 | Production never picks the highest version; with no pin it refuses `pin_missing`; `environment="production"` on the directory functions refuses `unsigned_repo_pack` |
| CMP39-T17 | `check_upgrade` refuses a `migrationRequired` target and a target whose overrides fail, and applies the `compatibilityRange` rule as Q-655 settles it; passes a compatible one |
| CMP39-T18 | Sign-offs: one entry, three entries or two of the same role refuse |
| CMP39-T19 | Same `signerId` twice refuses `signoff_same_person`; a `publishedBy` that is neither signer refuses; (after Q-653) an accountant whose `signerId` maps to a founder refuses |
| CMP39-T20 | A founder login outside the founders map, or one that does not map to `certification.founder`, and an accountant name or market not equal to `certification.accountant`, refuse |
| CMP39-T21 | A `statementDigest` for other content or another diff refuses |
| CMP39-T22 | Missing `mfa`, an unknown method, `authTime` more than 300 s before `signedAt`, `signedAt` after `publishedAt` or a future `publishedAt` refuse |
| CMP39-T23 | A record whose country, pack id, version or `publishId` differs from the pin and index entry (given as inputs) refuses `record_mismatch` |
| CMP39-T24 | The gate reads no file after the bundle is built (instrumented file access) |
| CMP39-T25 | Every existing production-mode rule (ADR-0063, ADR-0067) still refuses on an in-memory bundle with the same messages (CMP-041), and on a signed bundle inside `go_live_refused` (CMP-042) |
| CMP39-T26 | A bundle that carries its own founders map, product-choice file or key file changes nothing (closed file set refuses it) |
| CMP39-T27 | Store down, cache fresh: the pinned version loads from cache with every check re-run; source is `cache` |
| CMP39-T28 | Store down, cache older than the bound, or no bound configured: refuses `store_unavailable`; a cached withdrawal stays honoured |
| CMP39-T29 | Registry down: refuses `registry_unavailable`, never uses a cached pin |
| CMP39-T30 | Audit sink failure on a store-path load refuses `audit_unavailable`; security codes reach the security stream fake |
| CMP39-T31 | An urgent record with an open follow-up loads and every event carries `urgent` and `followUpOpen`; an urgent record with one sign-off refuses |
| CMP39-T32 | Import guard: no module outside the package calls `load_country_pack` or `resolve_country_pack` for tenant work; `company_calendar/settings.py` uses the tenant entry and its tests still pass |
| CMP39-T33 | Unreadable verified state refuses `verified_state_unavailable`; an empty state accepts a verified index at or above the pin's `indexSeqAtPin` and refuses one below it |

## Build split (proposed rows)
| ID | Task | Part | Gate | Depends | Owner | Status |
|---|---|---|---|---|---|---|
| CMP-041 | Country pack go-live gate on an in-memory bundle (ADR-0071 1.1, 1.2, 1.10), behaviour-neutral: the directory loader reads the closed file set once into a bundle of exact bytes and the gate, certification and evidence checks run on that bundle, with no second file read and every existing message unchanged; tests CMP39-T24, T25 and every existing country pack test unchanged | Compliance | G3 | CMP-036 | partner | todo |
| CMP-042 | Signed pack record verifier (ADR-0071 1.3 to 1.9, item 2 steps 3 and 6 to 10), a pure function over the envelope, bundle bytes, trust file and the expected pin and index entry as inputs: strict envelope parse, `trusted_publish_keys.json` beside the loader with active, retired and revoked keys and a deny-list, exact-bytes content digest, sign-off checks against `evidence.json`, stable reason codes in a new `PackStoreRefusal` class; shared test vectors with a throwaway dev key for CMP-038 to build against; tests CMP39-T02 to T12, T18 to T23, T26 | Compliance | G3 | CMP-041 | partner | todo |
| CMP-043 | Pack store read path (ADR-0071 1.6, item 2 steps 2, 4 and 5, item 6): `PackStore` and `VerifiedState` ports with in-memory fakes, signed country index with high-water mark, `indexSeqAtPin` floor, floor and withdrawals, verified cache bounded by a staleness setting (absent means no cache), state failure refusals; tests CMP39-T13, T14, T27, T28, T33 | Compliance | G3 | CMP-042 | partner | todo |
| CMP-044 | Tenant entry and upgrade check (ADR-0071 1.10, item 2 steps 1 and 11, items 3 to 5): `resolve_tenant_country_pack` with pin and site class through a `PinSource` port (fake), directory functions refuse production, `company_calendar/settings.py` moved to the tenant entry with an import guard, `check_upgrade` for the schedule and the registry, urgent and follow-up flags, audit and security events through an `AuditSink` port (fake until SEC-008), write-through refusal; tests CMP39-T01, T15 to T17, T29 to T32 | Compliance | G3 | CMP-043 | partner | todo |

None depends on an Eldon row: CMP-038, the tenant registry and SEC-008 are reached through ports, fakes and the shared vectors. Wiring the real store, registry and audit store is a later row, opened once Q-656 is answered and those exist.

## Questions for Eldon
| # | Question | Owner | Needed by | Related |
|---|---|---|---|---|
| Q-652 | CMP-039 (ADR-0071 1.8): with one publish key the loader only checks the publisher's attestation of the two sign-offs. Should each signer also produce a signature the loader can verify (for example a WebAuthn assertion over `statementDigest`, which needs ADR-0047 F1 and F2 and the signers' public credentials beside the loader), and should production require `webauthn` rather than `totp`? | eldon | G3 | CMP-039, CMP-038 |
| Q-653 | CMP-039 (ADR-0071 1.4, 2 step 9): do market accountants get staff-realm identities (MFA always, ADR-0047), one named accountant per market or a roster, and who adds them? How does a founder's staff `signerId` map to the GitHub login in the `scripts/lanes.json` founders map that `certification.founder` uses? | eldon | G3 | CMP-039, CMP-038 |
| Q-654 | CMP-039 (ADR-0071 6): on a store outage, may the loader serve the tenant's pinned version from its verified cache (proposed) and with what staleness bound, or must it always refuse? Where does the loader's verified state (high-water marks, floors, withdrawals, cached bytes) live in production? | eldon | G3 | CMP-039, CMP-038 |
| Q-655 | CMP-039 (ADR-0071 3.1 to 3.3): which registry row builds the pin record (with `publishId` and `indexSeqAtPin`) and calls `check_upgrade`; who approves a rollback: one founder with step-up and a reason (proposed) or the two-person rule; and what `upgradePolicy.compatibilityRange` means (proposed: the versions this one may be upgraded from; neither the schema nor the framework defines it)? | eldon | G3 | CMP-039, CMP-038 |
| Q-656 | CMP-039 (ADR-0071 1, 1.7, 5): should the record, index and pin formats move into a `contracts/` schema before CMP-038 is built, or stay in this ADR plus the shared vectors? Does the verification-key trust root stay a reviewed data file beside the loader (proposed) or move to the environment's configuration? Do you accept refusing a load when the audit write fails? | eldon | G3 | CMP-039, CMP-038 |
| Q-657 | CMP-039 (ADR-0071 3.4, 4): when a statutory change takes effect inside an open VAT period, do packs need dated values (a pack schema row), or do pins move only at accountant-approved boundaries (proposed)? The tax treatment is UNVERIFIED for all four markets and goes to the accountant. Does an open urgent follow-up stop rollout beyond the canary cohort? | eldon | G3 | CMP-039, CMP-038 |

## Alternatives rejected
- **Digest over re-serialised JSON.** Number and Unicode canonicalisation would need their own rules and tests; hashing the exact stored bytes needs none and the loader parses the bytes it hashed.
- **HMAC instead of a signature.** The loader would hold the minting secret, so a compromised loader host could publish packs (ADR-0068 item 6 makes the same point).
- **Trust keys from the pack store.** Whoever writes the store could then add a key; the trust root must be reviewed outside it.
- **Signing repo packs the same way and allowing them in production.** It adds a second publishing route outside CMP-038's two-person workflow; repo packs stay drafts for sandbox and test.
- **Refuse every load during a store outage.** Safe but it stops invoicing for tenants already on a verified version; kept as the behaviour when no bound is configured.
- **Refuse urgent versions until the follow-up closes.** It would block the legal change the urgent path exists for.
- **Revocation flags inside `evidence.json`.** ADR-0067's closed key set refuses them, and the pack under review must not decide its own validity; withdrawals live in the signed index.

## Consequences
- Production tenants can only run pack content that CMP-038 published with both sign-offs recorded and that has not been withdrawn or fallen below the floor; the repo packs never reach production.
- Harder: the loader gains a trust file, a store port, verified state and an audit dependency; every production load needs the registry, and either the store or a fresh cache.
- Residual, stated plainly: the loader cannot detect a compromised publish service or key (T06) until Q-652 adds per-signer signatures; it proves records, not accountant qualifications (as ADR-0063 says); tax transitions are not modelled (3.4, UNVERIFIED).
- A withdrawal, a floor raise or a key revocation refuses every tenant still pinned to the affected version at its next load, store path and cache alike. CMP-038 must move those tenants' pins (upgrade, rollback or `republish`) before or together with that change, and alert on any tenant left behind.
- CMP-038 must produce exactly the formats of item 1 and pass the shared vectors (CMP39-T07); the registry must hold the pin of 3.1. Tier 3 line-by-line review and a different-model security review are required before Accepted; neither is claimed here.

## Supersedes
None in full. Amends the production path of [ADR-0059](ADR-0059-draft-country-packs-in-sandbox.md) Decision 2, [ADR-0063](ADR-0063-country-pack-certification-record.md) and [ADR-0067](ADR-0067-country-pack-production-blockers-and-product-choice.md): in a production site class the bundle comes only from the pack store with a valid record, and their checks run on that verified bundle. Their sandbox and test rules are unchanged.
