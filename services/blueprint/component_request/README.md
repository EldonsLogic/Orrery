# component_request (BPL-016)

Turns a gap analysis `component_request` (DSC-006) into a `ComponentRequest` record with an AI-drafted spec and test plan. A need no component covers becomes a candidate component built once for everyone: configuration over code, never per-client code. Agents propose, humans decide ([ADR-0048](../../../docs/decisions/ADR-0048-agent-authority-propose-not-act.md)). It builds no code (BPL-017 does, from an approved record). Standard library plus the registry and `exceptions.sanitize` of this folder.

```python
from component_request import Actor, ComponentRequests
reqs = ComponentRequests(drafting_port, library_registry, owner_github="...", integrity_key=host_key)
out = reqs.intake(gap_request, principal, now)      # created | refused | duplicate | in_library
reqs.draft(id, now, actor); reqs.submit_for_review(id, now, actor)
reqs.approve(id, Actor("human", "b", ("component_reviewer",), True), now)   # or reject(id, reviewer, now, reason)
```
`now` is the caller's clock (`YYYY-MM-DDTHH:MM:SSZ`, never earlier than the last event). `DraftingPort.draft(brief)` is the only model call.

## Rules
- Status: `requested -> drafted -> in_review -> approved | rejected`, plus `refused` (routed to a human-built path, reason code, ar/en labels), `needs_human_classification` (not provably plain: parked) and `drafting_failed` (three drafter failures park it; a human `reopen` restores it, or a quality-rejected one, and clears every attestation). History is append-only. Approval is never automatic: only a verified human with a reviewer role who is not the requester, drafter or submitter (ids case-insensitive); the need and stored draft are re-judged first.
- **Plain is proven, never inferred from a name** (`policy.py`, reviewed Tool API tables first). Verdicts: `refuse` (reviewed ledger or stock entity, identity domain, sensitive data such as iban, national id, password, passport, salary, card, secret in English or Arabic, or a restricted word: the normalised word lists with plural stems, split letters, confusables and Arabic broken plurals are a secondary deny only), `plain` (every word of the name is benign vocabulary and every field is allow-listed: text, long_text, date, datetime, select with a closed options list, checkbox, link to a plain entity, attachment), `unproven` (anything else, including any money, decimal, percent, integer or boolean field). Unproven is parked, not refused: a verified human `attest_risk_class` says `plain` (the request goes on; the draft attestation is bound to the draft digest) or another class (routed to the human-built path). A human can never attest `plain` for a draft with a money-typed field. The pipeline never takes a risk class from the model.
- AI drafts may provide only `entity`, `screen`, `report` and `print_format` artifacts; permissions only read, list, create, update, export for tenant role names; `requires` only on library manifests whose artifacts all prove plain; test paths under `tests/` with no dot segments; the draft must provide the need it was drafted for. Workflow and component-binding needs are not draftable.
- Same `request_key` = same request, and the key must be the gap analysis hash of `kind:ref`. A closed record is returned unchanged by a duplicate.
- **Tenant comes from the verified Principal** (`intake(gap, principal, now)`; subject, session_id and tenant_id from the identity service, never an argument the agent chooses). A session that presents a second tenant is refused. A tenant counts toward generalisation only with at least one valid evidence item, is stored as an opaque hash, and its evidence is never merged. The host is trusted to vouch for the Principal (Q-427). Generalisation: at least `min_tenants` such tenants (default 2) or a human `attest_generalisable`; the model's rationale is display text only.
- **Whole-record seal**: an HMAC-SHA256 over the entire record (status, history, tenants, attestations, decision, draft) under the host `integrity_key`, checked on every read. With no key nothing is trusted as approved: `approve` and the read of an approved record fail closed (CRQ-022). `list()` skips a record that fails and `invalid()` reports it.
- The model sees only `{kind, ref}` with a plain id `[a-z][a-z0-9_.]*` that passed the gate; anything else is refused and never stored or sent.
- A draft is `{manifest, spec, generalisation}`, closed shapes, never repaired; the manifest passes registry admission; owner, licence, origin and certification are set by the pipeline; look-alike letters are hostile; tests need a blocking unit test and an rtl or arabic_text test covering every capability.
- Clock: `now` may not precede the record's last event or run more than an hour past the latest recorded event; an optional `host_now` bounds it by the host clock. The clock moves only on a recorded event.

Reason codes `CRQ-001..017` in `codes.py`, labels in `labels.json` (ar and en, same keys; tested). Open: Q-420 to Q-432.

Run: `uv run --no-project --with pytest --with jsonschema --with "pydantic>=2" --with hijridate==2.6.0 python -W ignore -m pytest services/blueprint/tests/component_request -q -p no:cacheprovider`
