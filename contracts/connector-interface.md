# Connector interface

Version: 0.1.0
Status: draft
Owner: eldon

A connector brings data from a customer's existing tool (or files) into a normalised source model that Discovery maps onto the Blueprint, and optionally writes data back out. All connectors implement the same lifecycle so the AI and the gap analysis do not care where data came from. Spec: [Discovery](../docs/specs/01-discovery.md).

## 1. Capability tiers
Prefer the lowest tier number that works.

| Tier | Mechanism | Example | Risk |
|---|---|---|---|
| 1 | Official API with read-only credentials/OAuth scopes | Accounting or POS system with an API | Lowest |
| 2 | File exports and uploads (Excel, CSV, PDF, photos) | Customer list in Excel | Low; untrusted file content |
| 3 | Document intake with Arabic OCR/extraction | Invoice photos, supplier PDFs | Medium; OCR errors, must show confidence |
| 4 | Email and WhatsApp forwarding into a tenant inbox | Owner forwards supplier invoices | Medium; untrusted text, spoofing |
| 5 | Owner-driven isolated read-only browser session | Legacy web ERP without API | Highest; late fallback only, never stores the owner's credentials |

Tier 5 is not built before it is needed and needs its own ADR and security review.

## 2. Lifecycle
Every connector exposes five operations. Inputs and outputs are JSON; schemas live beside each connector under `connectors/<id>/`.

| Step | Purpose | Notes |
|---|---|---|
| `describe()` | Static metadata | id, version, tier, supported source kinds, required scopes, data classes read/written, rate limits, locales, `writes: false` for read-only connectors |
| `authorize(session)` | Establish access | Tier 1: OAuth/token with read-only scopes, handled by the platform vault, never visible to the model. Tier 2-4: nothing or an inbox address. Tier 5: owner drives an isolated browser; platform sees the session, not the password |
| `extract(job)` | Pull raw data | Returns raw items with source ids, content hashes and fetched-at. Resumable, paginated, rate-limited |
| `normalise(raw)` | Convert to the source model (section 4) | Deterministic where possible; AI-assisted (OCR/extraction) outputs carry confidence and are labelled |
| `map(source_model, blueprint)` | Propose mapping to Blueprint entities/fields | Produces Blueprint `integrations[].mappings` with `mappingConfidence`; a human or the owner confirms low-confidence rows. Mapping is Discovery's job; connectors only supply hints |

Write-back (`push(change)`) is optional, only for tier 1, off by default, and always goes through an approval.

## 3. Security requirements (all connectors)
1. **Read-only by default.** Request the narrowest scopes. `describe().writes` must be true and approved to use any write scope.
2. **No credential storage by us beyond the vault.** API tokens live in the platform secrets vault, encrypted per tenant, never in the Blueprint, events, logs or prompts. Tier 5 never receives or stores the owner's password or session cookie beyond the live session.
3. **Untrusted-content labelling.** Everything returned by `extract` and `normalise` is wrapped as `trust: "untrusted"` with its source. It may be shown to the model only as quoted data, never as instructions. Strings that look like instructions are flagged but not executed ([ai-layer](../docs/architecture/ai-layer.md)).
4. **File safety.** Size limits, type allow-list, malware scan before parsing, parsers run sandboxed with time/memory limits, no macro execution, no external fetches from documents.
5. **Rate limits and budgets.** Per connector, per tenant, per job; respect the source's own limits; back off on 429.
6. **Tenant isolation.** A connector job runs with one tenant's context and writes only to that tenant's staging area.
7. **Staging first.** Extracted data lands in a per-tenant staging store. Nothing reaches the engine until the owner/team approves the mapping and the import passes validation.
8. **Audit.** Every job emits `meter.connector_run` and audit events: who authorised, scopes, counts, hashes. No raw customer data in events.
9. **No cross-tenant learning from raw data.** Only generalised mapping patterns (field name pairs, transform types) may be promoted, after anonymisation review.
10. **Licence.** A connector that wraps third-party code records the licence in its manifest; AGPL code needs an ADR.

## 4. Normalised source model (output of `normalise`)
A neutral, source-agnostic description of what exists in the customer's tool.

```json
{
  "source": {"connector": "file.excel_upload", "version": "0.1.0", "job_id": "job_1", "fetched_at": "2026-01-01T09:00:00Z", "tier": 2, "trust": "untrusted"},
  "locale_hints": ["ar", "en"],
  "entities": [
    {
      "source_name": "Sheet1",
      "guessed_kind": "customer",
      "guess_confidence": 0.9,
      "fields": [
        {"source_name": "col_a", "header_text": "اسم العميل", "guessed_type": "string", "sample_values_redacted": ["***"], "null_rate": 0.0, "distinct_count": 212, "guessed_target": "customer.customer_name", "guess_confidence": 0.97}
      ],
      "row_count": 212,
      "records_ref": "staging://job_1/Sheet1"
    }
  ],
  "relations": [{"from": "Sheet2.customer_id", "to": "Sheet1.id", "confidence": 0.8}],
  "documents": [{"doc_ref": "staging://job_1/inv-001.pdf", "kind": "supplier_invoice", "ocr_confidence": 0.84, "fields": {}}],
  "workflows_observed": [],
  "issues": [{"severity": "warn", "code": "duplicate_keys", "detail": "5 duplicate customer names"}],
  "stats": {"rows": 212, "bytes": 48213}
}
```
Records themselves stay in staging; the model sees schema, stats and redacted samples. Field names and types, not data, drive the gap analysis.

## 5. Registry and versioning
Connector ids are dotted (`file.excel_upload`, `inbox.email_forward`, `erp.<vendor>`). A connector has a semver, a manifest (describe output), tests with sample files (anonymised), and a security review for tiers 1, 3, 4 and 5. Connectors are listed in `connectors/README.md` as they are added.
