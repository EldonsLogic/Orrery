# Secrets management design

Status: draft
Owner: partner
Approved by: pending (with [ADR-0038](../decisions/ADR-0038-secrets-management.md))

Plan ID: SEC-002. Detail for ADR-0038. Nothing here is built; every line is a design requirement. Classes are from [data-classification.md](data-classification.md); threats from [threat-model.md](threat-model.md). External facts carry a URL and access date or are marked UNVERIFIED.

## 1. Inventory
Scope: P platform-wide, E per environment, T per tenant, U per tenant e-invoice unit. All items are C4. "Readers" are workload identities; no human reads any value in production (section 4).

| ID | Secret | Scope | Store (target) | Readers | Rotation | Threats |
|---|---|---|---|---|---|---|
| S01 | Model-provider API keys | P, E | Secret store | Model gateway only (PLT-009) | 90 days; on staff change or leak | T60 |
| S02 | Identity token signing keys (OIDC, ADR-0007) | E | KMS, non-exportable, sign only | Identity service via `Signer`; public keys published | 90 days, old key kept for verification until its last token expires | T50 |
| S03 | Internal service CA key and service certificates (adapter auth, contract 16.1) | E | CA key in KMS; certificates issued short-lived | Internal CA; each service holds only its own certificate | Certificates ≤ 24 h; CA key yearly with cross-signing | T55 |
| S04 | Gateway session cookie and CSRF secrets (web app) | E | Secret store | Web gateway | 90 days, two active keys | T50 |
| S05 | Tenant database credential (one database user per site) | T | Secret store | Engine workers of the tenant's bench pool; provisioning (PLT-003) | 90 days; on incident; on pool move | T53 |
| S06 | Database server administrative credential | E per DB server | Secret store, break-glass path | Provisioning, fetched per operation; never a long-running service | 30 days and after every break-glass use | T53 |
| S07 | Cache and queue credentials (per bench pool) | E per pool | Secret store | Engine workers of that pool | 90 days | T53 |
| S08 | Engine Administrator password per site | T | Secret store, break-glass path | Nobody in normal operation; engine login is disabled for it outside break-glass | Random at creation; rotated after each use | T53 |
| S09 | Gateway impersonation credential per site (ADR-0007 item 11) | T | Secret store | Operate gateway only, for that site's shadow users | 90 days; on incident | T36, T53 |
| S10 | Per-tenant data encryption keys (envelope) and backup keys | T | Data keys wrapped by a KMS key-encryption key | Storage and backup jobs; unwrap in KMS only | KEK yearly (re-wrap); data key on incident; destroyed at tenant deletion (crypto-shredding, SEC-011, DAT-007) | T58 |
| S11 | Connector credentials (OAuth refresh tokens, API keys for the owner's tools) | T | Secret store | That tenant's connector job only (DSC-010) | Provider's refresh cycle; revoked after one-off import (T4); on tenant request | T4 |
| S12 | Outbound webhook signing secrets | T per endpoint | Secret store | Event delivery worker | On tenant request; yearly | T55 |
| S13 | Inbound webhook verification secrets (payment, messaging providers) | P or T | Secret store | Receiving endpoint only | Provider's rules; on leak | T55 |
| S14 | Email and SMS provider credentials | P, E | Secret store | Notification service | 90 days | - |
| S15 | Compiled-artifact integrity signing key (engine-adapter 16.8) | E | KMS, sign only | Compiler (sign); adapter (verify with public key) | Yearly, overlap | T24 |
| S16 | Audit-chain export signing key (SEC-008) | E | KMS, sign only | Audit exporter | Yearly, overlap; verification keys kept as long as the audit trail | T56 |
| S17 | Support just-in-time access tokens (PLT-019) | T | Issued by identity, never stored in clear | Support tooling for the grant's lifetime | Expire with the grant | T52 |
| S18 | CI and deploy credentials | E | CI secrets; target OIDC federation to the cloud, no long-lived keys | Deploy job only, protected branch only | Federation: per run. Any static token: 90 days | T60 |
| S19 | Coding-agent and founder tokens (GitHub, model APIs used for development) | person | Founder's own machine or tool vault; never repo, never prompts | That person's tools | 90 days; fine-grained, repo-scoped | T60 |
| S20 | Dev, staging and preview secrets | E | Each environment's own store | That environment | Independent; never equal to a production value | T59 |
| Z1 | ZATCA private key (secp256k1) per e-invoice generation unit | U | KMS or HSM non-exportable (target) or secret store under KMS (fallback), ADR-0038 item 3 | Signer service only, for that unit | New key at every CSID renewal; on compromise | T10 |
| Z2 | ZATCA compliance CSID and its secret | U | Secret store | Onboarding job (CMP-007) | Short-lived by design; destroyed once the production CSID is active | T10 |
| Z3 | ZATCA production CSID (certificate, binary security token) and its API secret | U | Certificate: stored with the unit (not secret on its own); token and secret: secret store | Signer and submission services for that unit | Renew from 60 days before expiry; validity about one year per vendor sources (UNVERIFIED) | T10 |
| Z4 | Fatoora portal OTP | U, one use | Never stored. Held in memory for one onboarding call | Onboarding job, in the request that receives it | Single use; expires in about 60 minutes per vendor sources (UNVERIFIED) | T10 |
| Z5 | Other markets' e-invoice credentials (UAE, Egypt, Qatar) | T or U | Same rules as Z1 to Z3 | Same | Per regime | UNVERIFIED: regimes not researched; to be added by their CMP rows |

The CSR itself is not secret, but it is bound to Z1 and is regenerated with each new key. The ZATCA public certificate is C2: kept with the unit's records for audit after the key is destroyed.

## 2. ZATCA key lifecycle
1. **Create unit.** An owner or admin adds an e-invoice unit (CMP-007). The signer creates a new key Z1 for that unit and returns only the key id and public key.
2. **CSR.** Built from tenant data (VAT number, unit serial, invoice types) and signed by `Signer` with Z1. If CSR signing cannot be done through the KMS interface, this is part of the CMP-004 proof and the fallback in ADR-0038 item 3 applies.
3. **Compliance CSID.** The owner enters the OTP (Z4) in the dedicated form. The onboarding job sends CSR and OTP in one call, stores Z2 and discards the OTP. Then it runs the compliance invoice checks.
4. **Production CSID.** The job requests Z3 and stores it, then destroys Z2. The unit becomes `active`.
5. **Sign.** For each invoice the e-invoice component computes the hash and sends it to the signer with the tenant and unit from the stamped context. The signer checks that the unit is active for that tenant and signs. Every signature is audited with the unit, the invoice hash and the key version, never the key.
6. **Renew.** From 60 days before expiry the platform alerts the tenant's admins at 60, 30, 14, 7 and 1 days. Renewal repeats steps 1 to 4 with a new key and a new OTP. The old key is disabled once the new CSID is active and no submission with the old key is pending, then destroyed after a waiting period (D-3).
7. **Expiry.** An expired or revoked CSID blocks issuing for that unit, fail closed with a clear error. The platform never issues an unsigned or wrongly signed invoice to keep business moving.
8. **Compromise.** Disable the key at once, block issuing, revoke with ZATCA (procedure UNVERIFIED; CMP-007 records it), onboard a new key, run an incident per [incident-response.md](incident-response.md).
9. **Tenant deletion or export.** Keys are destroyed, never exported. The tenant gets its data and certificates and must onboard again on any new system. This matches data-classification ("re-issued, not copied") and the reported rule that the e-invoice solution must not offer key export (third-party claim, https://zatca1.discourse.group/t/private-key-usage-and-storage/6380, accessed 2026-11-18, UNVERIFIED).

## 3. Store options and selection criteria (decision deferred to INF-001)
| Option | Signs secp256k1 non-exportably | Strengths | Weaknesses |
|---|---|---|---|
| Cloud provider KMS plus secret manager (for example AWS KMS and Secrets Manager) | AWS: yes, `ECC_SECG_P256K1` (https://docs.aws.amazon.com/kms/latest/developerguide/symm-asymm-choose-key-spec.html, accessed 2026-11-18). Other providers UNVERIFIED | Managed, hardware-backed (provider claim), audit logs, IAM policies | Needs an in-country region of that provider (UNVERIFIED for KSA, UAE, Egypt, Qatar); provider lock-in behind our interface |
| Self-hosted OpenBao or Vault (KV plus transit), auto-unseal by a KMS or HSM | No: transit lists P-256, P-384, P-521, Ed25519 only (https://developer.hashicorp.com/vault/api-docs/secret/transit, accessed 2026-11-18) | Runs on any in-country provider; strong policy and lease model; dynamic database credentials | Operations burden; ZATCA keys only through the fallback path; Vault licence needs LEG-004 |
| Dedicated or network HSM through PKCS#11 (provider HSM service or appliance) | Depends on model (UNVERIFIED) | Strongest key custody; can serve as the signer for Z1 | Cost, scarce in-country, operations burden |

Selection criteria for INF-001:
1. Runs in each tenant's region (or legal advice says otherwise; Q-14, Q-129).
2. secp256k1 non-exportable signing, or an approved fallback.
3. Separate admin and use roles.
4. Per-call audit log exported to our audit store.
5. Workload identity, no static root credential in services.
6. Waiting period before key destruction.
7. Licence fits SaaS use (LEG-004).
8. Cost per tenant and per signature.

A likely shape, not decided: a provider KMS for signing and key wrapping plus a secret manager (managed or OpenBao) for values.

## 4. Access model
- **Identities.** Each service has a workload identity: the platform issues it, it is short-lived, and it is bound to service and environment. The store never sees a shared password.
- **Paths and policies.** `{env}/platform/{service}/{name}` is readable by the named service only. `{env}/tenant/{tenantId}/{kind}/{name}` is readable by services allowed that `kind`, and only when the request's stamped tenant equals `tenantId`. ZATCA keys sit under `{env}/tenant/{tenantId}/einvoice/{unitId}/...`, are usable only by the signer, and the signer checks the unit's state on every call.
- **Separation.** Key administration (create, rotate, disable, schedule destruction, change policy) and key use are different identities. No identity has both. Provisioning (PLT-003) may create and destroy tenant secrets; it never reads Z1.
- **Humans.** No human reads a production C4 value. Support triggers rotation through the team console (PLT-012) with a reason and a ticket.
- **Break-glass.** Root of the store, KMS administration and S06 and S08 use need two founders, hardware-key MFA, a written reason and a time box of at most 1 hour. Every action is logged off-box and alerts both founders. The tenant is notified when a tenant path is touched. Every secret used during the break-glass is rotated afterwards. Agents never break-glass (ALP-044).
- **Caching.** Services may cache a secret in memory for at most its lease, 15 minutes by default (D-2). Nothing secret is cached on disk.

## 5. Keeping secrets out of logs, repos, errors and models
1. **Type.** All secret handling uses a `SecretValue` wrapper whose string, repr, JSON and pickle forms are `<redacted:{id}>`. The value is reachable only by an explicit `reveal()` at the point of use, which code review flags.
2. **Logs and telemetry.** A structured logger with a key deny-list (`password`, `secret`, `token`, `key`, `otp`, `authorization`, `cookie`, `csid` and variants). It also scrubs values by pattern, reusing the patterns in `scripts/scan_secrets.py` plus PEM headers, JWT shape and ZATCA token shape. Scrubbing happens before export. A hit is replaced and counted; a non-zero count alerts.
3. **Errors.** Exceptions never include secret values. Services return our error model; engine errors are mapped by the gateway (PLT-024). Crash reporters and core dumps are disabled or scrubbed in production.
4. **Process.** No secret on argv (the ERP-003 script already avoids host argv; the engine's own site creation still takes flags inside its container, a known gap). No secrets in images, build args, environment dumps or health endpoints.
5. **Repo.** `scripts/scan_secrets.py` runs in pre-commit and CI; GitHub secret scanning and push protection (ADR-0021). Test fixtures use generated throwaway keys created at test time, never committed.
6. **Model gateway.**
   - Fields classed C4 in manifests never enter a Tool API schema or result (OPR-003, ALP-016).
   - The gateway's outbound filter checks every prompt, tool result and model output for secret patterns and for keyed fingerprints of live secrets. The fingerprint set is maintained by the store and held only in memory by the gateway. A hit blocks the call and raises `agent.output_flagged` ([prompt-injection-defence.md](prompt-injection-defence.md) section 5.3).
   - Chat input that matches a secret pattern is not forwarded. The user is told to use the secure form.
   - No system prompt, memory or Blueprint holds a secret.
7. **Exports and backups.** C4 is never in a tenant export. Backups carry only wrapped keys; restoring to another environment never restores production secrets (data-classification section 3).

## 6. Requirements
| ID | Requirement | Row |
|---|---|---|
| SEC2-001 | Every secret in section 1 is reached only through `SecretStore` or `Signer` | all callers |
| SEC2-002 | `SecretValue` redacts in string, repr, JSON, logging and exceptions | first code row |
| SEC2-003 | Production tenant secrets are stored in the tenant's region | INF-001, INF-005 |
| SEC2-004 | No production secret exists in dev, staging or preview, and no non-production secret in production | INF-012, INF-004 |
| SEC2-005 | Signing keys (S02, S03, S15, S16) are non-exportable KMS keys | INF-005 |
| SEC2-006 | Each ZATCA unit has its own key; no key is shared across units, tenants or environments | CMP-007 |
| SEC2-007 | The ZATCA key is never stored in an engine database field, file or log in clear | CMP-004, CMP-007 |
| SEC2-008 | The ZATCA key is used only by the signer service; engine web workers never hold it | CMP-004 |
| SEC2-009 | The signer signs only for an active unit of the stamped tenant | CMP-004 |
| SEC2-010 | Every signature is audited with unit, invoice hash and key version | CMP-004, SEC-008 |
| SEC2-011 | The OTP is used in one call, never stored, logged, echoed or sent to the chat or a model | CMP-007 |
| SEC2-012 | CSID renewal generates a new key pair | CMP-007 |
| SEC2-013 | Expiry alerts at 60, 30, 14, 7 and 1 days to tenant admins | CMP-007 |
| SEC2-014 | An expired or revoked CSID blocks issuing for that unit, fail closed | CMP-004 |
| SEC2-015 | Compliance CSID is destroyed once the production CSID is active | CMP-007 |
| SEC2-016 | Keys are destroyed, never exported, on tenant deletion; export contains no C4 | DAT-006, DAT-007 |
| SEC2-017 | Services authenticate to the store with workload identities, no static shared credential | INF-002 |
| SEC2-018 | Tenant paths are readable only when the stamped tenant equals the path tenant | first code row, SEC-004 |
| SEC2-019 | Key admin and key use are separate identities | INF-005 |
| SEC2-020 | No human reads a production C4 value; support can only trigger rotation | PLT-012, PLT-019 |
| SEC2-021 | Break-glass needs two founders, hardware MFA, a reason and a time box of at most 1 hour; it is logged off-box and alerts both founders | INF-005, PLT-019 |
| SEC2-022 | Secrets used during break-glass are rotated afterwards | runbook |
| SEC2-023 | The tenant is notified when break-glass touches its secrets | PLT-020 |
| SEC2-024 | Agents never read C4 and never break-glass | OPR-004 (ALP-016, ALP-044) |
| SEC2-025 | Rotation cadences in section 1 are enforced by a scheduled job with an overdue alert | first code row |
| SEC2-026 | Rotation keeps an overlap so verification of tokens and signatures in flight never fails | first code row |
| SEC2-027 | Staff departure triggers rotation of everything that person could reach | runbook |
| SEC2-028 | In-memory caching of secrets is bounded by the lease (D-2); none on disk | first code row |
| SEC2-029 | Logs and telemetry pass the scrubber; a hit alerts | PLT-015 |
| SEC2-030 | No secret appears in an error response, event, audit record (identifier only) or crash report | PLT-024, BPL-011 |
| SEC2-031 | No secret on host argv, in images or in build arguments | INF-006 |
| SEC2-032 | `scripts/scan_secrets.py` and GitHub secret scanning stay required checks | CI |
| SEC2-033 | C4 fields are excluded from every generated tool schema and result | OPR-003 |
| SEC2-034 | The model gateway blocks any prompt, tool result or output that matches a secret pattern or live-secret fingerprint | PLT-009 |
| SEC2-035 | Chat input matching a secret pattern is not forwarded to the model | PLT-009, WEB |
| SEC2-036 | No system prompt, memory, Blueprint or event payload holds a secret | BPL-003, OPR-001 |
| SEC2-037 | Store unavailable means the dependent operation fails closed, never with a default or cached-expired value | all callers |
| SEC2-038 | Destruction of a key has a waiting period (D-3) and is logged | INF-005 |
| SEC2-039 | Connector credentials have read-only scopes where the provider offers them and are revoked after a one-off import | DSC-010 |
| SEC2-040 | CI deploys use federation, not long-lived cloud keys; deploy secrets reachable only from protected branches | INF-003 |
| SEC2-041 | Tenant database credentials are distinct per site | PLT-003 |
| SEC2-042 | The engine Administrator password is random per site, stored only in the store, and its login is disabled outside break-glass | PLT-003 |
| SEC2-043 | Provisioning creates and destroys tenant secrets idempotently (one secret per name, never duplicated) | PLT-003 |
| SEC2-044 | Restoring a backup into another environment never restores production secrets | DAT-004 |
| SEC2-045 | Every store read and admin action is logged with identity, path and outcome, never the value | INF-005, SEC-008 |
| SEC2-046 | Store product, KMS and region are chosen against section 3 criteria and recorded in an ADR | INF-001 |

## 7. Test cases
| ID | Case | Expected |
|---|---|---|
| SEC2-T01 | Log a `SecretValue`, format it, raise it in an exception, serialise it | Only `<redacted:id>` appears |
| SEC2-T02 | Service A (with no policy) reads a tenant path | Denied, audited |
| SEC2-T03 | Engine worker with stamped tenant X reads tenant Y's database credential path | Denied |
| SEC2-T04 | Request body names another tenant for a secret read | Body ignored; stamped tenant used |
| SEC2-T05 | Signer asked to sign for a unit of another tenant | Refused, audited, alert |
| SEC2-T06 | Signer asked to sign for an expired, revoked or disabled unit | Refused; invoice not issued |
| SEC2-T07 | Attempt to export Z1 through every store and KMS API | Not possible (target) or fails policy (fallback) |
| SEC2-T08 | Scan the engine database, files and logs after onboarding and 100 signed invoices | No private key, OTP or CSID secret found |
| SEC2-T09 | OTP submitted, then the onboarding request's logs, audit, events and chat transcript are searched | OTP absent everywhere |
| SEC2-T10 | Reuse an OTP | Refused by our side before the call (one-use marker) and by ZATCA |
| SEC2-T11 | Renewal | New key id differs; old key disabled after cut-over; no invoice signed by the old key after cut-over |
| SEC2-T12 | Clock set to 61, 30, 7 and 0 days before expiry | Alerts at the listed thresholds; at expiry issuing blocks |
| SEC2-T13 | Paste a PEM private key and a ZATCA token into chat | Not forwarded to the model; user told to use the form |
| SEC2-T14 | Tool result containing a live secret (planted canary) | Gateway blocks; `agent.output_flagged` |
| SEC2-T15 | Generated tool set for a tenant with C4-classed fields | No C4 field in any schema or result |
| SEC2-T16 | Engine error containing a database password reaches the gateway | Mapped error; no secret in the response |
| SEC2-T17 | Commit a test file with a private-key header or a token shape | Pre-commit and CI fail |
| SEC2-T18 | Inspect argv of all provisioning processes on the host during a run | No secret values |
| SEC2-T19 | Support user triggers rotation of a tenant database credential | Rotated; old one invalid; value never shown |
| SEC2-T20 | Single founder attempts break-glass | Refused |
| SEC2-T21 | Two-founder break-glass on a tenant secret | Allowed for the time box; logged; tenant notified; secret rotated after |
| SEC2-T22 | Agent run token asks for any secret path | Denied |
| SEC2-T23 | Store unreachable during sign, provisioning and gateway start | Each fails closed with a clear error; no fallback value |
| SEC2-T24 | Token signing key rotation | Tokens signed by the previous key still verify until expiry; new tokens use the new key |
| SEC2-T25 | Rotation job finds an overdue secret | Alert raised |
| SEC2-T26 | Tenant export | No C4 in the archive |
| SEC2-T27 | Tenant deletion | Z1, S05, S08, S09, S10 and S11 destroyed (after waiting period); destruction logged |
| SEC2-T28 | Restore a production backup into staging | Production secrets not restored; staging uses its own |
| SEC2-T29 | Key admin identity tries to sign; key user identity tries to change policy | Both denied |
| SEC2-T30 | Provisioning step re-run after a crash between "create secret" and "record secret" | Exactly one secret exists for that name |
| SEC2-T31 | Log line with a secret pattern emitted by a library | Scrubbed before export; alert |
| SEC2-T32 | Preview or dev environment configured with a production secret value (by fingerprint) | Start-up refuses |

## 8. Decisions needed
1. **D-1** Store product, KMS or HSM and region (INF-001, Q-129). Criteria in section 3.
2. **D-2** Maximum in-memory lease for cached secrets (proposed 15 minutes).
3. **D-3** Waiting period before key destruction (proposed 30 days for tenant keys, 7 for ZATCA keys after renewal, to cover pending submissions).
4. **D-4** Whether the ZATCA remote-signer target is mandatory for go-live in KSA, or the fallback path is acceptable for the first pilot (depends on CMP-004 findings).
5. **D-5** Who holds break-glass while only two founders exist, and what happens when one is unreachable (an emergency third party, or accept delay).
