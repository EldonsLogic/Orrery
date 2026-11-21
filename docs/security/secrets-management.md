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
| S03 | Internal service CA key and service certificates (adapter auth, contract 16.1; internal event/webhook mTLS) | E | CA key in KMS; certificates issued short-lived | Internal CA; each service holds only its own certificate | Certificates ≤ 24 h; CA key yearly with cross-signing | T55 |
| S04 | Gateway session cookie and CSRF secrets (web app) | E | Secret store | Web gateway | 90 days, two active keys | T50 |
| S05 | Tenant database credential (one database user per site, dual-slot `slot_a`/`slot_b`) | T | Secret store | Engine workers of the tenant's bench pool (pool identity, app guard per tenant); ephemeral `provisioning-site-init` at `create_site` | 90 days via dual-slot cutover; on incident; on pool move | T53 |
| S06 | Database server administrative credential | E per DB server | Secret store, break-glass path | Ephemeral `provisioning-site-init` identity (per operation during site creation/deletion); never `engine-adapter` or long-running service | 30 days and forced automatic rotation at break-glass close / T+60m | T53 |
| S07 | Cache and queue credentials (per bench pool; target per-tenant Redis/queue ACL users) | E per pool (or T ACL) | Secret store | Engine workers of that pool (or tenant-scoped queue worker) | 90 days via dual-slot cutover | T53 |
| S08 | Engine Administrator password per site | T | Secret store, break-glass path | Ephemeral site-init generates/uses once at creation and writes with create-only scope; no subsequent normal store reader; login disablement UNVERIFIED until pinned-bench proof | Random at creation; forced automatic rotation after each break-glass use | T53 |
| S09 | Gateway impersonation credential per site (ADR-0007 item 11; separate credential/binding per principal kind for human vs agent users per ADR-0039) | T | Secret store | Operate gateway only, for that site's shadow/agent users | 90 days; on incident | T36, T53 |
| S10a | Regional envelope key-encryption key (KEK) | E per region | KMS, non-exportable, wrap/unwrap only | Never encrypts tenant data or backups directly; unwraps `S10b` for authorized jobs in KMS only | Yearly (re-wrap `S10b` DEKs) | T58 |
| S10b | Per-tenant data encryption keys (DEKs) and per-tenant backup DEKs | T | Envelope DEKs wrapped under `S10a` | Storage and backup jobs via KMS unwrap only | On incident; destroyed at tenant deletion after recovery window (crypto-shredding, SEC-011, DAT-007) | T58 |
| S11 | Connector credentials (OAuth refresh tokens, API keys for the owner's tools) | T | Secret store | Per-tenant connector job identity only (DSC-010) | Provider's refresh cycle; revoked after one-off import (T4); on tenant request | T4 |
| S12 | Outbound webhook signing secrets | T per endpoint | Secret store | Event delivery worker | On tenant request; yearly | T55 |
| S13 | Inbound webhook verification secrets (payment, messaging providers) | P or T | Secret store | Receiving endpoint only | Provider's rules; on leak | T55 |
| S14 | Email and SMS provider credentials | P, E | Secret store | Notification service | 90 days | - |
| S15 | Compiled-artifact integrity signing key (engine-adapter 16.8) | E | KMS, sign only | Compiler (sign); adapter (verify with public key) | Yearly, overlap | T24 |
| S16 | Audit-chain export signing key (SEC-008) | E | KMS, sign only | Audit exporter | Yearly, overlap; verification keys kept as long as the audit trail | T56 |
| S17 | Support just-in-time access tokens (PLT-019) | T | Issued by identity, never stored in clear | Per-tenant scoped support tooling for the grant's lifetime | Expire with the grant | T52 |
| S18 | CI and deploy credentials | E | Target: OIDC federation (`INF-003`), no long-lived cloud keys (`GOV-017` exception if temporary) | Deploy job only, protected branch only | Federation: per run. Any approved temporary static token: ≤ 90 days | T60 |
| S19 | Coding-agent and founder tokens (GitHub, model APIs used for development) | person | Founder's own machine or tool vault; never repo, never prompts | That person's tools | 90 days; fine-grained, repo-scoped | T60 |
| S20 | Dev, staging and preview secrets | E | Each environment's own store | That environment | Independent; never equal to a production value | T59 |
| S21 | Frappe per-site `encryption_key` (`site_config.json`, encrypts `Password` fields and tokens in tenant DB) | T | Secret store | Engine workers of tenant's bench pool; ephemeral `provisioning-site-init` at `create_site` | On incident; on pool move; excluded from backups | T53 |
| S22 | Control-plane regional database credentials (ADR-0040 workflow/audit/assignment DB) | E per region | Secret store | Control-plane and provisioning services only | 90 days via dual-slot cutover | T53 |
| S23 | Model-gateway live-secret fingerprint HMAC key (+ overlap key) | E | Secret store / KMS | Fingerprint publisher service; derived in-memory hashes pushed to model gateway only | 90 days with simultaneous dual-key re-index | T50, T54 |
| Z1 | ZATCA private key (`secp256k1`) per e-invoice generation unit | U | Target (and G3 mandatory): KMS or HSM non-exportable; first-pilot-only fallback (ADR-0042 `2026-11-18` note): encrypted at rest in secret store under `S10a` | Isolated per-tenant signer service only (never engine web workers); pilot fallback decrypted for single signature and immediately zeroized | New key at every CSID renewal; on compromise; fallback replaced before G3 | T10 |
| Z2 | ZATCA compliance CSID and its secret | U | Secret store | Onboarding job (CMP-007) | Short-lived by design; destroyed once the production CSID is active | T10 |
| Z3 | ZATCA production CSID (certificate, binary security token) and its API secret | U | Certificate: stored with the unit (C2, not secret); token and API secret: secret store | Signer and submission services for that unit | Renew from 60 days before expiry; CSID remains valid for multiple years per ZATCA Technical Guideline search index (exact PDF duration UNVERIFIED until CMP-004); prior `Z3` retained only during bounded Phase 2 retry drain, then disabled | T10 |
| Z4 | Fatoora portal OTP | U, one use | Plaintext OTP never stored (held in memory for one onboarding call); keyed HMAC digest of `(tenantId, unitId, otp)` persisted for ≥ 90 min as one-use replay marker (`SEC2-T10`) | Onboarding job in the single call that receives it | Single use; expires in ~60 minutes per ZATCA Technical Guideline search index (exact PDF UNVERIFIED until CMP-004) | T10 |
| Z5 | Other markets' e-invoice credentials (UAE, Egypt, Qatar) | T or U | Same rules as Z1 to Z3 | Same | Per regime | UNVERIFIED: regimes not researched; to be added by their CMP rows |

The CSR itself is not secret, but it is bound to `Z1` and is regenerated with each new key. The ZATCA public certificate is C2: kept with the unit's records for audit after the key is destroyed.

## 2. ZATCA key lifecycle
1. **Create unit.** An owner or admin adds an e-invoice unit (CMP-007). The signer creates a new key `Z1` for that unit (non-exportable in KMS/HSM for target & CMP-004, or KMS-encrypted under `S10a` in an isolated per-tenant signer for first pilot only) and returns only the key id and public key.
2. **CSR.** Built from tenant data (VAT number, unit serial, `uuid.uuid4()`, explicit `invoice_type` bitmask per ADR-0042) and signed by `Signer` with `Z1`. `CMP-004` tests a non-exportable KMS/HSM key regardless of whether the first pilot uses the fallback path.
3. **Compliance CSID.** The owner enters the OTP (`Z4`) in the dedicated UI form (never in chat). The onboarding job verifies/writes the tenant-unit HMAC one-use replay marker (TTL ≥ 90 min), sends CSR and OTP in one call, stores `Z2`, discards plaintext OTP from memory, and runs the compliance invoice checks.
4. **Production CSID.** The job requests `Z3` and stores it, then destroys `Z2`. The unit becomes `active`.
5. **Sign (no digest-signing oracle).** For each invoice the e-invoice component sends the **canonical invoice / `<xades:SignedProperties>` input** (never a bare digest and never trusting caller-supplied `tenantId`) over mTLS (`S03`) to the signer. The signer:
   - resolves the caller's tenant pool binding from mTLS workload identity (refusing any unit outside the caller's bound tenants/pools),
   - verifies the unit is `active`, requires a durable authorised invoice-issuance record bound to the tenant/unit and canonical payload, atomically reserves/checks the unit's own **ICV counter and PIH hash chain** (`ADR-0042`), and checks the **per-unit rate cap** (alerting on anomaly),
   - recomputes the canonical/SignedProperties digest itself and signs with `Z1` (in pilot fallback, inside an isolated per-tenant signer process that decrypts `Z1` for that single signature and immediately zeroizes memory).
   Every signature is audited with unit, ICV, invoice hash and key version, never the key.
