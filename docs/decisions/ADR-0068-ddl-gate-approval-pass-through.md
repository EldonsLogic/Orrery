# ADR-0068: A signed, single-use DDL-gate grant lets the guarded field path add a unique or index constraint to an adapter-owned custom field on an allow-listed built-in engine type

Status: Proposed
Owner: partner
Approved by: pending (security review by a different model, then Eldon line by line; RULES 42 because this touches authorisation and the audit trail)

Plan ID: BPL-040 (design only; no code until this ADR is Accepted and reviewed). Answers Q-603 as the partner decided it. Internal document: it names the engine (ADR-0016). Paths below shorten `apps/engine/change_engine/change_engine/` to `CE/`. Line numbers are at commit f3c0712f.

## Context
- A Blueprint with a unique or indexed field that `entity.add` must add to a built-in engine type (`customer_code` on Customer, `supplier_code` on Supplier) cannot apply. The backend refuses it with `unique_or_index` before any write (`CE/adapter/frappe_backend.py:896-903`). The plan already marks it `gated` (`CE/adapter/engine.py:1362-1363`; `CE/adapter/frappe_backend.py:565-567`), and apply then requires `approvals.gateApproved` (`CE/adapter/engine.py:1771-1779`). But that approval is only a ULID whose presence and format the adapter checks; its truth is the control plane's (`contracts/engine-adapter.md:116`, 15.3). Nothing reaches the backend, so the backend refuses even when the approval is present.
- The same refusal covers: an existing field (native or earlier custom) that lacks the constraint (`frappe_backend.py:888-894`); a quarantined field restored without it (`frappe_backend.py:1016-1021`); and `field.set_property` on `/unique` or `/indexed` unless the engine field already holds the value (`frappe_backend.py:643-652`, using `_has_constraint` at `:916-924`). The tests pin this: `CE/tests/test_bpl_031_entity_add_existing_doctype.py:252-271` and `:497-575`.
- The DDL gate approves exactly one `ALTER TABLE ... ADD COLUMN custom_*` statement (`CE/guarded_apply/ddl_plan_gate.py:55-60`). It rejects `ADD UNIQUE` and `ADD INDEX` (`:381-408`). For a new unique column the engine's diff yields two statements: the column with inline `unique`, then `ADD UNIQUE INDEX IF NOT EXISTS` (`:235-236`, `:282-289`, `:335-378`). A rejected plan falls back to `QUEUE_FOR_CONTROLLED_ADMIN_DEPLOYMENT` (`CE/api/endpoints.py:428-429`). That queue does not exist yet.
- The guarded six-stage path already runs in this order: lock, inspect and gate, durable audit intent, engine operation, reconcile, finalize (`CE/guarded_apply/schema_reconciler.py:97`, `:127-183`, `:185`, `:207`, `:216`, `:230`). The intent goes to the site audit table before DDL (`CE/api/endpoints.py:974-1015`). Each engine statement is checked against the approved plan before it runs (`endpoints.py:1080-1090`). A target with unresolved `RECOVERY_REQUIRED` blocks further deployments (`schema_reconciler.py:118-124`). Today any index change found at reconcile goes to `RECOVERY_REQUIRED` (`schema_reconciler.py:301`; `ddl_plan_gate.py:693-760`).
- Rules this must meet: approvals are bound to tenant, exact action, data revision, approver and expiry (ADR-0027; RULES 23). Roles and identity come only from the authenticated session, and failures fail closed (RULES 41). `onBehalfOf.roleIds` never authorise a configuration operation (`contracts/engine-adapter.md:41`, ADP-C-012). Apply is journaled and recoverable, not universally reversible (ADR-0028). Signing keys stay in the KMS (ADR-0038 item 2). The engine stays invisible (ADR-0016).

## Decision

### 1. The grant
1. The approval travels as a **DDL-constraint grant**: canonical JSON (contract 5.8 rules) signed with **ed25519**. Fields:
   `v` (1); `typ` (`ddl_constraint_grant`); `kid`; `tenantId`; `siteClass` (`sandbox`, `test` or `production`); `operation` (`apply` only); `artifactId`; `contentHash`; `baseConfigHash` (sha256 of the site export at plan time, the same value the plan token binds, `CE/adapter/engine.py:1378-1388`); `gateApprovedId` (the ULID sent in `approvals.gateApproved`); `scope`, a list of `{stepSeq, kind, subject, doctype, fieldname, constraint}` where `constraint` is `unique` or `index`; `approver` (`kind` = `user`, `id`, `authTime`, `mfa` = true); `iat`; `exp`; `nonce` (128 random bits).
