# Action outcome reconciliation

Status: draft
Owner: partner
Approved by: pending (Tier 3 line-by-line review, ADR-0031; cross-model review)

Plan ID: ERP-029. Follows ERP-023 (engine action-policy admission). Internal documentation; it may name the engine (ADR-0016). Built offline only: `apps/engine/change_engine/change_engine/guarded_apply/action_outcome_reconciler.py`, tested by `tests/test_erp_029_action_outcome_reconciliation.py`. Every engine fact below is UNVERIFIED unless a named test covers it; no test here touches a real bench.

## 1. Why
ERP-023 commits an admission (audit record plus request, idempotency and approval claims) before any effect, then appends one outcome per admitted request. A handler that fails after dispatch records `unknown`. A process crash, or a failed outcome write, leaves no outcome at all. Neither case may be retried blindly: the effect may already be in the ledger. ADR-0027 puts postings on the human floor, so an outcome nobody can prove must reach a human, and the claims must stay reserved until then.

## 2. Outcome states
| State | Meaning | Final |
|---|---|---|
| `applied` | A durable effect exists for this exact admission. | yes |
| `failed` | No effect exists and none can commit later. | yes |
| `unknown` | Neither is proven. The claims stay reserved; nothing is retried. | no |

Sources, in order:
1. The enforcer recorded `applied` or `failed`: taken as final (reason `recorded`). It is not re-read from the engine. Verifying recorded outcomes against engine state is out of scope here.
2. The enforcer recorded `unknown`, or recorded nothing: resolved only by an exact read-back (section 3).

