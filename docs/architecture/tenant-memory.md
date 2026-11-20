# Per-tenant memory

Status: draft
Owner: eldon

Plan row OPR-014 (Tier 3: tenancy and agent authority). Code: `services/operate/memory/`. Rules come from [prompt-injection-defence](../security/prompt-injection-defence.md) section 6 (memory is L3), [ai-layer](ai-layer.md) (per-tenant memory), [data-retention](../security/data-retention.md) (erasure) and ADR-0048 (the agent proposes, never acts).

## Model
A memory is a short note (at most 500 characters) of kind `preference`, `terminology` or `fact`, scoped to one tenant and one user. There is no tenant-wide or wildcard scope. Recipients, bank details, rates, rules, permissions and instructions are not kinds. Rule-like text (always, never, approve, pay, transfer, send to, without asking, and Arabic equivalents) and instruction-like text are stored `unverified` with a `rule_like` or `instruction_like` flag, so a planted rule is never recalled until the owner confirms it.

## Rules
| Topic | Rule |
|---|---|
| Isolation | Every call carries `Scope(tenant_id, user_id)` (validated ids). Another tenant's or user's entry is indistinguishable from a missing one; the store re-checks the owner on read |
| Data, not instructions | Recall returns L3 `DataItem`s (`source` `memory:<kind>`, flag `memory_read`), never text for the instruction position. No entry field names a tool or role; the module imports nothing from the allow-list, so memory cannot grant authority or change an allow-list |
| Secrets | Text with a secret (password and `pw`/`pass` phrasing, API keys, bearer tokens, JWTs, private-key headers, long or space-split opaque strings, digits split by letters) is refused with `secret_detected`, not masked, because a masked remnant can leak. IDs (e-mail in several spellings, IBAN, phone, card and long digit runs with any separator, Arabic-Indic digits too) are replaced by `[redacted]`. Any fault in sanitising or redaction is `invalid_input` |
| Taint | `remember` is host-facing: the host fills `tainted`, `author` and source ids from the verified run. The model calls only `AgentMemoryTool.remember(kind, text)`; unknown taint state counts as tainted. Tainted writes, assistant notes derived from source content, and instruction-like text are stored `unverified`, never recalled, and promoted only by the owner's `confirm` with the exact text hash, and only when the verified session user is the entry's owner (`not_owner` otherwise). A user write of the same text as a pending entry replaces it as verified |
| Provenance | Source turn, source content ids, author (`user` or `assistant`), created time, confirmer and time |
| Expiry and caps | Default 90 days, maximum 365 (unverified: 7 days); expired rows are hard-deleted on every write and by `sweep(tenant_id)`, and never count. 200 verified entries per user, 20 unverified (oldest unverified evicted, verified never), 5000 per tenant; oversize is refused, not truncated; recall returns at most 10 items and 2000 characters |
| Owner control | `list_entries`, `confirm`, `delete`, `erase_user` (right to erasure), `erase_tenant` (offboarding). The host must expose these only on a verified human session, never as agent tools. Hard delete, no tombstone with text. Erasure does not read the clock, so a bad clock never blocks it; the result is `Erasure(count, audit_failed)`, so a failed audit after the data is gone is reported beside the success. There is no cross-user tenant-admin listing yet (Q-394); the host may only call `erase_tenant` for a verified admin or operator |
| Audit | `memory.written`, `memory.write_quarantined`, `memory.read`, `memory.listed`, `memory.confirmed`, `memory.deleted`, `memory.erased`, `memory.tenant_erased`: ids, kind, length and keyed hash only (the salt may be per tenant, so equal texts do not link across tenants). No audit port or a sink failure refuses the operation (a write is rolled back) |
| Fail closed | A bad scope, input, clock reading (NaN, infinite, negative, non-number, after year 2100, raising; there is no stored high-water mark, so one bad reading cannot lock the service), store fault or audit fault gives a closed refusal code (`errors.py`) and stores nothing |

## Not here
Persistent store, embeddings or semantic search, model-written summaries, the event types in the events contract (Q-390), the host wiring into the chat prompt (Q-391).

## Erasure reach
`erase_user` and `erase_tenant` remove the memory store only. Copies of recalled text in agent trace spans, model requests and chat transcripts need their own erasure by the host (Q-395).