2. **Issuer: the control-plane approval service, and only that service.** It issues a grant when a human records the gate approval on the review screen (ADR-0049, ADR-0050) in an authenticated session. It takes `approver` from that session's identity token, never from a request body. It refuses agents, support grants and service callers, and refuses unless the action-policy row for a gate approval allows this human (ADR-0027). It computes `scope` from the compiled artifact it was shown: one entry per step that adds a constraint.
3. **Key:** a new KMS ed25519 signing key, inventory entry "DDL-constraint grant signing key" (proposed `S24`). It is used through ADR-0038's `Signer` interface. Only the approval service's workload identity may sign with it, and the key never leaves the KMS. The adapter holds only the public keys, by `kid`, from its environment's secret store. No key, private or public, is ever in the repo. Production, staging and dev keys are separate (ADR-0018).
4. **Why a signature, not an HMAC:** with an HMAC the verifier holds the minting secret, so a compromised adapter or engine worker could mint its own approvals. With a signature the backend can check a grant but cannot create one.
5. **Lifetime:** `exp - iat` is at most 60 minutes. The verifier enforces this itself, so a buggy issuer still cannot produce a long-lived grant. Allowed clock skew is 60 seconds.

### 2. The one audited code path
6. All constraint DDL goes through **one function in `CE/guarded_apply/`**: a constraint mode of the six-stage deployment that reuses `execute_single_field_deployment`'s stages and gate. No other caller may pass a grant. The backend receives the grant as an explicit argument, never from module or request state.
7. `CE/adapter/engine.py` checks the grant when it admits an apply (next to `:1771-1779`), so a bad grant is refused with no effect. The constraint path checks it again right before the effect. That second check is the one that counts.
8. **What it covers:** `entity.add` and `field.add` of a new adapter-owned custom field (`custom_` prefix) with `unique` or `indexed`; restoring a quarantined adapter-owned field whose constraint is missing; and `field.set_property` on `/unique` or `/indexed` from false to true on an adapter-owned custom field (item 17). Only on a doctype in the **constraint allow-list**: a versioned data file the adapter loads. It starts with Customer and Supplier. It never includes a protected entity (`CE/adapter/mapping.py:250`) and never a `text` or `longtext` field.
9. **Checks before the effect, in this order** (any failure refuses, fail closed, with a neutral code):
   1. The signature verifies with an allow-listed `kid`, and the algorithm is ed25519 only (nothing in the token chooses it). `typ` and `v` match.
   2. `iat ≤ now + skew` and `now ≤ exp`, and the lifetime is at most 60 minutes.
   3. `tenantId` equals the authenticated `context.tenantId` and the tenant of the site the backend opened through its resolver (`CE/adapter/frappe_backend.py:129-141`, `:208-211`). `siteClass` equals the site's class.
   4. `artifactId`, `contentHash` and `gateApprovedId` equal the apply input. `baseConfigHash` equals the current site export hash.
   5. **Scope equality:** the set of constraint steps the backend derives from the artifact equals `scope` exactly, entry by entry. The backend derives each entry (`stepSeq`, kind, subject, doctype, mapped fieldname, constraint) from the artifact and the mapping, never from the grant. Extra or missing entries refuse.
   6. The doctype is on the allow-list, and the field is adapter-owned and of an indexable type.
   7. The advisory lock is held (`schema_reconciler.py:97`). The live DDL plan contains exactly the statements expected for this step: `ADD COLUMN` of this field (new field only) and `ADD UNIQUE INDEX IF NOT EXISTS` or `ADD INDEX` on this column only, on this table only. No `MODIFY`, no `DROP`, no other column. The per-statement check at `endpoints.py:1080-1090` enforces the same list at run time.
   8. Table size: if the row count exceeds the configured ceiling, refuse with `table_too_large` (item 21).
   9. For `unique` on an existing column: `SELECT ... GROUP BY col HAVING COUNT(*) > 1` finds no duplicates among non-null values, else refuse with `duplicate_values`. A new column needs no check (all rows are NULL). The build must prove on a real bench how the engine stores an empty value in a unique Data column. If it stores `''` rather than NULL, the path also refuses a unique field that is not `required`.
