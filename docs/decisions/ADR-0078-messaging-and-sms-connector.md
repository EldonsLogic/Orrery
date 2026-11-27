# ADR-0078: Messaging and SMS connector: one conversation model for Meta's channels plus SMS, untrusted inbound, drafts by default

Status: Proposed
Owner: eldon
Approved by: pending (Eldon proposer; partner review on this PR). Touches contracts, tenancy and PDPL: Tier 3, needs a security review by a different model.

## Context
[ADR-0076](ADR-0076-phase-1-module-scope.md) (Proposed) adds an omnichannel inbox (WhatsApp, Instagram, Facebook) and marketing to phase 1 and asks for a messaging and SMS connector contract first (DSC-022). [OPR-015](../product/opr-015-messaging-channel.md) already designs WhatsApp as a *staff* channel into the chat; this is the other direction: a tenant's customers writing to the business. It brings a new processor (Meta, an SMS provider), untrusted text at volume, and sends that cost money and reach people outside the tenant.

Platform facts (Meta developer docs, accessed 2026-11-27):
- WhatsApp: a user message or call starts a 24-hour customer service window, reset by each new one; inside it any service message may be sent; when it closes only pre-approved templates may be sent ([send messages](https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/send-messages)). The send response means accepted, not delivered; status arrives by webhook (sent, delivered, read, failed); order is not guaranteed; no delivered status before the time-to-live (30 days by default) means dropped (same page).
- Templates are `authentication`, `marketing` or `utility`; only `APPROVED` templates can be sent ([template guidelines](https://developers.facebook.com/docs/whatsapp/message-templates/guidelines)).
- Opt-in before business-initiated messages: the person shares a number and agrees to messages from a named business; the method is the business's choice within local law; Meta recommends opt-in per category and clear opt-out ([getting opt-in](https://developers.facebook.com/docs/whatsapp/overview/getting-opt-in)). That page names no record-keeping duty; we keep records anyway.
- Messenger and Instagram: a 24-hour standard messaging window for most user actions (up to 7 days after a click-to-message ad); a Human Agent tag allows manual replies for 7 days; tags outside approved use can lead to restrictions ([Messenger policy overview](https://developers.facebook.com/docs/messenger-platform/policy/policy-overview)).
- Webhooks: `X-Hub-Signature-256` carries a SHA-256 signature made with the app secret; failed deliveries are retried for up to 36 hours and receivers should de-duplicate ([webhooks getting started](https://developers.facebook.com/docs/graph-api/webhooks/getting-started)). That the construction is HMAC: UNVERIFIED from the page read.
- UNVERIFIED (not read at an official source): Meta business verification steps and lead times; whether service-window replies are charged; per-country WhatsApp rates; Meta data residency and processor terms; SMS sender-id registration and marketing-SMS rules in KSA, UAE, Egypt and Qatar; cross-border transfer rules under each market's data law (LEG-003).

## Decision
1. **One conversation model** across WhatsApp, Instagram and Messenger (Meta's business platform) plus one provider-agnostic SMS port: [contracts/connector-messaging.md](../../contracts/connector-messaging.md) 0.1.0 and its schema. Channel differences live in a capability declaration, not in callers. Distinct from OPR-015: customer contacts are never principals and never run tools.
2. **Inbound is always untrusted** (L3, PI-RULE-1 to 5, AGENTS.md security rules). Sanitised, flagged, labelled at the boundary; any thread with inbound text is tainted; links and media are not fetched or read in v1.
3. **Replies are drafts by default.** An agent drafts into the inbox; a human sends.
4. **Auto-reply** is a per-tenant opt-in limited to a fixed list of safe intents (greeting, opening hours, location, hand-off), inside the service window, with fixed tenant-approved texts (the model only classifies), one per intent per window and daily caps (placeholders, Q-156). This is an agent-initiated external send, which the action-policy table today forbids ("draft-only, everywhere"). So it stays off until a SEC-owned action-policy row and its security review allow it; this ADR does not change the table or the human floor.
5. **Outbound marketing only through approved templates**, to contacts with a granted marketing consent recorded per contact, channel, country and purpose; opt-out (STOP and Arabic equivalents, in-app, provider block) revokes at once. Marketing sends are R3, human-initiated with an approval; never agent-creatable.
6. **Sending is a Tool API write**: `message.send_reply` and utility `message.send_template` to one contact are R1, marketing and any batch R3; idempotency key required; recipient only by contact record id (prompt-injection-defence 5.1).
7. **Per-tenant credentials in the secret store**, referenced by `credentialRef`; a channel account binds to exactly one tenant; inbound resolves the tenant only from the verified account id.
8. **Webhooks verified** (signature before parsing, fail closed), **idempotent** (dedup key per provider event) and **replay-protected** (seen keys and a timestamp window where the provider sends one).
9. **Minimise personal data**: sealed numbers plus keyed hash, opaque refs in objects, no bodies in events; retention per market from the country pack, shortest placeholder until counsel sets it.
10. **Customer go-live items, not build items**: each customer's Meta business verification, display name, template approvals per language, and SMS sender registrations (ADR-0076 decision 11). Build and tests use provider test numbers and synthetic data only.
11. Events 0.3.0 (following the 0.2.0 payment types of ADR-0077) adds `message.*`, `consent.*` and `meter.message_sent` (additive).

## Alternatives rejected
- A separate model per channel: duplicates consent, audit and inbox logic three times and lets rules drift.
- Reuse OPR-015's staff binding for customers: would give a customer number a principal and a tool menu.
- Model-written auto-replies: a tainted model send to an outside person with no human gesture; breaks the action-policy table and PI rules.
- Marketing by agents, or without per-purpose consent: floor breach and a PDPL and Meta policy risk.
- Pick one SMS vendor now: the four markets differ on sender registration (UNVERIFIED); a port defers the choice to DSC-024.

## Consequences
- Easier: one inbox screen (WEB-035) and marketing contract (BPL-055) build on one set of objects; contract tests guard the rules JSON Schema can express.
- Harder: auto-reply needs an action-policy row first; marketing waits on counsel per market; Meta adds a sub-processor and cost line.
- Must do: DSC-024 (build, test numbers only); a SEC action-policy row for `message.*` and auto-reply; LEG-003 per-market transfer and marketing-consent answers; country packs carry the messaging retention period.
- Open points: Q-695 (own Meta app or ours), Q-696 (Cloud API or BSP, SMS provider per market), Q-697 (Messenger and Instagram tags in v1), Q-698 (replay window, auto-reply caps with Q-156, owner of the action-policy row).

## Supersedes
none
