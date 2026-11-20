# services/discovery/accountant_view

Status: draft (DSC-016). Python 3.9+, `jsonschema`. No model call, no network, no clock read, no file write.

Read-only accountant review of a Blueprint (0.4.0), plus the accountant's comments and per-section sign-off as **data**. Design: `docs/architecture/accountant-view.md`.

```python
from accountant_view import build_review, record_decision, add_comment, Signer
view = build_review(blueprint, records, tenant_id=t)            # sections, comments, sign-off state, i18n keys
records = record_decision(blueprint, records, tenant_id=t, actor=signer, section="tax_vat",
                          decision="approved", decided_at=ts, now=clock_now, note="")
records = add_comment(blueprint, records, tenant_id=t, actor=signer, section="numbering", text="...",
                      created_at=ts, now=clock_now)
```

Sections: `chart_of_accounts`, `tax_vat`, `e_invoicing`, `approval_thresholds`, `posting_rules`, `numbering`. Blueprint 0.4.0 carries no chart of accounts or posting rules, so those two are `not_in_blueprint` (country pack and certified components supply them; Q-370): shown, commentable, not signable.

Rules: signer is a verified human of the same tenant holding `accountant` (built by the gateway from identity claims, never the request); a decision is `approved` or `changes_requested` (note required), final per (Blueprint digest, section), append-only; any Blueprint change makes earlier decisions stale (not counted); `overall.evidenceOnly` is always true, nothing here approves or promotes anything (DSC-009, BPL-020). Stored records are validated and fail closed. Money is integer minor units (`money.py`, no floats); VAT rate is basis points. Blueprint and accountant text is untrusted data (`untrustedText`), control and bidi characters removed. Labels: `labels.json` (en, ar; Arabic UNREVIEWED, ADR-0033).

Tests: `tests/`. Run: `python -m pytest services/discovery -q`.