10. **Audit before effect.** The nonce is consumed and the grant audit record written in one committed transaction in the adapter's regional store: an `INSERT` with a unique key on `(tenantId, nonce)`. Then the existing Stage 3 intent is committed to the site audit table. Only then does DDL run, with the session `lock_wait_timeout` from `schema_reconciler.py:208` set to a few seconds. If either write fails, nothing runs (`failed_clean`).
11. **Audit record:** auditId, requestId, correlationId, tenant, site, siteClass, caller service, `onBehalfOf` (recorded, not trusted), grant `kid`, nonce, the sha256 of the grant (not the grant itself), approver id, `authTime`, `iat`, `exp`, `gateApprovedId`, artifactId, contentHash, stepSeq, doctype, fieldname, constraint, row count, the duplicate-check result, approved statements, executed statements, before and after snapshot hashes, outcome and stage timings. These are internal only (`contracts/engine-adapter.md:200`).
12. The grant is spent once its nonce is consumed (item 10), whatever the outcome. A refusal at item 9 does not spend it. An idempotent replay with the same idempotency key returns the stored outcome without consuming anything. Any new attempt needs a new grant.

### 3. Failure and rollback
13. **Duplicates in existing data:** refused at item 9.9 before anything is consumed. If a duplicate is written between the check and the DDL, the database rejects the unique index. The statement fails and the table is unchanged, so the outcome is `failed_clean` and the grant is spent. The database, not the pre-check, is the final arbiter.
14. **DDL fails partway:** each `ALTER TABLE` statement either completes or leaves the table as it was (UNVERIFIED for the pinned MariaDB version under crash; the build proves it on a real bench). If the first statement adds the column with its inline unique index and the second (`IF NOT EXISTS`) then fails, the index already exists, and reconcile accepts the state only if the column and index match the approved plan. Anything else is `RECOVERY_REQUIRED` under the existing rows (`schema_reconciler.py:266-319`). The reconciler and `assess_applied_ddl` are extended to accept **exactly** the approved index on the approved column and to treat any other index change as before.
15. **Crash between DDL and the final audit:** the Stage 3 intent and the consumed nonce are already durable. On restart the deployment is `PREPARED` with no outcome. The target is blocked (`schema_reconciler.py:118-124`) until reconcile finalizes it as `applied` (matches the plan) or an operator resolves `RECOVERY_REQUIRED`. Recovery never re-runs DDL on the old grant.
16. **BPL-008 rollback does not drop the constraint.** The inverse of `entity.add` or `field.add` is quarantine, which hides the field and keeps the column (`CE/adapter/frappe_backend.py:1126-1129`; contract line 142: destructive inverse steps are quarantine). The index stays with the column. New rows hold NULL, which a unique index allows. Re-applying restores the field, and `_lacks_constraint` passes because the index is still there. The inverse of a `set_property` false-to-true is a drop, which stays refused (item 18), so rolling back that artifact is refused with no effect. Dropping a constraint is a separate future decision. This depends on BPL-041 moving the `unique_or_index` refusal into `check_ready`, so the rollback is refused before any step runs.

### 4. What stays refused
17. **`field.set_property` is covered by the same path, false to true only.** Without it a field added earlier without the constraint could never gain it, and the case adds no new risk beyond the duplicate check, which the path runs anyway. A second path for the same DDL would break "one audited code path".
18. Everything else keeps `unique_or_index`: any step without a valid grant; any step whose scope does not match; native engine columns (such as `item_code`); doctypes off the allow-list; true to false (dropping a constraint); composite indexes; `text` and `longtext`; tables above the ceiling; and every rollback that would drop a constraint.

### 5. Threats and abuse cases
| Threat | Control | Test that proves it |
|---|---|---|
| Replay of a used grant | Nonce consumed under a unique key before effect (item 10) | `test_bpl_040_replayed_grant_is_refused_and_no_ddl_runs` |
| Grant for tenant A used on tenant B | `tenantId` must equal the authenticated context and the resolved site (9.3) | `test_bpl_040_cross_tenant_grant_is_refused` |
| Sandbox grant used on production | `siteClass` match (9.3) | `test_bpl_040_sandbox_grant_on_production_is_refused` |
| Scope widening (other step, field, doctype or constraint) | Scope equality against what the backend derives (9.5); per-statement DDL check (9.7) | `test_bpl_040_grant_for_another_field_or_step_is_refused`, `test_bpl_040_extra_scope_entry_is_refused` |
| Grant reused on a changed artifact or drifted site | `artifactId`, `contentHash`, `baseConfigHash` (9.4) | `test_bpl_040_grant_bound_to_old_config_hash_is_refused` |
| Expired, future-dated or long-lived grant | `exp`, `iat`, 60-minute maximum in the verifier (9.2) | `test_bpl_040_expired_grant_is_refused`, `test_bpl_040_overlong_grant_is_refused` |
| Forged grant, wrong key or algorithm switch | ed25519 only, `kid` allow-list, public key only in the adapter (items 3-4, 9.1) | `test_bpl_040_bad_signature_unknown_kid_and_other_alg_are_refused` |
| Caller-supplied approver or roles | Approver only inside the signed grant, from the issuer's session; `onBehalfOf` ignored for authority | `test_bpl_040_approver_in_input_or_roles_change_nothing` |
| Agent or support obtains a grant | The issuer refuses non-user approvers; the verifier requires `approver.kind` = `user` | `test_bpl_040_grant_with_agent_approver_is_refused` |
| Race: a duplicate inserted between check and DDL | The unique index build fails in the database, `failed_clean` (item 13) | `test_bpl_040_duplicate_inserted_after_check_fails_clean` |
| Race: two applies with one grant | Advisory lock plus the unique nonce key | `test_bpl_040_concurrent_applies_one_grant_only_one_runs` |
| Long lock on a large production table | Row ceiling (9.8); short `lock_wait_timeout` so the DDL fails fast instead of queueing; above the ceiling goes to a controlled admin deployment | `test_bpl_040_table_above_ceiling_is_refused`, bench `test_bpl_040_lock_wait_times_out_fails_clean` |
| Engine names leak in errors | Neutral reason codes only; diagnostics internal | `test_bpl_040_refusals_carry_no_engine_names` |
| No effect without audit | Nonce and intent committed before DDL; a forced failure of either write stops the DDL | `test_bpl_040_audit_write_failure_runs_no_ddl` |

