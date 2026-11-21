# services/discovery/owner_approval

Status: draft (DSC-009, Tier 3: approval authority). Python 3.9+. No model call, no network, no file write; time comes from the injected host clock.

The owner approval flow, draft to `owner_approved`. The owner (a verified human with the owner role of THAT tenant, fresh step-up) reads a plain summary of the current draft and records one of `approve`, `request_changes` or `reject` with a typed reason and an optional note. Design rules are in the `flow.py` docstring; the port contract and claim assumptions are in `ports.py`.

```python
svc = OwnerApproval(identity=..., blueprints=..., quotes=..., gaps=..., holds=..., gate=..., content_digest=..., clock=...,
                    integrity_keys={"k1": key_bytes}, key_id="k1")
view = svc.review(claims, tenant_id=t, blueprint_id=bp)      # four sections + decisions + blockers, label keys only
svc.decide(claims, tenant_id=t, blueprint_id=bp, decision="approve", reason="agree", note="",
           seen_blueprint_digest=view["blueprintDigest"], seen_quote_digest=view["quoteDigest"],
           confirmations=["gaps", "quote", "summary"])
```

What the owner sees (`sections`): what will be built (`sections.py` `summary_section`), what it costs (from the quote draft, integer minor units re-derived by code), what is not covered (gap report), what the test month will check (fixed keys, Q-523). Labels: `labels.json` (en, ar; Arabic UNREVIEWED, ADR-0033); quote line labels come from `services/discovery/quote/labels.json`. Short plain sentences, no engine name.

Rules, each with a test in `services/discovery/tests/owner_approval/`:
- Only humans with the owner role of the tenant decide; agents, services, staff, and anyone also holding `team_reviewer` or `build_runner` are refused. A principal must be the exact `Principal` type (no dicts, no subclasses).
- The decision is bound to the Blueprint content digest and the quote digest the owner saw. If either changed, or the quote is expired, mismatched with the Blueprint or gap report, or its totals do not add up: refused, nothing recorded.
- Sealed append-only log (`ledger.py`): whole-record HMAC with key id, chained, tenant and stream bound, sealed per-tenant manifest against truncation and deletion; no key, no log. Any damaged record is OA-009 and blocks every decision (fail closed, no quarantine-and-skip).
- One decision per owner per version; a rejection of a Blueprint digest beats every approval of it; the draft is never auto-approved; a hold blocks approval.
- Approval is evidence, then the gate: the flow asks the build state machine's owner gate through the `gate` port; the machine re-checks everything. A refusal or an unconfirmed answer is sealed as `refused` and the approval does not count. `reconcile` settles a decision left without an outcome by a crash.
- Notes and Blueprint/quote text are untrusted: NFC, control, bidi, zero-width and format characters removed, bounded (notes over 1000 characters are refused, never cut), flagged `untrustedText` for plain-text rendering.

Not done here (follow-up WEB-027, Q-526): the web screen. It should follow the DSC-007 viewer pattern: tenant realm, design tokens only, RTL, plain-text rendering of untrusted fields, port-based with fixtures. Open questions: Q-520 to Q-526.

Run: `python -m pytest services/discovery/tests/owner_approval -q`.
