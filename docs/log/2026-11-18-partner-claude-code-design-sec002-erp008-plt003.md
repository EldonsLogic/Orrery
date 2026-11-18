# Session log: design-sec002-erp008-plt003

Date: 2026-11-18
Author: partner
Tool and model: claude-code / opus-5.5
Plan IDs: SEC-002,ERP-008,PLT-003

## Summary
Wrote three Proposed design ADRs, with no code, for secrets management (ADR-0038), Blueprint role to engine permission mapping (ADR-0039) and the tenant provisioning service (ADR-0040). Each ships in its own PR and each row stays `doing` until a cross-model review and founder acceptance.

## Files touched
- docs/decisions/ADR-0038-secrets-management.md, docs/security/secrets-management.md, INDEX row: SEC-002 (branch `sec-002-secrets-design`, this PR).
- docs/decisions/ADR-0039-role-and-permission-mapping.md, docs/architecture/role-and-permission-mapping.md, INDEX row: ERP-008 (branch `erp-008-role-mapping-design`).
- docs/decisions/ADR-0040-tenant-provisioning-service.md, docs/architecture/tenant-provisioning.md, INDEX row: PLT-003 (branch `plt-003-provisioning-design`).
- docs/PLAN.md: each row set to `doing` on its own branch.

## Decisions
- ADR-0038 (Proposed):
  - One `SecretStore` and `Signer` interface, with path-scoped workload identities.
  - Signing keys stay in the KMS.
  - The ZATCA secp256k1 key sits behind a separate signer: non-exportable in a KMS or HSM where the backend supports the curve (AWS KMS does; Vault and OpenBao transit do not), otherwise a fallback held in the signer process only.
  - The OTP is never stored.
  - No human reads production C4; break-glass needs two founders.
  - The model gateway never receives a secret.
  - The store product and region are deferred to INF-001 and Q-129.
- ADR-0039 (Proposed):
  - Adapter-owned roles only; actions map by a fixed table.
  - Hidden and read-only fields become deterministic permission levels (at most 9 extra per entity).
  - Branch, warehouse and department scopes become user permissions; own_records becomes the owner-only flag; assigned_records is denied in the engine.
  - No role profiles.
  - Everything unmapped or unresolved is denied, with no fallback to any built-in role.
  - Drift fingerprint.
  - Agents get their own engine principal, draft-only.
  - 34 denied-case tests listed.
- ADR-0040 (Proposed):
  - A control-plane step machine with durable state in the control-plane database (not the tenant database).
  - Steps observe before they act; keys and identifiers derive from the tenant id; secrets are put-if-absent.
  - Leases with fencing tokens.
  - No route until verified.
  - Cancel compensates only before routing.
  - Deprovisioning reuses the machinery under legal hold and crypto-shredding.
- ADRs reference each other and ADR-0041 (ERP-026, written in parallel by another session; first numbered ADR-0036, renumbered because #120 took 0036) while all are in open PRs.

## Founder questions raised (in the detail docs, not added to open-questions.md to stay inside allowed paths)
- SEC-002 D-1 to D-5: store product and region, cache lease, destruction waiting period, whether the ZATCA fallback signer is acceptable for the first pilot, break-glass with two founders.
- ERP-008: the agent "shadow user" wording conflict between ALP section 3.1 and the brief; per-member scope values (schema change); assigned_records mechanism; mixed-scope members.
- PLT-003 D-1: `services/control-plane/` is Eldon's lane but PLT-003 is the partner's.

## Sources checked (accessed 2026-11-18)
- AWS KMS key spec reference (`ECC_SECG_P256K1`): https://docs.aws.amazon.com/kms/latest/developerguide/symm-asymm-choose-key-spec.html
- Vault transit key types: https://developer.hashicorp.com/vault/api-docs/secret/transit
- ZATCA onboarding (third-party, UNVERIFIED against ZATCA's manual): https://learn.microsoft.com/en-us/dynamics365/finance/localizations/e-invoicing-sa-onboarding, https://www.wafeq.com/en-sa/tax-and-reporting/zatca-phase-2-integration:-5-steps-to-avoid-onboarding-errors
- Engine permissions: https://docs.frappe.io/framework/user/en/basics/users-and-permissions, https://docs.frappe.io/erpnext/perm-levels

## Not checked
- The ZATCA official Developer Portal Manual was not read: the curve, OTP window and certificate validity are UNVERIFIED.
- The ERPGulf app's key handling was not inspected.
- None of the engine behaviours was run on the bench.

## Tokens or cost
Unknown.

## Next step
Cross-model review of each PR (a different model), then founder acceptance. After that: SEC-002 implementation row once hosting is chosen; ERP-008 implementation with the DENY tests; PLT-003 implementation once the lane question D-1 is answered.