### 6. Test plan for the build row
All of the threat-table tests above, plus:
- `test_bpl_040_entity_add_unique_customer_code_with_valid_grant_applies_and_engine_reports_unique`
- `test_bpl_040_indexed_supplier_code_with_valid_grant_applies_and_engine_reports_index`
- `test_bpl_040_set_property_unique_false_to_true_with_grant_applies`
- `test_bpl_040_set_property_true_to_false_stays_refused`
- `test_bpl_040_existing_duplicates_refused_before_nonce_is_consumed`
- `test_bpl_040_native_column_and_off_allow_list_doctype_stay_refused`
- `test_bpl_040_no_public_key_configured_keeps_unique_or_index_refusal`
- `test_bpl_040_crash_after_ddl_before_finalize_blocks_target_and_reconciles_to_applied`
- `test_bpl_040_reconcile_accepts_only_the_approved_index`
- `test_bpl_040_rollback_quarantines_and_keeps_the_constraint`
- `test_bpl_040_rollback_of_set_property_unique_is_refused_before_any_step`
- `test_bpl_040_idempotent_replay_does_not_consume_a_second_nonce`
- bench: `test_bpl_040_empty_value_storage_in_unique_data_column` and `test_bpl_040_alter_atomic_on_failure` (real MariaDB)
- The existing BPL-031 refusal tests stay green unchanged when no grant is sent.

### 7. Non-goals and follow-up rows
- Not in scope: dropping or relaxing a constraint; native engine columns; composite or partial indexes; `MODIFY COLUMN`; tables above the ceiling; the controlled admin deployment queue; signing compiled artifacts (contract 16.8); changing the Blueprint schema.
- Follow-up rows, to be added to `docs/PLAN.md` by the founders (this ADR does not edit the plan):
  - partner, `apps/engine/`: build the verifier and the constraint path to items 6-16 with the tests in section 6. The path stays off (refusing as today) while no public key is configured, so it does not depend on Eldon's rows (ADR-0025).
  - eldon, `contracts/` and `services/control-plane/`: an additive optional `approvals.ddlConstraintGrant` in the apply schema (minor contract bump), and the issuer in the approval service.
  - shared, `docs/security/`: add the proposed `S24` to the secrets inventory and the threat model.

## Alternatives rejected
- A controlled admin deployment only (a human runs the DDL by hand): no binding to the approved change, a second unaudited path, and it does not scale past the first pilots. It stays as the fallback above the ceiling.
- Adding the column without the constraint: rejected in the BPL-031 review, because the Blueprint would apply without enforcing uniqueness.
- An HMAC grant: the verifier could mint (item 4).
- The adapter fetching the approval record from the control plane by ULID: adds a runtime dependency and a new trust channel into the engine side. A signed token is checked offline.
- Trusting `approvals.gateApproved` as it stands: it is an unsigned id with no scope, approver or expiry.

## Consequences
- Easier: Blueprints with unique customer or supplier codes apply on built-in types, with an approval that is bound, single-use and audited.
- Harder: a KMS key, a new contract field and an issuer must exist before anything works in production. The reconciler must learn to accept exactly one approved index.
- Open for founders: the initial allow-list (Customer and Supplier proposed); the row ceiling (to be set in configuration after a bench measurement); whether the approver must differ from the requester for this gate (action-policy row); and MFA step-up for production grants (ADR-0047).

## Supersedes
None.