6. **Renew.** From 60 days before expiry the platform alerts the tenant's admins at 60, 30, 14, 7 and 1 days. Renewal repeats steps 1 to 4 with a new key (`Z1`) and a new OTP (`Z4`). The new unit key handles all new invoices immediately; the old `Z1`/`Z3` stays enabled only for the bounded drain window of in-flight 24-hour reporting retries (`D-3`), then is disabled and destroyed after the waiting period.
7. **Expiry.** An expired or revoked CSID blocks issuing for that unit, fail closed with a clear error. The platform never issues an unsigned or wrongly signed invoice to keep business moving.
8. **Compromise.** Disable the key at once, block issuing, revoke with ZATCA (procedure UNVERIFIED; CMP-007 records it), onboard a new key, run an incident per [incident-response.md](incident-response.md).
9. **Tenant deletion or export.** Keys are destroyed, never exported. The tenant gets its data and certificates and must onboard again on any new system. This matches data-classification ("re-issued, not copied") and the reported rule that the e-invoice solution must not offer key export (`site:zatca.gov.sa` Detailed Guidelines v2 summary & third-party claim, https://zatca1.discourse.group/t/private-key-usage-and-storage/6380, accessed 2026-11-18, direct portal PDF timed out / UNVERIFIED until CMP-004).

## 3. Store options and selection criteria (decision deferred to INF-001)
| Option | Signs `secp256k1` non-exportably | Strengths | Weaknesses |
|---|---|---|---|
| Cloud provider KMS plus secret manager (AWS KMS, Azure Key Vault, GCP KMS) | AWS KMS: yes, `ECC_SECG_P256K1` (https://docs.aws.amazon.com/kms/latest/developerguide/symm-asymm-choose-key-spec.html, accessed 2026-11-18). Azure Key Vault: yes, `P-256K` / `ES256K` on `EC-HSM` (https://learn.microsoft.com/en-us/azure/key-vault/keys/about-keys-details, accessed 2026-11-18). GCP KMS: `EC_SIGN_SECP256K1_SHA256` (`HSM`) per search index, direct doc UNVERIFIED (`"OK"` stub) | Managed, hardware-backed (provider claim, UNVERIFIED locally), audit logs, IAM policies | Needs an in-country region of that provider (UNVERIFIED for KSA, UAE, Egypt, Qatar); provider lock-in behind our interface |
| Self-hosted OpenBao or Vault (KV plus transit), auto-unseal by a KMS or HSM | UNVERIFIED for pinned versions: both Vault Transit (https://developer.hashicorp.com/vault/api-docs/secret/transit, accessed 2026-11-18) and OpenBao Transit (https://openbao.org/docs/api/secret/transit/, accessed 2026-11-18) list P-256, P-384, P-521, Ed25519 only (OpenBao supports external KMS keys) | Runs on any in-country provider; strong policy and lease model; dynamic database credentials | Operations burden; `Z1` requires external KMS/HSM or first-pilot-only fallback; Vault BUSL and OpenBao MPL-2.0 licences UNVERIFIED under `LEG-004` |
| Dedicated or network HSM through PKCS#11 (provider HSM service or appliance) | Depends on model (UNVERIFIED) | Strongest key custody; can serve as the signer for `Z1` | Cost, scarce in-country, operations burden |

Selection criteria for INF-001:
1. Runs in each tenant's region (or legal advice says otherwise; Q-14, Q-129).
2. `secp256k1` non-exportable signing (mandatory before G3; pilot-only fallback rule if unavailable in KSA for first pilot).
3. Separate admin and use roles.
4. Per-call audit log exported to our audit store.
5. Workload identity, no static root credential in services.
6. Waiting period before key destruction.
7. Licence fits SaaS use (`LEG-004`).
8. Cost per tenant and per signature.

A likely shape, not decided: a provider KMS for signing and `S10a`/`S10b` key wrapping plus a secret manager (managed or OpenBao) for values.

## 4. Access model
- **Identities.** Each service has a short-lived workload identity (`S03`), never a shared static credential. Narrowest unit binding applies: **per tenant** for connector jobs (`S11`), pilot fallback signers (`Z1`), and support tooling (`S17`); **per bench pool** only for shared engine workers (`S05`, `S07` until per-tenant Redis ACL users exist).
- **Paths and policies (store vs application enforcement).** `{env}/platform/{service}/{name}` is readable by the named service only. `{env}/tenant/{tenantId}/{kind}/{name}` is scoped per tenant:
  - For single-tenant identities (`S09` gateway binding, `S11`, `S17`, fallback `Z1`), the store policy itself restricts reads to the bound `{tenantId}` (and signer validates caller pool placement over mTLS).
  - For **pool-shared engine workers (`S05`, `S07`)**, the store enforces **bench-pool workload identity** across sites assigned to that pool; the `stamped tenant == path tenant` guard (`SEC2-018`) is an **application check** inside the worker/adapter, not a store-enforced guarantee, and shared-pool exposure is logged as residual risk in `SEC-004`.
- **Separation (admin vs use, and ephemeral provisioning init).** Key administration (create metadata, rotate, disable, schedule destruction, change policy) and key use are different identities (`SEC2-019`). No identity holds both store administration and secret-read/use permissions. Provisioning (`PLT-003`) metadata creation uses a `provisioning-secret-admin` identity (never reads values); site creation (`create_site` / `harden_site`) uses a short-lived **ephemeral `provisioning-site-init`** job identity scoped strictly to `S06` and generating `S05`, `S08`, and `S21` locally and writing initial values through tenant/workflow-bound create-only paths (no store read, rotate, delete or policy permissions) for that single tenant before being revoked (`engine-adapter` workers never read `S06` or `S08`). Provisioning never reads `Z1`.
- **Humans.** No human reads a production C4 value. Support triggers rotation through the team console (`PLT-012`) with a reason and a ticket.
- **Break-glass (refines ADR-0007 item 7).** Root of the store, KMS administration, `S06`, and `S08` use are limited strictly to **platform-incident repair with zero tenant-data read** ; any tenant-data access requires prior tenant owner/admin approval via `PLT-019`, even when the tenant is unreachable. Until `PLT-019` exists, staff have no tenant-data access; cross-border staff access depends on `Q-14`. Break-glass requires both founders (until a third trusted person exists), hardware-key MFA, a written reason, and a time box of at most 1 hour. Every action logs off-box, alerts both founders, notifies affected tenants (including co-hosted tenants under `S06` policy), and triggers an **automated forced-rotation / credential revocation job at session close or T+60m expiry** (alerting at T+65m if unrotated). Agents never break-glass (`ALP-044`).
- **Caching.** Services may cache a secret in memory for at most its lease, 15 minutes by default (`D-2`). Nothing secret is cached on disk (except the admitted interim engine `site_config.json` gap before `INF-001` memory-backed storage, mitigated by backup exclusion below).

## 5. Keeping secrets out of logs, repos, errors and models
1. **Type.** All secret handling uses a `SecretValue` wrapper whose string, repr, JSON and pickle forms are `<redacted:{id}>`. The value is reachable only by an explicit `reveal()` at the point of use, which code review flags.
2. **Logs and telemetry.** A structured logger with a key deny-list (`password`, `secret`, `token`, `key`, `otp`, `authorization`, `cookie`, `csid` and variants). It also scrubs values by pattern, reusing the patterns in `scripts/scan_secrets.py` plus PEM headers, JWT shape and ZATCA token shape. Scrubbing happens before export. A hit is replaced and counted; a non-zero count alerts.
3. **Errors.** Exceptions never include secret values. Services return our error model; engine errors are mapped by the gateway (`PLT-024`). Crash reporters and core dumps are disabled or scrubbed in production.
4. **Process.** No secret on host `argv`, images, build args, env dumps, or health endpoints. **Known gap tracked for `PLT-003`:** `scripts/provision_tenant_site.py` (`ERP-003`) passes `--db-root-password`, `--admin-password`, and `--db-password` on container-shell `argv` (visible in container `/proc/<pid>/cmdline`). Before production (`PLT-003` / `G3`), site creation must switch to file descriptor, stdin, tmpfs secret file, or post-create SQL password setting (`SEC2-T35` checks `/proc/*/cmdline` inside the container).
5. **Repo.** `scripts/scan_secrets.py` runs in pre-commit and CI; GitHub secret scanning and push protection (`ADR-0021`). Test fixtures use generated throwaway keys created at test time, never committed.
6. **Model gateway.**
   - Fields classed C4 in manifests never enter a Tool API schema or result (`OPR-003`, `ALP-016`).
   - The gateway's outbound filter checks every prompt, tool result and model output for secret patterns and for **keyed HMAC fingerprints** (`S23`, plus secondary overlap key during rotation) maintained in memory by the gateway. Store pushes synchronous invalidations on `secret.created`/`secret.rotated` with a bounded max-staleness SLA. **Failure & oracle guard:** if the fingerprint feed fails at startup **or goes stale/drops mid-run**, model calls fail closed (`SEC2-037`). Checks scope to `tenant + platform` with uniform generic refusal (`agent.output_flagged`) so cross-tenant probing cannot use Tenant B prompts to enumerate Tenant A secrets (`SEC2-T37`).
   - **OTP never enters chat:** the Fatoora OTP is accepted only in the dedicated onboarding form; chat never prompts for an OTP, and pastes matching PEM/token/secret shapes are blocked before reaching a model (`SEC2-035`).
   - No system prompt, memory or Blueprint holds a secret.
7. **Exports and backups.** C4 is never in a tenant export. Engine site backups **explicitly exclude `site_config.json`** and site private keys (`SEC2-T08` scans backup archives); tenant payload backups encrypt exclusively under per-tenant `S10b` DEKs wrapped by `S10a` so restoring into another environment never restores production secrets (`data-classification` section 3, `data-retention` section 8).

## 6. Requirements
| ID | Requirement | Row |
|---|---|---|
| SEC2-001 | Every secret in section 1 is reached only through `SecretStore` or `Signer` | all callers |
| SEC2-002 | `SecretValue` redacts in string, repr, JSON, logging and exceptions | first code row |
| SEC2-003 | Production tenant secrets are stored in the tenant's region | INF-001, INF-005 |
| SEC2-004 | No production secret exists in dev, staging or preview, and no non-production secret in production | INF-012, INF-004 |
| SEC2-005 | Signing keys (`S02`, `S03`, `S15`, `S16`, `Z1`) are non-exportable KMS/HSM keys; `Z1` pilot fallback only per `ADR-0042` dated note `2026-11-18` (isolated per-tenant process, single-sig zeroize, replaced before G3) | INF-005, CMP-004 |
| SEC2-006 | Each ZATCA unit has its own key; no key is shared across units, tenants or environments | CMP-007 |
| SEC2-007 | The ZATCA key is never stored in an engine database field, file or log in clear | CMP-004, CMP-007 |
| SEC2-008 | The ZATCA key is used only by the isolated signer service; engine web workers never hold it | CMP-004 |
| SEC2-009 | Signer receives canonical invoice / `SignedProperties` input (not a bare digest), requires a durable authorised issuance record bound to the canonical payload, atomically checks/reserves unit ICV/PIH chain and rate cap, authenticates caller by mTLS (`S03`) bound to control-plane tenant/pool placement (never caller-supplied `tenantId`), and signs only for active units | CMP-004 |
| SEC2-010 | Every signature is audited with unit, ICV, invoice hash and key version | CMP-004, SEC-008 |
| SEC2-011 | Plaintext OTP (`Z4`) is entered only in the dedicated form, used in one call, and never stored, logged, or sent to chat/models; a tenant/unit HMAC replay marker (≥ 90 min TTL) enforces pre-call single use across workers | CMP-007 |
| SEC2-012 | CSID renewal generates a new key pair; prior `Z1`/`Z3` remain active only for the bounded retry drain window before disablement | CMP-007 |
| SEC2-013 | Expiry alerts at 60, 30, 14, 7 and 1 days to tenant admins | CMP-007 |
| SEC2-014 | An expired or revoked CSID blocks issuing for that unit, fail closed | CMP-004 |
| SEC2-015 | Compliance CSID is destroyed once the production CSID is active | CMP-007 |
| SEC2-016 | Keys are destroyed, never exported, on tenant deletion; export contains no C4; `S10b` DEKs are separate from `S10a` regional KEKs | DAT-006, DAT-007 |
| SEC2-017 | Services authenticate to the store with narrowest-unit workload identities (`S03`), no static shared credential | INF-002 |
| SEC2-018 | Single-tenant identities enforce tenant isolation at the store; pool-shared workers (`S05`/`S07`) enforce `stamped tenant == path tenant` as an application guard (residual risk tracked in `SEC-004`) | first code row, SEC-004 |
| SEC2-019 | Key admin (`provisioning-secret-admin`) and key use (`provisioning-site-init`, services) are separate identities; `engine-adapter` never reads `S06`/`S08` | INF-005, PLT-003 |
| SEC2-020 | No human reads a production C4 value; support can only trigger rotation | PLT-012, PLT-019 |
| SEC2-021 | Break-glass (`S06`, `S08`, store root) is limited to platform-incident repair with zero tenant-data read (tenant-data access requires prior `PLT-019` approval without a reachability exception, subject to `Q-14`), needs two founders, hardware MFA, reason, ≤ 1h box, off-box log, and alerts | INF-005, PLT-019 |
| SEC2-022 | Secrets checked out under break-glass are automatically force-rotated on session end / T+60m expiry (alerting at T+65m) | runbook, INF-005 |
| SEC2-023 | Affected tenants (and co-hosted tenants for `S06`) are notified when break-glass touches their paths/server | PLT-020 |
| SEC2-024 | Agents never read C4 and never break-glass | OPR-004 (ALP-016, ALP-044) |
| SEC2-025 | Rotation cadences in section 1 are enforced by a scheduled job with an overdue alert | first code row |
| SEC2-026 | Rotation uses dual-slot/overlap cutover (`S02`, `S04`, `S05`, `S07`, `S22`, `S23`) so in-flight calls and queries never fail | first code row |
| SEC2-027 | Staff departure triggers rotation of everything that person could reach | runbook |
| SEC2-028 | In-memory caching bounded by lease (`D-2`); engine `site_config.json` excluded from all backups until memory-backed `INF-001` lands | first code row |
| SEC2-029 | Logs and telemetry pass the scrubber; a hit alerts | PLT-015 |
| SEC2-030 | No secret appears in an error response, event, audit record (identifier only) or crash report | PLT-024, BPL-011 |
| SEC2-031 | No secret on host or container argv (container fd/stdin/file required before G3/PLT-003 prod), in images or in build arguments | INF-006, PLT-003 |
| SEC2-032 | `scripts/scan_secrets.py` and GitHub secret scanning stay required checks | CI |
| SEC2-033 | C4 fields are excluded from every generated tool schema and result | OPR-003 |
| SEC2-034 | Model gateway blocks any prompt, tool result or output matching secret patterns or `S23` keyed fingerprints (with synchronous invalidation and oracle-safe refusal) | PLT-009 |
| SEC2-035 | OTP (`Z4`) is accepted only in the onboarding UI form; chat never prompts for it and pastes matching PEM/token/secret shapes are blocked before any model call | PLT-009, WEB |
| SEC2-036 | No system prompt, memory, Blueprint or event payload holds a secret | BPL-003, OPR-001 |
| SEC2-037 | Store or fingerprint-feed unavailability / staleness (at start-up or mid-run) fails closed, never with a default or stale-expired value | all callers |
| SEC2-038 | Destruction of a key has a waiting period (`D-3`) and is logged | INF-005 |
| SEC2-039 | Connector credentials have read-only scopes where available and are revoked after a one-off import | DSC-010 |
| SEC2-040 | Production CI deploys require OIDC federation (`INF-003`, fail closed on static deploy keys unless `GOV-017` exception); deploy secrets reachable only from protected branches | INF-003 |
| SEC2-041 | Tenant database credentials (`S05`) and per-site `encryption_key` (`S21`) are distinct per site | PLT-003 |
| SEC2-042 | The engine Administrator password (`S08`) is random per site, stored only in the store, and its login is disabled outside break-glass | PLT-003 |
| SEC2-043 | Provisioning creates and destroys tenant secrets idempotently (`put-if-absent` bound to active `tenantId` + `workflowId`, never adopting secrets pending destruction) | PLT-003 |
| SEC2-044 | Restoring a backup into another environment never restores production secrets | DAT-004 |
| SEC2-045 | Every store read and admin action is logged with identity, path and outcome, never the value | INF-005, SEC-008 |
| SEC2-046 | Store product, KMS and region are chosen against section 3 criteria and recorded in an ADR | INF-001 |
| SEC2-047 | `S09` gateway impersonation enforces distinct bindings/credentials per principal kind (`human` shadow user vs `agent` engine user, ADR-0039) | PLT-003, ERP-008 |

## 7. Test cases
| ID | Case | Expected |
|---|---|---|
| SEC2-T01 | Log a `SecretValue`, format it, raise it in an exception, serialise it | Only `<redacted:id>` appears |
| SEC2-T02 | Service A (with no policy) reads a tenant path | Denied, audited |
| SEC2-T03 | Engine worker app guard with stamped tenant X requests tenant Y's secret path (plus `SEC-004` pool-breach test documenting pool-level exposure) | App guard denies; `SEC-004` records pool scope |
| SEC2-T04 | Request body names another tenant for a secret read or ZATCA signature | Body ignored; mTLS/stamped tenant used |
| SEC2-T05 | Signer asked to sign for a unit of another tenant, or pool P worker requests tenant on pool Q | Refused, audited, alert |
| SEC2-T06 | Signer asked to sign for an expired, revoked or disabled unit | Refused; invoice not issued |
| SEC2-T07 | Attempt to export `Z1` through every store and KMS API (and `CMP-004` non-exportable KMS/HSM sign test) | Not possible in target; fails policy in pilot fallback |
| SEC2-T08 | Scan the engine database, files, logs, and **backup archives** after onboarding and 100 signed invoices | No private key, OTP, CSID secret, or `site_config.json` found |
| SEC2-T09 | OTP submitted, then onboarding logs, audit, events and chat transcript searched | Plaintext OTP absent everywhere |
| SEC2-T10 | Reuse an OTP across two concurrent onboarding workers / replicas | First passes; second refused deterministically pre-call by HMAC replay marker (`Z4`) |
| SEC2-T11 | Renewal | New key id differs; old key drains only active retries then disables; no new invoice signed by old key |
| SEC2-T12 | Clock set to 61, 30, 7 and 0 days before expiry | Alerts at listed thresholds; at expiry issuing blocks |
| SEC2-T13 | Paste a PEM private key and a ZATCA token into chat | Not forwarded to model; user directed to form |
| SEC2-T14 | Tool result containing a live secret (planted canary) | Gateway blocks; `agent.output_flagged` |
| SEC2-T15 | Generated tool set for a tenant with C4-classed fields | No C4 field in any schema or result |
| SEC2-T16 | Engine error containing a database password reaches the gateway | Mapped error (`PLT-024`); no secret in response |
| SEC2-T17 | Commit a test file with a private-key header or token shape | Pre-commit and CI fail |
| SEC2-T18 | Inspect argv of all provisioning processes on host during a run | No secret values |
| SEC2-T19 | Support triggers rotation of `S05`/`S07` during live queries | Dual-slot overlap keeps active queries succeeding; old slot invalid post-cutover |
| SEC2-T20 | Single founder attempts break-glass | Refused |
| SEC2-T21 | Two-founder break-glass on a platform incident (with `S06` multi-tenant server audit) | Allowed for time box; logged; tenants notified; forced auto-rotation runs at close |
| SEC2-T22 | Agent run token asks for any secret path | Denied |
| SEC2-T23 | Store unreachable during sign, provisioning and gateway start | Each fails closed with clear error; no fallback value |
| SEC2-T24 | Token signing key rotation | Tokens signed by previous key verify until expiry; new tokens use new key |
| SEC2-T25 | Rotation job finds an overdue secret | Alert raised |
| SEC2-T26 | Tenant export | No C4 in archive |
| SEC2-T27 | Tenant deletion | `Z1`, `S05`, `S08`, `S09`, `S10b`, `S11`, `S21` destroyed (after waiting period); `S10a` intact; destruction logged |
| SEC2-T28 | Restore a production backup into staging | Production secrets not restored; staging uses its own |
| SEC2-T29 | Key admin tries to sign; `provisioning-site-init` / key user tries to change policy; `engine-adapter` reads `S06`/`S08` | All denied |
| SEC2-T30 | Provisioning step re-run after crash between "create secret" and "record secret" (same `workflowId`) | Adopted; exactly one secret exists (`SEC2-043`) |
| SEC2-T31 | Log line with a secret pattern emitted by a library | Scrubbed before export; alert |
| SEC2-T32 | Preview or dev environment configured with a production secret value (by fingerprint) | Start-up refuses |
| SEC2-T33 | Caller asks ZATCA signer for raw digest with no valid canonical invoice / ICV / PIH chain or exceeds rate cap | Refused, audited, alert (`SEC2-009`) |
| SEC2-T34 | Pilot fallback signer process crash / memory scan / cross-tenant isolation | Single-tenant process only; memory zeroized after single signature |
| SEC2-T35 | Inspect `/proc/*/cmdline` **inside** the provisioning container during `create_site` | Zero secret values on container argv (once non-argv delivery lands for prod) |
| SEC2-T36 | Gateway fingerprint cache stale (> SLA), `S23` HMAC key rotated, or feed drops mid-run | Refreshes/re-indexes on `secret.rotated`; fails closed on mid-run outage/staleness |
| SEC2-T37 | Cross-tenant secret probing oracle: Tenant B prompts gateway with Tenant A's canary string vs random string | Both return identical generic block/handling without leaking Tenant A existence |
| SEC2-T38 | Break-glass operator fails to manually trigger rotation after 1-hour session closes | Automated T+60m forced rotation revokes/rotates credential; T+65m overdue check alerts |
| SEC2-T40 | Two founders attempt tenant-data access without tenant-approved PLT-019 grant, including unreachable tenant or missing PLT-019 | Refused; repair-only tooling cannot read tenant data |
| SEC2-T41 | Compromised pool reader bypasses stamped-tenant guard and reads another site in the same pool, then another pool | Same-pool exposure demonstrated and recorded in SEC-004; other-pool access denied; no claim of store tenant isolation |
| SEC2-T39 | CI production deploy attempted with static cloud key instead of OIDC (`S18`) | Refused (`SEC2-040`) unless valid `GOV-017` exception |

The store and signer capabilities above are requirements, not production evidence. Engine backup exclusion and Administrator-login disablement remain UNVERIFIED on the pinned engine until SEC2-T08 and provisioning hardening probes pass. Memory-backed site config remains plaintext readable by pool workers; backup exclusion remains mandatory after migration to tmpfs. Managed hardware-backed availability is UNVERIFIED; candidate provider documentation: https://learn.microsoft.com/en-us/azure/key-vault/keys/about-keys-details (source previously accessed 2026-11-18; deployment proof required under INF-001).

## 8. Decisions needed
1. **D-1** Store product, KMS or HSM and region (`INF-001`, `Q-129`). Criteria in section 3.
2. **D-2** Maximum in-memory lease for cached secrets (proposed 15 minutes).
3. **D-3** Waiting period before key destruction (proposed 30 days for tenant keys, 7 for ZATCA keys after renewal to cover pending submissions).
4. **D-4** **Resolved (`2026-11-18`):** First-pilot-only exception permits the fallback in-process signer key (`Z1` encrypted at rest under `S10a`, isolated per-tenant process, single-sig zeroization, replaced with non-exportable KMS/HSM before G3), while `CMP-004` **must** test a non-exportable KMS/HSM key (`ADR-0042` dated note).
5. **D-5** Who holds break-glass while only two founders exist, and what happens when one is unreachable (an emergency third party, or accept delay; subject to `Q-14` for cross-border staff access).
