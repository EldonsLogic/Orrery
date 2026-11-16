# Fake engine adapter and conformance suite (BPL-025)

Status: draft. Owner: eldon. Contract: [contracts/engine-adapter.md](../../../contracts/engine-adapter.md) 0.1.2 (sections 14 and 15). Decision: ADR-0028 (Proposed).

An in-memory fake of every adapter operation (`capabilities`, `provision_site`, `site_status`, `plan`, `preview`, `apply`, `rollback`, `export_config`, `sync_members`, `health`) and the pytest suite that holds any adapter to the contract. It models behaviour only; **nothing here is evidence about a real engine (UNVERIFIED until ERP-001 and BPL-012 run it on a bench).** Synthetic data only.

## What the fake does
- `apply` and `rollback` run the six stages (acquire, inspect, prepare, execute, reconcile, finalize) with compensation. Each step is journaled before it runs; a failure compensates in reverse order by running the matching step of the stored inverse (same pointer; an initial build has no inverse, so the undo is derived from the journal as contract 5.6.2 says: additions quarantined or disabled, settings set back to the journaled value), then the export hash is compared with the pre-apply hash. Quarantined leftovers of compensated additions stay in `retained`. A missing or wrong inverse step makes the compensation fail (`recovery_required`). A compensation failure, or a failed finalize, leaves the site `recovery_required`, which blocks later `apply`, `rollback` and `plan` (verdict `rejected`).
- Events follow the contract's 8.2 table: a 4.2 refusal emits one `permission.denied`; other refusals before the operation record exists (including `idempotency_conflict` and `concurrent_change` in `acquire`) emit nothing; an apply or rollback rejected in `inspect` returns outcome `rejected` and emits one `blueprint.apply_failed`. After a rollback, `site.applied` names the artifact rolled back to.
- One lock per site; keys are scoped (tenant, operation, key) and bound to the sha256 of the input; plan tokens bind tenant, artifact hash, export hash and adapter version, and expire.
- Tenant comes only from `context.tenantId`. Unknown input keys, a bad context, a bad artifact hash, unknown versions and over-limit requests are refused before anything changes.
- Removal is quarantine; a re-add with the same definition restores the element at its old position with its data. The fake never removes stored data.
- Errors carry no free text; internal evidence stays in the adapter.

## Run
From the repo root (needs `pip install -r services/blueprint/requirements.txt`):
```
python3 -m pytest services/blueprint/tests/adapter -q
```
Each test is named after its item: `test_adp_c_043_...` is ADP-C-043. The harness wrapper in `tests/adapter/conftest.py` validates every response against its schema (ADP-C-001), checks error shape (ADP-C-005) and scans for engine leaks (ADP-C-006) on every call of every test.

## Running the suite against another adapter
Implement `AdapterHarness` ([harness.py](harness.py)) and point `ADAPTER_HARNESS=module:factory` at a zero-argument factory. The suite imports only the harness, the contract schemas and the canonical-hash helper, never adapter internals.
Contract section 15.1 (0.1.2) defines every harness method and its semantics; all are required: a harness that lacks one makes the tests that need it fail, and any skipped test fails the run, so a green run never hides a missing capability. Besides `call`, `fault`, `data_probe`, `auth_probe`, `action_probe`, `events` and `reset`:

| Extension | Used by | Meaning |
|---|---|---|
| `on_lock_held(callback)` | 042 | run `callback` once while the next apply or rollback holds the site lock |
| `advance_time(seconds)` | 034 | move the adapter clock (plan token expiry) |
| `set_site_state(tenant, state)` | 017 | put a site in `provisioning` or `failed` |
| `audit_log()` | 070 | audit records with `auditId` |
| `dropped_data()` | 050 | pointers whose data an operation removed (must be empty) |
| `plan_evidence(ref)` | 050 | the adapter's internal plan evidence (storage statements) for an `evidenceRef` |
| `execution_journal()` | 047, 071 | every step run, in order: `artifactId`, `seq`, `phase` (`execute` or `compensate`) |
| `without_test_hooks()` | 069 | a production-like instance with no fault hooks |

`fault(stage, ...)` stages: `prepare`, `execute` (with `step_seq`), `reconcile` (with `post_condition_id`), `finalize`, `deadline` (the deadline passes during `execute`: the call returns `timeout` after the artifact finished, and a retry with the same key returns the stored outcome). `during_compensation=True` makes the compensation that follows also fail.
`data_probe`, `auth_probe` and `action_probe` take an optional `tenant_id` (default: the harness's tenant).

## Files
| File | Content |
|---|---|
| `fake.py` | The fake adapter |
| `contract.py` | Canonical JSON, hashes, schema loading (shared by fake and suite) |
| `harness.py` | `AdapterHarness`, `FakeHarness`, `make_harness` |
| `testkit.py` | Contexts, sealed artifacts, an initial-build artifact, derived artifacts, call helpers |
| `../tests/adapter/` | The suite, `golden_export_hashes.json` (ADP-C-060) and `test_fake_selfcheck.py` |

## Stand-ins and known gaps
- `testkit.initial_build` stands in for the compiler (BPL-004): one step per Blueprint element, built from `contracts/examples/blueprint-trading-minimal.json`, so the samples (which start at revision 1) have a site to apply to.
- The fake declares `role.*` kinds `gated` and `binding.*` kinds `unsupported` so ADP-C-028 is exercised; `PROTECTED` entities (`general_ledger`, `user_account`) are a fixture list (open question 6 in the contract).
- The `exportedProperties` keys are the contract's (5.1; the Blueprint `i18n` settings are keyed `settings_intl`); the property lists inside them are the fake's own. `golden_export_hashes.json` depends on these lists; ADP-C-060 needs them agreed with the real adapter (open question 16.3).
- Not modelled: signature verification, real deadlines, real concurrency (the lock hook stands in), `state_in_use`, `multi_statement`.
