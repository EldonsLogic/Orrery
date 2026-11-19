# Change by chat

Plan row OPR-009. Code: `services/operate/change/`. A router `change` decision becomes a Blueprint change proposal, shown as a preview, and is applied only after a confirmation bound to that exact proposal, through the existing Blueprint path (never the engine). Basis: [intent-router](intent-router.md), [change-engine](change-engine.md), [ADR-0027](../decisions/ADR-0027-human-floor-action-policy-and-agent-authority.md), Q-280 to Q-282 and Q-290 in [open-questions](../open-questions.md).

## Pipeline
1. Caller check: tenant, subject and a role in the service's allowed roles; otherwise `change_no_permission`.
2. Draft: an injected drafter sees the user's turn, the locale and ids only (no labels, no data items) and returns typed edits (`set`, `add`, `remove`). `edits.decode_draft` is a closed-shape decode; `edits.check_allowed` is an early exit only (allowed roots, forbidden keys, no whole-section `set`).
3. Apply to a copy, validate the result with the Blueprint validator, compute the diff with `bpdiff`.
4. Decide on the diff (`policy.check_diff`), for every changed path, including a whole parent replaced at once:
   - owning entity of each op (the entity, `workflow.entity`, `report.entity`, the entity named by a label-override key, a link target), in both the current and the target Blueprint: ledger class or a ledger or tax name gives `change_ledger_tax`; stock class gives R3, refused;
   - a tax token in any id on the path, or a money field (other than its labels), gives `change_ledger_tax`;
   - any `remove` or `reorder` gives `change_needs_review` (removals are R3);
   - default deny: the op's schema path must be on the allow-list (labels and plural labels of entities, fields, select options, workflows, states, transition action labels, reports and locations; an added optional plain field or select option; a plain field's `maxLength`; location city; non-assistant label overrides; glossary translations; branding display name and colours). Anything else is `change_forbidden_path`, including transitions (`from`, `to`, `kind`, guards, approval, roles, notify), `locksEditing`, `entities/*/workflow`, report schedules and recipients, defaults, `readOnly`, `computed`, `type`, `required`, `unique`, numbering;
   - forbidden keys anywhere in the path or the before and after subtrees; only labels may change on a computed or read-only field.
5. Risk: the highest of the mode floor, the diff impacts, the entity class floor and the router hint (never lowered). Above R2 is refused (`change_needs_review`).
6. Preview: built from the diff only; values rendered as JSON text, no risk code in the customer line. The digest binds tenant, user, session, base hash, target hash, diff hash, risk and expiry.

## Confirm
- The decision must be mode `change` and carry the proposal's action id and digest; the service re-checks user, session, tenant, expiry (exclusive), digest, live base hash and validity, and re-derives the diff and risk from the stored edits (a lower stored risk is tampering).
- `store.consume` is compare-and-delete on the digest: it succeeds only if that proposal is still the active one of its session and unused. A proposal superseded while its confirm was in flight is refused.
- `BlueprintPort.submit_change(tenant, diff, digest, idempotency_key=digest, actor=..., risk=...)`: the apply runs under the caller's identity (tenant, subject, roles, session), never a service identity, and the port re-classifies the risk itself.
- Outcomes: success is `applied`. Only a typed `ApplyRefused` (refused before any write) gives "Nothing was changed" (`change_apply_failed`). Any other failure asks `change_status(tenant, idempotency_key)`; `applied` is reported as applied, `not_applied` as `change_apply_failed`, anything else as `change_outcome_unknown` ("check the change history"), never as "nothing changed".
- A non-integer, non-float, NaN, infinite or `bool` clock gives `change_unavailable` in both propose and confirm; a non-positive or non-finite TTL refuses at construction.
- Audit: `change.proposed`, `change.applied`, `change.apply_failed`, `change.outcome_unknown`, and `change.refused` for every confirm refusal (code, session, digest prefix). Hashes and codes only; never the turn, values or model output.

## Not covered here
The real port binding, the drafter model call and a shared proposal store (Q-281); replay protection across workers relies on the port's idempotency key. Arabic texts are UNREVIEWED (ADR-0033).
