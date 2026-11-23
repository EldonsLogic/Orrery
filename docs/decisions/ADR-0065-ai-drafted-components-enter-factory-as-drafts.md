# ADR-0065: AI-drafted component code enters the factory only as an unreviewed sandbox draft

Status: Proposed
Owner: eldon
Approved by: pending (Tier 3: a different model and the partner review; RULES 42 because it touches AI-written code)

Plan ID: BPL-017.

## Context
BPL-017 lets the model draft component code and tests from a request (principle 9: a need no component covers becomes a candidate component built once for everyone). Model output is untrusted (RULES 25), the rigid zone is never AI-written (RULES 21), agents propose and humans decide ([ADR-0048](ADR-0048-agent-authority-propose-not-act.md)), and only a named reviewer lifts a component above `tested` ([ADR-0034](ADR-0034-reviewed-level-needs-a-named-reviewer.md)). The factory sandbox (BPL-015) is logical only; an OS-level sandbox (INF-014) does not exist yet. Model calls go through the model-call contract ([ADR-0054](ADR-0054-model-call-contract.md), PLT-026, Proposed).

## Decision
1. **One path in.** AI-drafted component code enters only through `services/blueprint/factory/drafting.py`, from a request validated against `factory/request.schema.json` (closed shape). The requester is the verified principal, never a request field.
2. **Request is data.** It reaches the model only as an `untrusted` block; the instructions are a platform block by reference (`factory.drafter.v1`). That separation is the control. The instruction-like-text filter (applied to the raw and the folded text), the per-client and the personal-data checks of BPL-016 refuse a request before any call, but the filter is a backstop that a determined author can pass.
3. **Rigid zone by deterministic code, before and after the call.** The structural controls: the requested need must be proven `plain` by the BPL-016 `policy.classify` (the request names only entity, screen, report or print format); the draft's `provides` must be exactly that need, with `capability` equal to the component id and, for an entity, `riskClass: plain` (a missing or different class, an extra artifact or capability is refused); parameters must pass `policy.field_verdict` and may not be money typed or `affectsLedgerOrTax`; declared fields in JSON files must pass `policy.field_verdict`, and script-like keys (`formula`, `script` and similar) are refused. A secondary deny list (English and Arabic words for ledger, tax, e-invoicing, payroll, audit, money, auth and tenancy, after folding, Arabic prefix removal and joining spaced letters) refuses on any hit in the request, the manifest, file names or file contents; a miss proves nothing. Every refusal says `route_to_human`; there is no human queue yet. The model's own classification is never used.
4. **Model call** only through the model-call port: tier `mid`, purpose `build`, `min_output_tokens` reserved; any port refusal (budget, kill switch, filter) fails closed with nothing written.
5. **Fixed fields set by code, not the model:** `id`, `kind: configurable`, `requires: []`, owner, licence, `origin: component_factory` with the request id, `dataHandling` (no personal data, nothing to models, `promotableToLibrary: false`), every test `blocking: true`, and `certification.level: draft` with no reviewer. `touchesLedgerOrTax: false` is stamped because item 3 refused anything else, not because it is proven. A component id in a reserved namespace (`core`, `country`, `compliance`, `platform`, `system`, `library`) or already in `components/` is refused. The manifest must pass registry admission.
6. **Sandbox only, no candidate code runs.** Paths are checked (BPL-015 path check, then normpath, NFC and casefold, no `.` segment, no twins, no file-versus-folder clash) before any write. Files go to a temp folder under a caller-given sandbox root outside the repo (never `components/` or the library) and are renamed into place only at the end; any failure removes the temp folder. The BPL-015 runner checks the draft statically; candidate tests are never run in this slice (expected finding `FAC-012`), because the BPL-015 sandbox is logical and INF-014 does not exist. Running them needs a later decision once INF-014 exists. A HIGH static finding or a runner level other than `draft` refuses the draft and removes it.
7. **No promotion here.** The draft record says `reviewed: false`, `promotable: false`; promotion is a separate human step by a named reviewer who is not the requester (ADR-0034), bound to the recorded content hashes. Every outcome, including an internal error (`FDR-010`), writes one audit record: request hash, request and component id, tenant, requester, owner, outcome, status and code, matched words, call id (also on a port refusal), tier, prompt version, meter event id, manifest and file hashes. The audit record is written before the draft is renamed into place, so a failing audit sink leaves no draft. A reply without a meter event id, or served at a tier other than `mid`, is refused. The model id is not in the reply by design (ADR-0054); the meter event id links to it. There is no role check on the requester yet (Q-600).

## Alternatives rejected
- Let the model classify the risk of its own draft: self-assessment by the drafter is no control (RULES 21, ADR-0034).
- Write drafts into `components/` behind a draft flag: one bad path check would put unreviewed code in the library.
- Run every draft's tests now on the logical sandbox: customer-influenced code would run as the host user with network access (BPL-015 README).

## Consequences
- Safe slice: a draft exists only in the sandbox and cannot reach a tenant. Word lists cause false refusals (fail closed); those go to a human.
- Not built yet: the promotion step and its reviewer check, the link from an approved BPL-016 record, a live gateway adapter, i18n labels for the codes (internal tool today), and running tests under INF-014.

## Notes
- The platform prompt `factory.drafter.v1` is not in the repo yet (UNVERIFIED); the tests use a one-line stand-in, so how well the model itself resists injection is unreviewed.
- The sandbox root is checked and then used later (local attacker only). Accepted names such as `.git/hooks/pre-commit` stay inert inside the draft folder; the promotion step must never copy draft files blindly.

## Supersedes
none
