# services/discovery/owner_approval

Status: draft (DSC-009, Tier 3: approval authority). Python 3.9+. No model call, no network, no file write; time comes from the injected host clock.

The owner approval flow, draft to `owner_approved`. The owner (a verified human with the owner role of THAT tenant, fresh step-up) reads a plain summary of the current draft and records one of `approve`, `request_changes` or `reject` with a typed reason and an optional note. Design rules are in the `flow.py` docstring; the port contract and claim assumptions are in `ports.py`.

```python
svc = OwnerApproval(identity=..., blueprints=..., quotes=..., gaps=..., holds=..., gate=..., content_digest=..., clock=...,
                    integrity_keys={"k1": key_bytes}, key_id="k1", store=durable_store)   # see ledger.py for the store port
view = svc.review(claims, tenant_id=t, blueprint_id=bp)      # four sections + decisions + blockers, label keys only
svc.decide(claims, tenant_id=t, blueprint_id=bp, decision="approve", reason="agree", note="",
           seen_blueprint_digest=view["blueprintDigest"], seen_quote_digest=view["quoteDigest"],
           confirmations=["gaps", "quote", "summary"])
```

What the owner sees (`sections`): what will be built (`sections.py` `summary_section`), what it costs (from the quote draft, integer minor units re-derived by code), what is not covered (gap report), what the test month will check (fixed keys, Q-523). Labels: `labels.json` (en, ar; Arabic UNREVIEWED, ADR-0033); quote line labels come from `services/discovery/quote/labels.json`. Short plain sentences, no engine name.

Rules, each with a test in `services/discovery/tests/owner_approval/`:
- Only humans with the owner role of the tenant decide (the sources, Blueprint, quote and gap report, are tenant-scoped by the host adapter, Q-542); agents, services, staff, and anyone also holding `team_reviewer` or `build_runner` are refused. A principal must be the exact `Principal` type (no dicts, no subclasses).
- The decision is bound to the Blueprint content digest and the quote digest the owner saw. If either changed, or the quote is expired, mismatched with the Blueprint or gap report, or its totals do not add up: refused, nothing recorded.
- Sealed append-only log (`ledger.py`): whole-record HMAC with key id, chained, tenant and stream bound, sealed per-tenant manifest against truncation and deletion; no key, no log. Any damaged record is OA-009 and blocks every decision (fail closed, no quarantine-and-skip). Decisions and outcomes are both appended under the same fold rules (clock skew, one outcome per decision), so a racing `reconcile` or a clock step back is refused, never sealed into an unreadable log.
- No store, no service: the log lives behind the `store` port (one atomic write of record and manifest). Without one the constructor refuses (OA-010) unless `ephemeral=True`, which keeps an in-memory `MemoryStore` for tests and local runs only (a restart forgets every decision, rejections included). A store read error is OA-009.
- One decision per owner per version (at most 5 sealed tries, refused approvals included); a rejection of a Blueprint digest beats every approval of it; the draft is never auto-approved; a hold blocks approval.
- The machine requires this approval (ADR-0050 item 11): its owner gate calls `OwnerApproval.verify` (the `owner_approvals` port) with the content digest IT computed and the quote digest, and needs a sealed approval by the calling owner, a current quote and no block; every later gate re-checks it. Quote validity counts at approval time only: past draft the same quote (same digest, bound to the same content and gap report) stays current after it expires; at draft it must be valid. A confirmed approval is not credited once the machine is back at draft (spent by a rollback). The flow records what the owner saw, the machine re-derives the digest (a mismatch is BS-008, so it never reaches `owner_approved` on content the owner did not see). A refused or unconfirmed gate call is sealed as `refused`, does not count, and the owner may try again; `reconcile` settles a decision left without an outcome by a crash, crediting only the machine's own record for that owner.
- One step-up per decision: the machine's gate consumes it when called, otherwise the flow does (Q-541).
- Several owners (Q-540): any rejection blocks the digest; any request for changes blocks that version; one approval is otherwise enough. Reject and request changes work in every state before live (they roll the build back to draft), also after the quote expired, except for an owner who already decided on that version (one decision per owner per version, Q-524).
- The summary lists every item of every collection by id and labels, plus what roles (permissions, admin, chat actions), approval rules (what, steps, self-approval), integrations (connector, direction) and assistants (roles, tools) allow. Other item details (record fields, process steps), branding and language settings are not listed, and the notice says so. If any collection, list or gap row is cut (`moreItems > 0`), approval is blocked (`too_large`, OA-017); reject and request changes still work.
- Audit callback failures are swallowed on allow and on refuse: the sealed log is the record of truth, the callback is a copy.
- Notes and Blueprint/quote text are untrusted: NFC, control, bidi, zero-width and format characters removed, bounded (notes over 1000 characters are refused, never cut), flagged `untrustedText` for plain-text rendering.

Not done here (follow-up WEB-027, Q-526): the web screen. It should follow the DSC-007 viewer pattern: tenant realm, design tokens only, RTL, plain-text rendering of untrusted fields, port-based with fixtures. Open questions: Q-521, Q-523 to Q-526, Q-540 to Q-542 (Q-520 and Q-522 resolved).

Run: `python -m pytest services/discovery/tests/owner_approval -q`.