Once `applied` or `failed` is journaled for a request it is not re-read from the engine. A unique index allows one final entry per tenant and request. Under `BEGIN IMMEDIATE`, `_commit()` re-reads `outcome_for` before inserting so a final outcome recorded while the read-back was running wins over the read-back. If a recorded final outcome later contradicts an already journaled final state for any request of the tenant (including requests outside `request_ids`), `_commit()` appends one HMAC-chained `outcome_conflict` entry (`state = 'unknown'`, `reason = 'outcome_conflict'`, `stuck = 1`, guarded by a partial unique index) for that request. The conflict entry is written once, sticky, returned as escalated (`stuck: true`), and never resolved automatically. The run continues in the same transaction with the other requests, which keep reconciling and escalating. While any conflict is open for the tenant (evidence that the reader's `not_applied` fence failed), no new `failed` outcome is finalised from a `not_applied` read-back; it stays `unknown` with its own reason, `conflict_hold` (not `readback_pending`, which is a real pending answer), so it escalates and the held-back request stays distinguishable in the journal. Recorded final outcomes, exact `applied` read-backs and stuck escalations may still be written.

## 3. Resolving unknown: exact read-back by idempotency key
The reconciler never calls a handler, never retries, and never releases a claim. It reads.

- **Binding.** At admission the store now also writes `(tenant, request, submitter, idempotency key)` to `action_policy_admission_keys`, in the same transaction as the claims (section 6). The reconciler uses a key only while both the request claim and the `[submitter, key]` idempotency claim exist, and only when the submitter matches the admission's audit record. Otherwise the outcome stays `unknown` (`admission_unbound`) and the engine is not asked.
- **Read.** An injected `read_engine_state(tenant, submitter, key)` returns an `EngineReadback` that echoes the tenant, submitter and key it read, with one of three states:
  - `applied`: the effect carries the bound `request_id` and `payload_hash`. Both must equal the admission's (constant-time compare), or the result is `readback_mismatch`.
  - `not_applied`: no effect exists and the engine guarantees none can commit later for that key (a fence). This carries no request or hash.
  - `pending`: anything else, including an effect that may still be in flight.
- **Decision.** An exact `applied` gives `applied`. An exact `not_applied` gives `failed`, except:
  - when the outcome is missing or recorded `unknown` and the admission is younger than `handler_deadline` (`0 < handler_deadline < stuck_after`): then the outcome stays `unknown` with reason `handler_in_flight` so an in-flight handler or commit is never marked `failed` before it finishes;
  - when any `outcome_conflict` is open for the tenant: then `not_applied` stays `unknown` with reason `conflict_hold`. A conflict is never closed in this module (section 4), so for that tenant this lasts until a conflict can be closed (Q-558 (d)).
  Everything else stays `unknown` with a reason: `readback_pending`, `readback_mismatch` (wrong echo, other tenant, other request or hash, or effect fields on `not_applied`), `readback_invalid` (wrong type or state) or `reader_error` (any exception). A reader error never resolves anything.

UNVERIFIED engine facts that a live reader must prove before use:
- that a committed business effect is findable by `(tenant, submitter, idempotency key)`;
- that it stores the admission's `request_id` and `payload_hash`;
- that a `not_applied` answer is fenced, so a late in-flight commit for that key is refused. Without a fence the reader must answer `pending`, and the outcome escalates (section 4).

## 4. Stuck outcomes and the human floor
An outcome is **stuck** when it is still `unknown` and its admission is at least `stuck_after` old, or when it is an `outcome_conflict`. `stuck_after` and `handler_deadline` are constructor arguments with no defaults (`0 < handler_deadline < stuck_after`). The thresholds are founder decisions ([Q-558](../open-questions.md)).

When an outcome is stuck:
- The journal records `stuck = 1` in a separate column (`CHECK (stuck IN (0, 1) AND (stuck = 0 OR state = 'unknown'))`, covered by the entry's HMAC) while keeping the specific `reason` (`readback_pending`, `readback_mismatch`, `readback_invalid`, `reader_error`, `admission_unbound`, `handler_in_flight`, `outcome_conflict`, `conflict_hold`). The transition to `stuck = 1` is journaled once for a given reason; later runs return `stuck: true` with the current reason without appending. If the reason changes again after the threshold, one more `stuck = 1` row is appended per change, so a request can have several `stuck = 1` rows. OPR-007 must escalate on the first `stuck = 1` row per request, not on every row.
- A run returns results only for the requests it was asked about, but it journals every new conflict for the tenant, including one for a request outside a subset `request_ids`. The journal is the source of record: OPR-007 reads escalations (`stuck = 1` rows, including `outcome_conflict`) from the journal, not only from the return value of `reconcile()`.
- The request keeps every replay claim. Resubmitting the same request or key is refused as `replay` (tested).
- The result is handed to a human with the floor role for that action (ADR-0027, SEC-019). In G2 that means an item in the approval inbox (OPR-007). Until OPR-007 exists, the caller must surface the item; nothing auto-closes it.
- The human cannot mark it `applied` or `failed` in this module. They repair or inspect the engine side so that a later exact read-back decides it. Whether an audited human attestation may close an outcome that no read-back can ever decide is open ([Q-558](../open-questions.md)).

## 5. Reconciliation journal (append-only)
Table `action_outcome_reconciliation`, in the same server-owned database as the ERP-023 journal. Columns: `sequence` (`INTEGER PRIMARY KEY CHECK (sequence > 0)`), `tenant_id`, `request_id`, `state`, `reason`, `stuck`, `timestamp` and `mac`. `__init__` checks the column list and `CHECK (sequence > 0)` constraint and refuses any other schema layout. No payload, no session and no idempotency key are stored.

- **What is journaled.** All transitions of a run commit together in one `BEGIN IMMEDIATE` transaction; any refusal or error rolls back, restores the in-memory chain head, and writes nothing. The journal records the first observation of each admitted request, every change of `reason` while `unknown`, every move to a final state, the first `stuck = 1` escalation, and one sticky `outcome_conflict` escalation per conflicted request. A repeat run under the same conditions appends nothing. An instance lock serializes threads sharing one `ActionOutcomeReconciler`, while separate instances serialize on `BEGIN IMMEDIATE`, re-verify under the lock, and append at most one final entry.
- **Append-only.** Triggers refuse `UPDATE`, `DELETE` and `INSERT OR REPLACE`.
- **Tamper evidence.** Each entry carries an HMAC-SHA256 over its fields (including `stuck`), its sequence and the previous entry's MAC. The chain covers all tenants, so moving a row to another tenant breaks it. Every run verifies all rows in `ORDER BY sequence` from 1 (`sequence == prev + 1`) before any read-back and again inside `BEGIN IMMEDIATE`. A gap, duplicate, `sequence <= 0`, MAC mismatch, shrinkage, or `IntegrityError` stops the run with `journal_tampered` and writes nothing. The key (at least 32 bytes) is injected and never stored in the database.
- **Limits, stated plainly:**
  - Deleting the newest entries, or wiping the journal after dropping the triggers, is not detectable without an external head anchor (section 7 item 6).
  - ERP-023 `action_policy_audit` rows carry no MAC today; protecting audit rows so an edited `payload_hash` cannot pair with a matching read-back is a live-handler gate item (section 7 item 6).
  - Key custody and rotation are not built ([Q-558](../open-questions.md), like Q-428 and Q-441).
  - Verification reads the whole table on every run.
- **Tenant isolation.** A reconciler is bound to one tenant. It acts only on that tenant's admissions and refuses another tenant's request ID (`unknown_request`). It asks the reader only for its own tenant. Readbacks naming another tenant never resolve anything.
- **Clock.** A missing, naive or failing clock, or a clock earlier than any admission timestamp or latest journal timestamp for the tenant, stops the run (`clock_unavailable`) before anything is written.

## 6. The store hook (the only change to ERP-023 code)
`action_policy_store.py` gains:
- the append-only table `action_policy_admission_keys`, with one row per admission and one key per request (primary key and unique index, update, delete and replace triggers);
- one `INSERT` in `record()`, after the claims are reserved, only when the decision is not `deny`;
- a read method, `admission_key()`.

Why it is needed: ERP-023 stores the idempotency claim as `[submitter, key]` with no link to the request. The audit record does not hold the key, and the payload hash cannot be inverted. Without the binding, a reconciler would have to take the key from its caller. That is untrusted input, and it could point the read-back at another request's effect. The insert shares the admission transaction, so a failure aborts the admission (fail closed, as for any journal failure). Every decision the enforcer makes is unchanged. `action_policy_enforcer.py` is not edited, and ERP-023's tests pass unchanged. Admissions committed before this hook have no binding and stay `unknown` until a human acts (none are deployed).

## 7. Gate for OPR-004 and OPR-007 live handlers
No live business-action handler is enabled for a tenant until all of these hold:
1. A real `read_engine_state` exists for each enabled action. It is tested on the pinned bench (ERP-001, ERP-024) for exact lookup by `(tenant, submitter, key)`, for storing `request_id` and `payload_hash`, and for a fenced `not_applied`.
2. The reconciler runs on a schedule shorter than `stuck_after`, for every tenant with admissions. Its refusals (`journal_tampered`, `clock_unavailable`) page the operator and block new admissions for that tenant. An `outcome_conflict` is not a run failure: it is a returned, journaled result (`unknown`, `stuck = 1`) that escalates through the journal like any stuck outcome (section 4), and it holds back new `failed` outcomes for the tenant (`conflict_hold`) until a conflict can be closed (Q-558 (d)).
3. Stuck outcomes arrive in the OPR-007 approval inbox for the floor role, and nothing auto-closes them.
4. Q-558 is answered: the threshold, the escalation recipient, journal key custody, and attestation yes or no.
5. Production storage follows ADR-0041: tenant database, not a shared SQLite file. The reconciliation journal moves with the ERP-023 journal (UNVERIFIED; it needs its own row).
6. An external head anchor stores the latest `(sequence, mac)` of `action_outcome_reconciliation` outside the table so tail truncation or a full-table wipe is detected, and ERP-023 `action_policy_audit` rows carry tamper-evident MAC protection so an edited audit row's `payload_hash` or `submitter` cannot pair with a matching engine read-back.

## 8. Tests (offline)
`test_erp_029_action_outcome_reconciliation.py` covers:
- applied, failed and unknown from the real ERP-023 enforcer, with a later read-back resolving `unknown` both to `applied` and to `failed` (and keeping both a missing outcome and a recorded `unknown` outcome `handler_in_flight` until `handler_deadline`, tested at the exact boundary);
- exact-match refusals: wrong tenant/submitter/key echo, other request, other hash, missing fields, effect fields on `not_applied`, invalid state;
- reader errors and wrong types failing closed, and reason changes before `stuck_after` being journaled;
- a repeated run, 8 concurrent reconcilers, a barrier-forced contradictory-readback race, a single instance shared across 8 threads, and a rolled-back commit (`OperationalError` mid-run) restoring the in-memory chain head;
- sticky, single-entry `outcome_conflict` journaling and escalation when a recorded final outcome contradicts a journaled final state (including when recorded during the read-back), with unrelated requests continuing to reconcile and escalate, and new `not_applied` read-backs staying `unknown` with reason `conflict_hold` while a conflict is open (a subset run journals but does not return a conflict outside it), plus an outcome recorded during the read-back winning under the lock;
- stuck escalation at the exact `stuck_after` boundary preserving each specific failure reason (`readback_pending`, `readback_mismatch`, `readback_invalid`, `reader_error`, `admission_unbound`, `outcome_conflict`) and journaling `stuck = 1` once, with claims kept;
- triggers, `CHECK (sequence > 0)`, out-of-range sequences (`<= 0`), older schema layout, edited, moved, deleted or forged rows (including `stuck` tampering, tail shrinkage on the same instance, and `IntegrityError` mapping to `journal_tampered`), a wrong key, a row whose MAC skips the previous entry's MAC, and a reason outside the allowlist with an otherwise valid MAC, all refused;
- a re-pointed admission binding or mismatched submitter never reaching the reader, and tenant-scoped binding lookup;
- cross-tenant requests, cross-tenant readbacks and separate tenants;
- invalid configuration and an untrusted or backwards clock (earlier than admission or latest journal entry);
- the store hook writing a binding for admissions only.
