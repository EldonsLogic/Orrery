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

Once `applied` or `failed` is journaled for a request it never changes. A unique index allows one final entry per tenant and request. If the enforcer's recorded outcome later contradicts a journaled final state, the run stops with `outcome_conflict`.

## 3. Resolving unknown: exact read-back by idempotency key
The reconciler never calls a handler, never retries, and never releases a claim. It reads.

- **Binding.** At admission the store now also writes `(tenant, request, submitter, idempotency key)` to `action_policy_admission_keys`, in the same transaction as the claims (section 6). The reconciler uses a key only while both the request claim and the `[submitter, key]` idempotency claim exist, and only when the submitter matches the admission's audit record. Otherwise the outcome stays `unknown` (`admission_unbound`) and the engine is not asked.
- **Read.** An injected `read_engine_state(tenant, submitter, key)` returns an `EngineReadback` that echoes the tenant, submitter and key it read, with one of three states:
  - `applied`: the effect carries the bound `request_id` and `payload_hash`. Both must equal the admission's (constant-time compare), or the result is `readback_mismatch`.
  - `not_applied`: no effect exists and the engine guarantees none can commit later for that key (a fence). This carries no request or hash.
  - `pending`: anything else, including an effect that may still be in flight.
- **Decision.** An exact `applied` gives `applied`. An exact `not_applied` gives `failed`. Everything else stays `unknown` with a reason: `readback_pending`, `readback_mismatch` (wrong echo, other tenant, other request or hash), `readback_invalid` (wrong type or state) or `reader_error` (any exception). A reader error never resolves anything.

UNVERIFIED engine facts that a live reader must prove before use:
- that a committed business effect is findable by `(tenant, submitter, idempotency key)`;
- that it stores the admission's `request_id` and `payload_hash`;
- that a `not_applied` answer is fenced, so a late in-flight commit for that key is refused. Without a fence the reader must answer `pending`, and the outcome escalates (section 4).

## 4. Stuck outcomes and the human floor
An outcome is **stuck** when it is still `unknown` and its admission is at least `stuck_after` old. `stuck_after` is a constructor argument, must be positive, and has no default. The value is a founder decision ([Q-558](../open-questions.md)). It must exceed the handler deadline.

When an outcome is stuck:
- One `unknown` entry with reason `stuck` is journaled, once. Later runs return `stuck: true` without appending.
- The request keeps every replay claim. Resubmitting the same request or key is refused as `replay` (tested).
- The result is handed to a human with the floor role for that action (ADR-0027, SEC-019). In G2 that means an item in the approval inbox (OPR-007). Until OPR-007 exists, the caller must surface the item; nothing auto-closes it.
- The human cannot mark it `applied` or `failed` in this module. They repair or inspect the engine side so that a later exact read-back decides it. Whether an audited human attestation may close an outcome that no read-back can ever decide is open ([Q-558](../open-questions.md)).

## 5. Reconciliation journal (append-only)
Table `action_outcome_reconciliation`, in the same server-owned database as the ERP-023 journal. Columns: `sequence`, `tenant_id`, `request_id`, `state`, `reason`, `timestamp` and `mac`. No payload, no session and no idempotency key are stored.

- **What is journaled.** The first observation of each admitted request, every move to a final state, and the first `stuck` escalation. A repeat run under the same conditions appends nothing, so the operation is idempotent. Concurrent runs serialize on `BEGIN IMMEDIATE`, re-check under the lock, and append at most one final entry (tested with 8 threads).
- **Append-only.** Triggers refuse `UPDATE`, `DELETE` and `INSERT OR REPLACE`.
- **Tamper evidence.** Each entry carries an HMAC-SHA256 over its fields, its sequence and the previous entry's MAC. The chain covers all tenants, so moving a row to another tenant breaks it. Sequences must be contiguous. Every run verifies the whole chain before acting, and re-verifies new rows inside each append transaction. A mismatch stops the run with `journal_tampered` and writes nothing. The key (at least 32 bytes) is injected and never stored in the database.
- **Limits, stated plainly:**
  - Deleting the newest entries, after dropping the triggers, is not detectable without an external anchor. The effect is bounded: the journal is evidence, not the authority. A deleted final entry is derived again from the recorded outcome or an exact read-back. It is never guessed.
  - Key custody and rotation are not built ([Q-558](../open-questions.md), like Q-428 and Q-441).
  - Verification reads the whole table on every run.
- **Tenant isolation.** A reconciler is bound to one tenant. It acts only on that tenant's admissions and refuses another tenant's request ID (`unknown_request`). It asks the reader only for its own tenant. Readbacks naming another tenant never resolve anything.
- **Clock.** A missing, naive or failing clock stops the run (`clock_unavailable`) before anything is written.

## 6. The store hook (the only change to ERP-023 code)
`action_policy_store.py` gains:
- the append-only table `action_policy_admission_keys`, with one row per admission and one key per request (primary key and unique index, update, delete and replace triggers);
- one `INSERT` in `record()`, after the claims are reserved, only when the decision is not `deny`;
- a read method, `admission_key()`.

Why it is needed: ERP-023 stores the idempotency claim as `[submitter, key]` with no link to the request. The audit record does not hold the key, and the payload hash cannot be inverted. Without the binding, a reconciler would have to take the key from its caller. That is untrusted input, and it could point the read-back at another request's effect. The insert shares the admission transaction, so a failure aborts the admission (fail closed, as for any journal failure). Every decision the enforcer makes is unchanged. `action_policy_enforcer.py` is not edited, and ERP-023's tests pass unchanged. Admissions committed before this hook have no binding and stay `unknown` until a human acts (none are deployed).

## 7. Gate for OPR-004 and OPR-007 live handlers
No live business-action handler is enabled for a tenant until all of these hold:
1. A real `read_engine_state` exists for each enabled action. It is tested on the pinned bench (ERP-001, ERP-024) for exact lookup by `(tenant, submitter, key)`, for storing `request_id` and `payload_hash`, and for a fenced `not_applied`.
2. The reconciler runs on a schedule shorter than `stuck_after`, for every tenant with admissions. Its failures (`journal_tampered`, `outcome_conflict`, `clock_unavailable`) page the operator and block new admissions for that tenant.
3. Stuck outcomes arrive in the OPR-007 approval inbox for the floor role, and nothing auto-closes them.
4. Q-558 is answered: the threshold, the escalation recipient, journal key custody, and attestation yes or no.
5. Production storage follows ADR-0041: tenant database, not a shared SQLite file. The reconciliation journal moves with the ERP-023 journal (UNVERIFIED; it needs its own row).

## 8. Tests (offline)
`test_erp_029_action_outcome_reconciliation.py` covers:
- applied, failed and unknown from the real ERP-023 enforcer, with a later read-back resolving `unknown` both to `applied` and to `failed`;
- exact-match refusals: other request, other hash, missing fields, invalid state;
- reader errors and wrong types failing closed;
- a repeated run and 8 concurrent runs staying idempotent;
- stuck escalation journaled once, with claims kept;
- triggers, edited, moved, deleted or forged rows, and a wrong key, all refused;
- a re-pointed admission binding never reaching the reader;
- cross-tenant requests, cross-tenant readbacks and separate tenants;
- invalid configuration and an untrusted clock;
- the store hook writing a binding for admissions only.
