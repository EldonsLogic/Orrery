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
- Status: `requested -> drafted -> in_review -> approved | rejected`, plus `refused` (routed to a human-built path with a reason code and ar/en labels). History is append-only. Approval is never automatic: only a verified human with a reviewer role, who is not the requester or submitter; the stored draft is re-validated first.
- Same `request_key` = same request: new evidence and requirement ids are appended. A need an admitted library manifest already provides returns `in_library` and creates nothing.
- Refused at intake: compliance or `rigid` needs, and words for ledger, tax, VAT, e-invoicing, payroll maths or audit (English and Arabic); needs written for one client. Refused after drafting: the same scopes, ledger, tax, stock or permission risk classes, `scheduled_job` and `tool` artifacts, permission actions beyond read, list, create, update, export (Q-421).
- The model sees only a brief with the kind and an id-safe slug of the need (Arabic-only text becomes `need_<key>`); requirement text is untrusted, cleaned, scanned for injection and personal data, never passed on as prose.
- A draft is `{manifest, spec, generalisation}`, closed shapes, run on a copy and never repaired. The manifest must pass registry admission; owner, licence, origin (`component_factory` and the request id) and certification (`draft`) are set by the pipeline, never the model. Tests must include a blocking unit test and an rtl or arabic_text test and cover every capability; i18n locales ar and en; a generalisation rationale and `tenant_specific: false` are required.
- A failed draft (malformed, hostile, port error) stays `requested` with a coded history entry; three failures, or any forbidden scope, refuse the request.

Reason codes `CRQ-001..017` in `codes.py`, labels in `labels.json` (ar and en, same keys; tested). Open: Q-420 to Q-424.

Run: `uv run --no-project --with pytest --with jsonschema --with "pydantic>=2" --with hijridate==2.6.0 python -W ignore -m pytest services/blueprint/tests/component_request -q -p no:cacheprovider`
