# ADR-0065: AI-drafted component code enters the factory only as an unreviewed sandbox draft

Status: Proposed
Owner: eldon
Approved by: pending (Tier 3: a different model and the partner review; RULES 42 because it touches AI-written code)

Plan ID: BPL-017.

## Context
BPL-017 lets the model draft component code and tests from a request (principle 9: a need no component covers becomes a candidate component built once for everyone). Model output is untrusted (RULES 25), the rigid zone is never AI-written (RULES 21), agents propose and humans decide ([ADR-0048](ADR-0048-agent-authority-propose-not-act.md)), and only a named reviewer lifts a component above `tested` ([ADR-0034](ADR-0034-reviewed-level-needs-a-named-reviewer.md)). The factory sandbox (BPL-015) is logical only; an OS-level sandbox (INF-014) does not exist yet. Model calls go through the model-call contract ([ADR-0054](ADR-0054-model-call-contract.md), PLT-026, Proposed).

## Decision
1. **One path in.** AI-drafted component code enters only through `services/blueprint/factory/drafting.py`, from a request validated against `factory/request.schema.json` (closed shape). The requester is the verified principal, never a request field.
2. **Request is data.** It reaches the model only as an `untrusted` block; the instructions are a platform block by reference (`factory.drafter.v1`). Instruction-like text in the request is refused before any call.
3. **Rigid zone by deterministic check, before and after the call.** A request or draft that names ledger, tax, e-invoicing, payroll, audit, auth or tenancy (English and Arabic word lists, the BPL-016 `policy` identifier and class checks), declares an entity `riskClass` other than `plain`, or provides an artifact other than entity, screen, report or print format, is refused and routed to a human. A need not proven plain is also routed to a human. The model's judgement is never used for this.
4. **Model call** only through the model-call port: tier `mid`, purpose `build`, `min_output_tokens` reserved; any port refusal (budget, kill switch, filter) fails closed with nothing written.
5. **Fixed fields set by code, not the model:** `id`, `kind: configurable`, `requires: []`, owner, licence, `origin: component_factory` with the request id, and `certification.level: draft` with no reviewer. The manifest must pass registry admission.
6. **Sandbox only.** Files are written only under a caller-given sandbox root outside the repo (never `components/` or the library), after every path passed the BPL-015 path check. The BPL-015 runner then checks it. Candidate tests run only when the host sets `run_candidate_tests`; until INF-014 exists that stays off for anything a customer influenced, so such drafts stop at `draft` (`FAC-012`).
7. **No promotion here.** The draft record says `reviewed: false`, `promotable: false`; promotion is a separate human step by a named reviewer who is not the requester (ADR-0034). Each outcome writes one audit record (request hash, requester, outcome and code, tier, prompt version, call id, meter event id). The model id is not in the reply by design (ADR-0054); the meter event id links to it.

## Alternatives rejected
- Let the model classify the risk of its own draft: self-assessment by the drafter is no control (RULES 21, ADR-0034).
- Write drafts into `components/` behind a draft flag: one bad path check would put unreviewed code in the library.
- Run every draft's tests now on the logical sandbox: customer-influenced code would run as the host user with network access (BPL-015 README).

## Consequences
- Safe slice: a draft exists only in the sandbox and cannot reach a tenant. Word lists cause false refusals (fail closed); those go to a human.
- Not built yet: the promotion step and its reviewer check, the link from an approved BPL-016 record, a live gateway adapter, i18n labels for the codes (internal tool today), and running tests under INF-014.

## Supersedes
none
