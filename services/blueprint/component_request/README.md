# component_request (BPL-016)

Turns a gap analysis `component_request` (DSC-006) into a `ComponentRequest` record with an AI-drafted spec and test plan. A need no component covers becomes a candidate component built once for everyone: configuration over code, never per-client code. Agents propose, humans decide ([ADR-0048](../../../docs/decisions/ADR-0048-agent-authority-propose-not-act.md)). It builds no code (BPL-017 does, from an approved record). Standard library plus the registry and `exceptions.sanitize` of this folder.

```python
from component_request import Actor, ComponentRequests
reqs = ComponentRequests(drafting_port, library_registry, owner_github="...")
out = reqs.intake(gap_request, Actor("agent", "discovery"), now)      # created | refused | duplicate | in_library
reqs.draft(id, now, actor); reqs.submit_for_review(id, now, actor)
reqs.approve(id, Actor("human", "b", ("component_reviewer",), True), now)   # or reject(id, reviewer, now, reason)
```
`now` is the caller's clock (`YYYY-MM-DDTHH:MM:SSZ`, never earlier than the last event). `DraftingPort.draft(brief)` is the only model call.

## Rules
- Status: `requested -> drafted -> in_review -> approved | rejected`, plus `refused` (routed to a human-built path with a reason code and ar/en labels) and `drafting_failed` (three drafter failures park the need for a human; a human `reopen` puts it, or a quality-rejected one, back to `requested`). History is append-only. Approval is never automatic: only a verified human with a reviewer role who is not the requester, drafter or submitter (ids compared case-insensitively); the need and the stored draft are re-validated first. Stored records are re-validated on every read; the draft digest is HMAC-SHA256 when the host passes `integrity_key`, otherwise a plain sha256 that detects accidents only (anyone who can write the store can recompute it).
- **The risk class is derived, never taken from the model** (`policy.py`, using the reviewed Tool API tables in `services/operate/toolapi`). Default deny: an entity, workflow or report is allowed only when it is in the reviewed plain table, or has no restricted word and at least one benign scope word. Ledger, stock, identity and sensitive entities, and anything unclassified, are refused at intake (before the model) and again in the draft. The pipeline sets `riskClass: plain` on entity artifacts itself. The word scan (English and Arabic, after NFKC, tatweel, harakat, confusable and leetspeak folding) is only a backstop.
- AI drafts may provide only `entity`, `screen`, `report` and `print_format` artifacts; permissions only read, list, create, update, export for tenant role names (never platform roles); `requires` only on library manifests whose artifacts all derive as plain. Test paths must sit under `tests/` with no dot segments.
- Same `request_key` = same request, and the key must equal the gap analysis hash of `kind:ref` (a mismatch is refused). Evidence stays per tenant under an opaque tenant reference (`intake(..., tenant)`), pattern-restricted, never merged across tenants; a closed record is returned unchanged. A need a certified or regulated library manifest provides returns `in_library`.
- Generalisation is deterministic: at least `min_tenants` distinct tenants (default 2) or a human `attest_generalisable`. The model's rationale is display text only.
- The model sees only a brief with the kind and a plain id (`[a-z][a-z0-9_.]*`). A ref that is not a plain id (Arabic, prose, personal data, injection) is refused as unclassified and never stored or sent.
- A draft is `{manifest, spec, generalisation}`, closed shapes, run on a copy and never repaired. The manifest must pass registry admission; owner, licence, origin and certification (`draft`) are set by the pipeline. Look-alike letters (Cyrillic, Greek) are hostile. Tests need a blocking unit test and an rtl or arabic_text test and must cover every capability.
- Clock: `now` may not precede the record's last event or run more than a day past the latest time seen.

Reason codes `CRQ-001..017` in `codes.py`, labels in `labels.json` (ar and en, same keys; tested). Open: Q-420 to Q-429.

Run: `uv run --no-project --with pytest --with jsonschema --with "pydantic>=2" --with hijridate==2.6.0 python -W ignore -m pytest services/blueprint/tests/component_request -q -p no:cacheprovider`
